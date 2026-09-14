# 内网一键部署

## 直接部署

服务器准备 Docker Engine 与 Docker Compose v2，将本项目放到服务器后执行：

```bash
chmod +x 一键部署.sh
./一键部署.sh
```

首次执行会自动选择一个 RFC1918 内网 IPv4，使用 8080 端口，生成 `.env` 中的数据库口令与邮箱加密密钥，然后构建前端和后端、启动 PostgreSQL、执行数据库迁移并进行健康检查。最后在终端中创建首个管理员，密码不会回显。重复运行沿用 `.env` 和两个 Docker 数据卷，可用于发布当前目录中的新版本。

启动前会检查同名 Compose 项目、既有数据卷、Docker 映射端口及宿主机监听端口。默认 8080 被占用时会自动在 18080–18180 中选择可用端口；使用 `--port` 明确指定的端口发生冲突时会停止，不会结束或接管原服务。如果已有数据卷但 `.env` 丢失，脚本也会停止，避免生成新加密密钥导致历史敏感信息无法解密。

只做检查而不创建配置或启动容器：

```bash
./一键部署.sh --check --bind 192.168.10.20 --port 8080
```

如服务器有多个内网网卡，请在首次运行时指定地址：

```bash
./一键部署.sh --bind 192.168.10.20 --port 8080
```

脚本只绑定端口，不会改写主机防火墙。若其他内网电脑无法访问，请让内网管理员仅向需要的办公网段开放所选 TCP 端口。

HTTP 模式适合受控内网试运行。正式处理投资者资料或邮箱授权码时，应由公司已有的 HTTPS 网关终止 TLS，并将流量转发到本机容器端口：

```bash
./一键部署.sh --bind 127.0.0.1 --origin https://fundops.intra.example
```

该模式会自动设置安全 Cookie。域名解析、证书和公司网关由内网基础设施提供；应用容器仍通过 HTTP 接受同机反向代理流量。

## 数据与密钥

- PostgreSQL 数据位于 Docker 卷 `xuchuan-operations_postgres_data`。
- 邮件原件和上传资料位于卷 `xuchuan-operations_archive_data`。
- `.env` 权限为 600，包含数据库口令和用于加密邮箱授权码、投资者敏感字段的 `MAIL_ENCRYPTION_KEY`。
- `.dockerignore` 会阻止 `.env`、运行数据库、邮件归档、待整理文件和本机依赖进入 Docker 构建上下文。
- 备份必须同时覆盖数据库、归档卷和 `.env`，并把备份存放在另一台受控主机。丢失 `MAIL_ENCRYPTION_KEY` 后，已保存的加密信息无法恢复。
- 停止服务使用 `docker compose --env-file .env down`。不要附加 `-v`，否则会删除数据卷。

## 日常命令

```bash
docker compose --env-file .env ps
docker compose --env-file .env logs -f --tail 200
./一键部署.sh
```

若需要更换监听地址或域名，先备份 `.env`，然后同步修改 `BIND_ADDRESS`、`APP_PORT`、`ALLOWED_ORIGINS` 和 `COOKIE_SECURE`；重新执行脚本即可应用配置。
