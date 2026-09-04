# 序川 · 基金运营工作台

第一阶段开发版 **v0.1**。正式应用从空数据开始，沿用已确认的暖白、陶土色侧栏与轻动效。

当前是可运行的核心链路实现，不代表全部第一阶段业务已经验收：真实邮箱、各托管模板、完整持仓解析及收益口径仍待联调。

## 目录

- `frontend/`：React + TypeScript 正式前端，只连接实际 API，没有预设业务数据。
- `backend/`：FastAPI + SQLAlchemy、数据库迁移、只读 IMAP 采集与解析 worker。
- `preview/`：此前确认的独立设计原型；保留不变，不存放真实业务数据。
- `docs/第一阶段_开发落地与验收.md`：已实现、待完成、业务边界及验收记录。
- `docs/基金运营工作台_V2_业务需求与调研总纲.md`：产品与业务决策依据。
- `docs/基金运营工作台_V2_总体架构_改良版.md`：长期领域方向、技术边界与渐进演进基线。
- `docs/基金运营工作台_V2_前端架构与开发规范.md`：正式前端的路由、状态、组件、权限和测试规范。
- `docs/基金运营工作台_V2_后端架构与开发规范.md`：模块化单体、API、事务、数据、任务和安全规范。
- `docs/基金运营工作台_V2_开发实施手册.md`：从需求准入到开发、测试、发布、回滚的执行手册。

## 已实现的核心链路

登录 → 按管理人授权 → 产品 / 份额建档 → 上传或 IMAP 只读收件 → 原件归档 → 后台解析 → 新产品待确认 / 基础规则自动确认 / 异常待办 → 牌照成员直接处理 → 有效净值、反账版本与审计。

产品可人工创建、由运营确认邮件解析候选后创建，或先登记简化的产品备案事项并在备案结束后转入台账。异常无需领取，当前牌照成员均可查看和处理；管理员拥有当前牌照全部页面和操作权限，所有操作仍记录实际账号。

原邮件、文件与净值候选只追加，切换有效版本不会覆盖原记录。原件、净值候选、审计表有数据库级更新 / 删除拦截；下载时核验 SHA-256。该机制不是防数据库超级管理员或操作系统管理员的 WORM 保证。

## 一键启动与管理员登录（本机试用）

在项目文件夹中右键“在终端打开”，运行：

```bash
./一键启动.sh
```

首次运行会检查 Python 环境、安装锁定依赖、构建页面并迁移数据库，然后引导你填写：

1. 集团名称（没有集团就填公司名称）、管理人主体名称。
2. 管理员姓名、**登录邮箱**。
3. 是否同时授予运营操作权限、是否允许下载资料。需要自己建产品、上传和确认净值时，运营权限选 `y`；每项直接回车默认不授予，后续可在“组织与权限”修改。
4. 自行设置 **12–128 位密码**，输入两次。终端不显示密码或星号，属于正常现象。

完成后自动打开 **http://127.0.0.1:8000**。管理员与员工使用同一个登录页，输入刚设置的邮箱和密码；登录后在左侧“组织与权限”管理成员和授权。**没有内置管理员，也没有默认密码**；请勿把密码发到聊天。

启动窗口需要保持打开。按 `Ctrl+C` 停止 API 和解析服务；再次运行同一脚本会保留账号、密码和业务数据，未变化的前端不重复构建。不要同时用手动命令运行另一套 worker。

脚本适用于 Linux / macOS，需 Node.js 22.13+ 与 Python 3.12+；已有 `uv` 时可自动准备 Python 3.12。首次安装需要网络，安装工具失败会停止并显示错误，不会清空数据库。若文件管理器支持“作为程序运行 / 在终端运行”，也可以这样打开脚本；若双击只显示源码，使用上面的终端命令即可。

常用操作：

```bash
# 端口冲突时换一个端口，不会强行结束其他程序
./一键启动.sh --port 8001

# 不自动打开浏览器
./一键启动.sh --no-open

# 忘记密码：先按 Ctrl+C 停止启动窗口，再执行以下命令
# 将邮箱换成已有管理员的真实登录邮箱；新密码仍通过终端隐藏输入
./一键启动.sh --reset-password your-admin@example.com
```

重置密码会使该账号的全部已登录会话失效，不会更改其他账号或牌照权限。

- 数据库：`runtime/development.db`；原件归档：`runtime/archive/`。不要删除 `runtime/`；备份时需一起备份数据库和归档文件。
- 日志：`runtime/logs/api.log`、`runtime/logs/worker.log`，追加保留供排查；日志不自动轮转，请留意磁盘空间。
- 上传文件会后台解析；仅管理员在网页中启用的邮箱会被后台只读同步。旧版 `.env.mail` 配置仅为迁移兼容，新邮箱请直接在网页登记。
- 一键入口固定管理本机开发库。如果终端已有 `DATABASE_URL` / `ARCHIVE_DIR`，会拒绝启动以避免误操作其他环境。
- 此入口只监听本机，使用 SQLite 和本机 HTTP，**不作为公司多人生产部署**；正式使用见下方 PostgreSQL / 内网 HTTPS 部署说明。
- 此前 `http://127.0.0.1:18000` 是独立的假数据联调服务，不是这里的一键启动实例，账号和数据不会自动迁移。

## 手动本地开发（进阶）

需要 Python 3.12、Node 22.13+。正式多人部署使用 PostgreSQL 17；SQLite 仅限本地单进程调试，不能作为并发一致性的验收依据。

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r backend/requirements.lock
uv pip install --python .venv/bin/python --no-deps -e backend
uv pip install --python .venv/bin/python 'pytest>=8,<10' 'httpx>=0.28,<1'
```

在仓库根目录创建运行目录并迁移（不创建示例用户或产品）：

```bash
mkdir -p runtime
.venv/bin/alembic -c backend/alembic.ini upgrade head
.venv/bin/python -m app.cli bootstrap --group '你的集团名称' --manager '你的管理人名称' --email 'your-admin@example.com' --name '管理员' --roles admin,operator --download
```

初始化密码通过终端隐藏输入两次，不存在默认密码。`admin` 不隐含运营权限；上例显式授予 `operator` 和下载权限。

三个终端分别运行：

```bash
# API，开发环境 HTTP 需显式关闭 Secure Cookie；生产 HTTPS 必须保持 true。
COOKIE_SECURE=false .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# 只处理上传队列，不连接邮箱
.venv/bin/python -m app.worker

# 前端（在 frontend 目录）
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`。前端使用同源 `/api` 代理。构建后也可由 API 直接提供静态页面；此时必须将准确的页面来源加入 `ALLOWED_ORIGINS`，例如 `http://127.0.0.1:8000`。

## 内网容器部署

1. 将 `.env.example` 复制为 `.env`，填写至少 32 位的 URL 安全随机数据库口令和准确的应用访问来源。
2. 生成 `MAIL_ENCRYPTION_KEY` 并写入 `.env`；这是网页邮箱授权码的独立加密密钥，必须另行备份。
3. 运行以下命令构建并启动。Compose 会先执行迁移，再启动 API / worker。

```bash
docker compose up -d --build
docker compose run --rm api python -m app.cli bootstrap --group '你的集团名称' --manager '你的管理人名称' --email 'your-admin@example.com' --name '管理员' --roles admin,operator --download
```

默认网关仅绑定 `127.0.0.1:8080`。正式访问应通过内网 HTTPS 反向代理，不要将调试服务直接暴露公网。配置 `ALLOWED_ORIGINS=https://真实内网域名`、`COOKIE_SECURE=true`；只在本机 HTTP 验证时允许改为 `false`。

数据库和归档文件分别使用持久卷。不要执行 `docker compose down -v`，它会删除卷。上线前必须配置双份备份、加密、恢复演练、容量监控及主机权限。

容器配置已提供；是否能在目标内网完成镜像拉取、证书配置与备份恢复，需要在部署环境验收。镜像标签采用主版本轨道，部署应记录实际 digest，并经过补丁升级测试。

## 邮箱接入（需要明确授权范围）

管理员登录后进入“组织与权限” → “邮箱接入”，可登记和管理多个邮箱。每个邮箱分别填写：

- 邮箱名称、IMAP 服务器、端口、SSL / STARTTLS；
- 完整邮箱账号和客户端授权码；
- 从哪一天开始同步、仅收件箱或所有可读取文件夹；
- 是否启用后台同步；163 邮箱建议开启“发送客户端标识”。

新建或启用前会先测试连接，失败不会保存新授权码。授权码通过 HTTPS / 本机同源页面提交，使用 Fernet 加密后写入数据库，API 和页面均不会回显明文；审计日志只记录邮箱、同步范围和是否更换凭据。管理员可以测试、编辑、启用或停用，每个邮箱故障互不影响，停用不会删除历史邮件和附件。

本机一键启动首次保存邮箱时，会生成权限为 600 的 `runtime/private/mail-encryption.key`。必须与数据库分开备份；密钥丢失后只能重新填写邮箱授权码。正式容器部署必须在 `.env` 设置固定 `MAIL_ENCRYPTION_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

原邮件采用 `readonly=True`、`BODY.PEEK[]` 收取，不设置已读、不移动、不删除。所有文件夹模式按“文件夹 + UIDVALIDITY + UID”断点续收；同一原件出现在多个文件夹时按 SHA-256 只归档一份。每轮每个邮箱最多收取 100 封，持续运行会分批完成历史导入。自动刷新 OAuth token、连续故障退避、更大邮件容量及自定义托管模板路由仍需生产联调。

## 管理多个牌照

```bash
.venv/bin/python -m app.cli list-managers
.venv/bin/python -m app.cli add-manager --group-id '已有集团ID' --name '关联管理人名称'
.venv/bin/python -m app.cli link-member --email 'existing@example.com' --manager-id '目标牌照ID' --roles admin,operator --download
.venv/bin/python -m app.cli reset-password --email 'existing@example.com'
```

已有账号关联新牌照不会覆盖密码或其他牌照权限。日常成员角色、下载权及产品范围由本牌照管理员在界面调整。密码重置仅由部署管理员在本地工具执行；暂无自助找回密码。

## 测试

本次一键启动回归：SQLite 后端 42 项通过、2 项 PostgreSQL 专用并发测试跳过；PostgreSQL 后端 44 项全部通过；前端 3 项数字格式测试、类型检查和生产构建通过。专项测试覆盖共享异常并发、管理员完整权限、待确认邮件产品、备案转产品、多邮箱加密与只读同步。

启动器端到端测试使用临时目录和独立数据库，不使用本机管理员或联调账号。执行过一次一键启动并准备好构建后会运行该测试；尚未准备前端构建时会明确跳过它。

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm run build
npm audit
```

PostgreSQL 专用测试使用独立的 `xuchuan_test` 数据库。测试会创建并清理自身 UUID 命名的 schema，禁止指向正式数据库：

```bash
docker compose -f compose.test.yaml up -d --wait
TEST_DATABASE_URL=postgresql+psycopg://qa:qa-isolated-local-only@127.0.0.1:55432/xuchuan_test .venv/bin/python -m pytest backend/tests -q
docker compose -f compose.test.yaml stop
```

测试库仅监听本机 55432，数据在 tmpfs，停止后不保留。该固定测试口令严禁用于正式环境。

独立的页面联调服务：

```bash
# 先完成前端 build；只用于假数据界面验收，绝不接入真实邮箱
.venv/bin/python backend/tests/serve_qa.py
```

它在 `127.0.0.1:18000` 启动，每次生成新的 `runtime/ui-qa-*` 目录，不写入正式开发数据库。测试账号仅用于该服务，详见测试脚本。
