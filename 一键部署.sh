#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
BIND_OVERRIDE=""
PORT_OVERRIDE=""
ORIGIN_OVERRIDE=""
SKIP_ADMIN=false
NO_BUILD=false
CHECK_ONLY=false

usage() {
  cat <<'EOF'
序川 · 内网一键部署

用法：
  ./一键部署.sh
  ./一键部署.sh --bind 192.168.1.20 --port 8080
  ./一键部署.sh --bind 127.0.0.1 --origin https://fundops.intra.example

选项：
  --bind IP       Docker 网关监听的本机 IP；首次部署默认自动识别 RFC1918 内网 IP
  --port PORT     网关端口，首次部署默认 8080
  --origin URL    浏览器实际访问来源；HTTPS 反向代理部署时必须填写
  --skip-admin    跳过首次管理员交互设置
  --no-build      使用现有镜像启动，不重新构建
  --check         只读检查同名项目、数据卷和端口，不创建配置或启动服务
  -h, --help      显示帮助

首次生成 .env 后，重复运行会沿用原配置并保留数据库与归档卷。
EOF
}

fail() {
  printf '部署未完成：%s\n' "$1" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --bind)
      (($# >= 2)) || fail "--bind 缺少 IP"
      BIND_OVERRIDE="$2"
      shift 2
      ;;
    --port)
      (($# >= 2)) || fail "--port 缺少端口"
      PORT_OVERRIDE="$2"
      shift 2
      ;;
    --origin)
      (($# >= 2)) || fail "--origin 缺少 URL"
      ORIGIN_OVERRIDE="${2%/}"
      shift 2
      ;;
    --skip-admin)
      SKIP_ADMIN=true
      shift
      ;;
    --no-build)
      NO_BUILD=true
      shift
      ;;
    --check)
      CHECK_ONLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "未知参数：$1（使用 --help 查看用法）"
      ;;
  esac
done

command -v docker >/dev/null 2>&1 || fail "未找到 Docker，请先安装 Docker Engine 与 Compose v2"
docker compose version >/dev/null 2>&1 || fail "未找到 docker compose v2"
docker compose up --help | grep -q -- '--wait' \
  || fail "Docker Compose 版本过旧，请升级到支持 up --wait 的 Compose v2"
docker info >/dev/null 2>&1 || fail "当前账号无法连接 Docker；请启动 Docker，并将部署账号加入 docker 组后重新登录"

valid_ipv4() {
  local address="$1" a b c d
  [[ "$address" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || return 1
  IFS=. read -r a b c d <<<"$address"
  ((a <= 255 && b <= 255 && c <= 255 && d <= 255))
}

EXISTING_PROJECT=false
check_existing_project() {
  local container working_dir
  while read -r container; do
    [[ -n "$container" ]] || continue
    EXISTING_PROJECT=true
    working_dir="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$container")"
    if [[ -n "$working_dir" && "$working_dir" != "$PROJECT_DIR" ]]; then
      fail "发现另一目录中的同名 Compose 项目 xuchuan-operations：${working_dir}。请勿从当前目录接管其容器和数据卷"
    fi
  done < <(docker ps -aq --filter label=com.docker.compose.project=xuchuan-operations)

  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ "$EXISTING_PROJECT" == true ]] \
      || docker volume inspect xuchuan-operations_postgres_data >/dev/null 2>&1 \
      || docker volume inspect xuchuan-operations_archive_data >/dev/null 2>&1; then
      fail "检测到既有 xuchuan-operations 容器或数据卷，但 .env 已丢失。请从备份恢复原 .env，脚本不会生成新密钥覆盖既有部署"
    fi
  fi
}

docker_port_conflict() {
  local bind_address="$1" app_port="$2" container project host_ip host_port bindings
  while read -r container; do
    [[ -n "$container" ]] || continue
    project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container")"
    if [[ "$EXISTING_PROJECT" == true && "$project" == "xuchuan-operations" ]]; then
      continue
    fi
    bindings="$(docker inspect --format '{{range $bindings := .NetworkSettings.Ports}}{{range $bindings}}{{println .HostIp .HostPort}}{{end}}{{end}}' "$container")"
    while read -r host_ip host_port; do
      [[ -n "$host_port" && "$host_port" == "$app_port" ]] || continue
      if [[ "$bind_address" == "0.0.0.0" || "$host_ip" == "0.0.0.0" \
        || "$host_ip" == "::" || "$host_ip" == "$bind_address" ]]; then
        return 0
      fi
    done <<<"$bindings"
  done < <(docker ps -q)
  return 1
}

host_port_conflict() {
  local bind_address="$1" app_port="$2" local_address host_ip host_port
  command -v ss >/dev/null 2>&1 || return 1
  while read -r local_address; do
    [[ -n "$local_address" ]] || continue
    host_port="${local_address##*:}"
    host_ip="${local_address%:*}"
    host_ip="${host_ip#[}"
    host_ip="${host_ip%]}"
    [[ "$host_port" == "$app_port" ]] || continue
    if [[ "$bind_address" == "0.0.0.0" || "$host_ip" == "0.0.0.0" \
      || "$host_ip" == "*" || "$host_ip" == "::" || "$host_ip" == "$bind_address" ]]; then
      return 0
    fi
  done < <(ss -H -ltn 2>/dev/null | awk '{print $4}')
  return 1
}

port_conflict() {
  docker_port_conflict "$1" "$2" && return 0
  if [[ "$EXISTING_PROJECT" != true ]] && host_port_conflict "$1" "$2"; then
    return 0
  fi
  return 1
}

private_ipv4() {
  local address="$1" a b _
  valid_ipv4 "$address" || return 1
  IFS=. read -r a b _ <<<"$address"
  ((a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168)))
}

detect_private_ip() {
  local candidate
  if command -v ip >/dev/null 2>&1; then
    while read -r candidate; do
      if private_ipv4 "$candidate"; then
        printf '%s' "$candidate"
        return 0
      fi
    done < <(ip -o -4 address show scope global | awk '{split($4,a,"/"); print a[1]}')
  fi
  if command -v hostname >/dev/null 2>&1; then
    for candidate in $(hostname -I 2>/dev/null || true); do
      if private_ipv4 "$candidate"; then
        printf '%s' "$candidate"
        return 0
      fi
    done
  fi
  return 1
}

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

check_only() {
  local bind_address app_port candidate existing_bind existing_port
  existing_bind=""
  existing_port=""
  if [[ -f "$ENV_FILE" ]]; then
    existing_bind="$(env_value BIND_ADDRESS)"
    existing_port="$(env_value APP_PORT)"
  fi
  bind_address="${BIND_OVERRIDE:-${existing_bind:-}}"
  app_port="${PORT_OVERRIDE:-${existing_port:-8080}}"
  if [[ -z "$bind_address" ]]; then
    bind_address="$(detect_private_ip)" \
      || fail "无法自动识别 RFC1918 内网 IP，请用 --bind 指定需要检查的本机 IP"
  fi
  valid_ipv4 "$bind_address" || [[ "$bind_address" == "0.0.0.0" ]] \
    || fail "需要检查的监听地址不是有效 IPv4 地址"
  if ! [[ "$app_port" =~ ^[0-9]+$ ]] || ! ((app_port >= 1 && app_port <= 65535)); then
    fail "需要检查的端口必须是 1–65535 的整数"
  fi
  if port_conflict "$bind_address" "$app_port"; then
    printf '发现冲突：%s:%s 已由其他 Docker 项目占用。\n' "$bind_address" "$app_port"
    for candidate in $(seq 18080 18180); do
      if ! port_conflict "$bind_address" "$candidate"; then
        printf '建议使用：./一键部署.sh --bind %s --port %s\n' "$bind_address" "$candidate"
        break
      fi
    done
    return 2
  fi
  printf '检查通过：未发现同名项目接管风险，%s:%s 未被其他 Docker 项目占用。\n' "$bind_address" "$app_port"
}

write_environment() {
  local bind_address app_port allowed_origin cookie_secure postgres_password mail_key temporary candidate
  bind_address="${BIND_OVERRIDE:-}"
  app_port="${PORT_OVERRIDE:-8080}"
  allowed_origin="${ORIGIN_OVERRIDE:-}"

  if ! [[ "$app_port" =~ ^[0-9]+$ ]] || ! ((app_port >= 1 && app_port <= 65535)); then
    fail "端口必须是 1–65535 的整数"
  fi
  if [[ -z "$bind_address" ]]; then
    bind_address="$(detect_private_ip)" \
      || fail "无法自动识别 RFC1918 内网 IP，请用 --bind 明确指定本机内网 IP"
  fi
  if [[ "$bind_address" != "0.0.0.0" ]]; then
    valid_ipv4 "$bind_address" || fail "--bind 必须填写 IPv4 地址"
  fi
  if port_conflict "$bind_address" "$app_port"; then
    if [[ -n "$PORT_OVERRIDE" ]]; then
      fail "${bind_address}:${app_port} 已由其他 Docker 项目占用，请改用 --port 指定其他端口"
    fi
    for candidate in $(seq 18080 18180); do
      if ! port_conflict "$bind_address" "$candidate"; then
        app_port="$candidate"
        printf '默认端口 8080 已被占用，自动改用 %s。\n' "$app_port"
        break
      fi
    done
    [[ "$app_port" != "8080" ]] || fail "未找到可用的部署端口，请用 --port 明确指定"
  fi
  if [[ -z "$allowed_origin" ]]; then
    [[ "$bind_address" != "0.0.0.0" ]] \
      || fail "监听 0.0.0.0 时必须用 --origin 指定浏览器实际访问 URL"
    allowed_origin="http://${bind_address}:${app_port}"
  fi
  [[ "$allowed_origin" =~ ^https?://[^[:space:]/]+(:[0-9]+)?$ ]] \
    || fail "--origin 必须是无路径的 http(s) URL，例如 https://fundops.intra.example"

  command -v openssl >/dev/null 2>&1 || fail "首次部署需要 openssl 生成数据库和邮箱加密密钥"
  postgres_password="$(openssl rand -hex 32)"
  mail_key="$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n')"
  cookie_secure=false
  [[ "$allowed_origin" == https://* ]] && cookie_secure=true
  temporary="$(mktemp "$PROJECT_DIR/.env.tmp.XXXXXX")"
  trap 'rm -f -- "${temporary:-}"' EXIT
  cat >"$temporary" <<EOF
# 由 ./一键部署.sh 生成。此文件包含密钥，禁止提交或发送。
POSTGRES_PASSWORD=${postgres_password}
BIND_ADDRESS=${bind_address}
APP_PORT=${app_port}
ALLOWED_ORIGINS=${allowed_origin}
COOKIE_SECURE=${cookie_secure}
MAX_UPLOAD_MIB=25
MAIL_ENCRYPTION_KEY=${mail_key}
EOF
  chmod 600 "$temporary"
  mv -- "$temporary" "$ENV_FILE"
  trap - EXIT
  printf '已生成权限为 600 的 .env；数据库口令和邮箱加密密钥未显示。\n'
}

cd -- "$PROJECT_DIR"
check_existing_project
if [[ "$CHECK_ONLY" == true ]]; then
  check_only
  exit $?
fi
if [[ -f "$ENV_FILE" ]]; then
  if [[ -n "$BIND_OVERRIDE$PORT_OVERRIDE$ORIGIN_OVERRIDE" ]]; then
    fail ".env 已存在；为避免误改现网地址，本次未覆盖。请先备份并人工修改 BIND_ADDRESS、APP_PORT、ALLOWED_ORIGINS 和 COOKIE_SECURE"
  fi
else
  write_environment
fi

BIND_ADDRESS="$(env_value BIND_ADDRESS)"
APP_PORT="$(env_value APP_PORT)"
ALLOWED_ORIGINS="$(env_value ALLOWED_ORIGINS)"
BIND_ADDRESS="${BIND_ADDRESS:-127.0.0.1}"
APP_PORT="${APP_PORT:-8080}"
[[ -n "$ALLOWED_ORIGINS" ]] || fail ".env 缺少 ALLOWED_ORIGINS"
valid_ipv4 "$BIND_ADDRESS" || [[ "$BIND_ADDRESS" == "0.0.0.0" ]] \
  || fail ".env 中的 BIND_ADDRESS 不是有效 IPv4 地址"
if ! [[ "$APP_PORT" =~ ^[0-9]+$ ]] || ! ((APP_PORT >= 1 && APP_PORT <= 65535)); then
  fail ".env 中的 APP_PORT 必须是 1–65535 的整数"
fi
if port_conflict "$BIND_ADDRESS" "$APP_PORT"; then
  fail "${BIND_ADDRESS}:${APP_PORT} 已由其他 Docker 项目占用；请修改 .env 中的 APP_PORT 与 ALLOWED_ORIGINS"
fi

COMPOSE=(docker compose --env-file "$ENV_FILE")
"${COMPOSE[@]}" config --quiet || fail "Compose 配置校验失败，未改变正在运行的服务"

printf '正在构建并启动 PostgreSQL、迁移、API、邮件 worker 和内网页面……\n'
UP_ARGS=(up -d --remove-orphans --wait --wait-timeout 300)
if [[ "$NO_BUILD" == true ]]; then
  UP_ARGS+=(--no-build)
else
  UP_ARGS+=(--build)
fi
"${COMPOSE[@]}" "${UP_ARGS[@]}"

if [[ "$SKIP_ADMIN" != true ]]; then
  if [[ -t 0 && -t 1 ]]; then
    printf '\n检查首次管理员账号（密码输入不会显示）……\n'
    "${COMPOSE[@]}" run --rm --no-deps api python -m app.cli setup
  else
    printf '当前不是交互终端，已跳过管理员设置。稍后在项目目录运行：\n'
    printf 'docker compose --env-file .env run --rm --no-deps api python -m app.cli setup\n'
  fi
fi

"${COMPOSE[@]}" exec -T api python -c \
  "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=5)); assert data['status'] == 'ok'"

ACCESS_URL="${ALLOWED_ORIGINS%%,*}"
cat <<EOF

部署完成，数据库迁移及服务健康检查已通过。
访问地址：${ACCESS_URL}

常用命令：
  查看状态：docker compose --env-file .env ps
  查看日志：docker compose --env-file .env logs -f --tail 200
  停止服务：docker compose --env-file .env down

停止命令不会删除数据卷。不要使用 docker compose down -v。
EOF
