# OfficeAgent 技术落地计划清单 v2

> 本计划基于实际代码扫描生成(扫描时间 2026-07-04),整合用户原始三阶段诉求与项目当前真实状态。所有任务标注「依赖」「验收标准」「涉及文件」,可直接转化为 Sprint 任务卡。
>
> **核心策略**:先对齐后端基线(Phase 0),再启动前端(Phase 1),避免在残缺后端上叠层。剔除商业化计费/订阅分层,仅围绕技术实现与功能落地。

---

## 〇、现状基线(扫描结论)

### 已存在(可直接复用,无需重做)

| 资产 | 路径 | 状态 |
|---|---|---|
| FastAPI 主入口 | [src/officeagent/main.py](file:///e:/Officeagent/officeagent/src/officeagent/main.py) | ✅ 已含 lifespan 模式开关 |
| 5 个 API 路由 | [api/routers/](file:///e:/Officeagent/officeagent/src/officeagent/api/routers/) | ✅ 43 个端点(auth/chat/documents/tasks/tools) |
| 12 个核心子模块 | [core/](file:///e:/Officeagent/officeagent/src/officeagent/core/) | ✅ topology/skills/flywheel/orchestrator/llm/tools/memory/security/reasoning/reflection/prompt/retrieval |
| LangGraph 编排 | [graph/](file:///e:/Officeagent/officeagent/src/officeagent/graph/) | ✅ 5 节点 + 条件边 + MemorySaver |
| 加密资产层 | [assets/](file:///e:/Officeagent/officeagent/src/officeagent/assets/) | ✅ bundle/crypto/snapshot |
| 3 个业务模块 | [business/](file:///e:/Officeagent/officeagent/src/officeagent/business/) | ✅ search/word/converter |
| 内存存储层 | [services/storage.py](file:///e:/Officeagent/officeagent/src/officeagent/services/storage.py) | ⚠️ UserStore/ApiKeyStore/DocumentStore/TaskStore 全内存,需替换为持久化 |
| JWT 鉴权(基础) | [api/routers/auth.py](file:///e:/Officeagent/officeagent/src/officeagent/api/routers/auth.py) | ⚠️ HS256 + PBKDF2,需升级 |
| Docker 骨架 | [deploy/docker/Dockerfile](file:///e:/Officeagent/officeagent/deploy/docker/Dockerfile) + [docker-compose.yml](file:///e:/Officeagent/officeagent/docker-compose.yml) | ⚠️ 链路断裂,见 0.2 |
| 4 份核心文档 | ARCHITECTURE.md / DEVELOPMENT.md / README.md / SELF_EVOLUTION_AGENT_PLAN.md | ✅ |

### 缺失(必须新增)

1. **前端代码**:零基础,需从零搭建
2. **CI/CD**:`.github/workflows/` 完全缺失
3. **nginx 配置**:完全缺失
4. **数据库迁移**:`migrations/` + `alembic.ini` 缺失
5. **`pyproject.toml`**:Dockerfile 引用但缺失(构建会失败)
6. **prod compose**:`deploy/docker/docker-compose.prod.yml` 缺失
7. **业务模块**:`literature/`、`chart/`、`pdf/`、`parser/`、`learning/`、`workflow/` 6 个子模块未创建
8. **配置文件**:`topology_schema.yaml`、`skill_bindings.yaml`、`flywheel_rules.yaml` 未创建;`settings.yaml` 未追加拓扑/技能/飞轮配置域
9. **项目根级 `assets/` 数据目录**:`topology/`、`traces/`、`snapshots/` 等未创建
10. **Token 黑名单**:JWT 登出为无状态,未接 Redis 黑名单
11. **依赖冗余**:`python-jose` / `passlib[bcrypt]` 在 requirements.txt 中但代码未使用

---

## 一、统一技术基线(全项目强制执行)

### 1.1 前端与客户端技术栈

| 类别 | 选型 | 备注 |
|---|---|---|
| 框架 | React 18 + TypeScript + Vite | 严格 TS,禁用 `any` |
| 样式 | Tailwind CSS + shadcn/ui | 极简原生风格,组件源码直接读取修改 |
| 编辑内核 | Monaco Editor | VS Code/Cursor 同款,支持文档预览、语法高亮 |
| 图标 | Lucide React | 极简线性,风格统一 |
| 桌面壳 | Electron + electron-vite | 全平台打包用 electron-builder |
| 状态管理 | Zustand | 比 Redux 轻,适合中型应用 |
| 数据请求 | TanStack Query + axios | 自动缓存/重试/失效 |
| 路由 | React Router v6 | |
| 表单 | React Hook Form + Zod | 类型安全校验 |
| **复用原则** | 桌面客户端、Web 管理后台共用同一套组件库与业务逻辑 | 单仓库 monorepo(pnpm workspace) |

### 1.2 全链路安全规范

| 层 | 规范 | 实施位置 |
|---|---|---|
| 传输层 | 全站 HTTPS TLS 1.3 + Electron 端证书钉扎 | nginx + Electron `session.webRequest.onBeforeSendHeaders` |
| 密码层 | 服务端 Argon2id 慢哈希 + 单用户独立随机盐;客户端使用服务端公钥 RSA-2048 加密后传输 | 替换 [services/storage.py](file:///e:/Officeagent/officeagent/src/officeagent/services/storage.py) 中 PBKDF2 |
| 鉴权层 | 双 Token(Access 2h + Refresh 7d)+ 设备指纹绑定,一设备一令牌 | 重写 [api/routers/auth.py](file:///e:/Officeagent/officeagent/src/officeagent/api/routers/auth.py) |
| 客户端存储 | Electron 端统一调用 `safeStorage` 系统级加密存储 | Electron 主进程封装 |
| 权限原则 | 所有权限校验、核心逻辑全部在后端执行 | 现有端点已遵守,需补 RBAC 中间件 |
| 审计要求 | 敏感操作全量留痕,支持追溯与导出 | 新增 `audit/` 模块 + 独立日志库 |

### 1.3 架构设计原则

- 前后端分离,接口统一 RESTful 规范(已对齐 OpenAPI 3.1)
- 核心逻辑后置服务端,客户端轻量化,仅做交互与展示
- 渐进式解耦,初期单体架构快速落地,后期按需拆分微服务(Phase 3)
- monorepo 结构:`apps/desktop` + `apps/admin` + `apps/web` + `packages/ui` + `packages/sdk`

---

## 二、分阶段落地计划

### 阶段 0:后端基线对齐与加固(P0-,2-3 周)

> **目标**:补齐后端短板,确保后续前端开发站在稳固地基上。**此阶段必须先于阶段 1 完成**。

#### 0.1 完成 Day 7 自进化集成收尾

| 项 | 内容 |
|---|---|
| 任务 | `services/service.py` 已改写为 `build_graph()`,但需验证 `process_with_graph()` 在真实场景下与现有 `/chat/message` 端点的兼容性 |
| 依赖 | 无 |
| 涉及文件 | [services/service.py](file:///e:/Officeagent/officeagent/src/officeagent/services/service.py)、[api/routers/chat.py](file:///e:/Officeagent/officeagent/src/officeagent/api/routers/chat.py)、[main.py](file:///e:/Officeagent/officeagent/src/officeagent/main.py) |
| 验收标准 | ① `OFFICEAGENT_MODE=evolve` 启动后 `/chat/evolve` 可用;② `OFFICEAGENT_MODE=legacy` 启动后 `/chat/message` 仍可用;③ 全量 779+ 测试通过 |
| 工作量 | 0.5 sprint |

#### 0.2 修复 Docker 构建链

| 项 | 内容 |
|---|---|
| 任务 | ① 补 `pyproject.toml`(PEP 621,引用 requirements.txt);② 补 `etcd` 服务到 docker-compose(Milvus 依赖);③ 写 `deploy/docker/docker-compose.prod.yml`(Makefile `deploy` 目标引用);④ 清理 requirements.txt 中未使用的 `python-jose` / `passlib[bcrypt]` |
| 依赖 | 无 |
| 涉及文件 | `pyproject.toml`(新增)、[docker-compose.yml](file:///e:/Officeagent/officeagent/docker-compose.yml)、`deploy/docker/docker-compose.prod.yml`(新增)、[requirements.txt](file:///e:/Officeagent/officeagent/requirements.txt) |
| 验收标准 | ① `docker compose up` 全部服务健康;② `docker compose -f deploy/docker/docker-compose.prod.yml up` 可启动;③ `make deploy` 不再报错 |
| 工作量 | 1 sprint |

#### 0.3 数据库迁移体系

| 项 | 内容 |
|---|---|
| 任务 | ① `alembic init migrations`;② 把 [scripts/init_db.py](file:///e:/Officeagent/officeagent/scripts/init_db.py) 的建表逻辑转为初始 migration;③ 校验 [models/db/models.py](file:///e:/Officeagent/officeagent/src/officeagent/models/db/models.py) 与 migration 一致;④ `Makefile migrate` 目标接通 |
| 依赖 | 0.2 |
| 涉及文件 | `migrations/`(新增)、`alembic.ini`(新增)、[Makefile](file:///e:/Officeagent/officeagent/Makefile) |
| 验收标准 | ① `alembic upgrade head` 在空库可建表;② `alembic downgrade base` 可回滚;③ CI 中加入 migration 校验 |
| 工作量 | 1 sprint |

#### 0.4 安全规范对齐(高优先)

| 项 | 内容 |
|---|---|
| 任务 | ① 密码哈希从 PBKDF2 升级到 **Argon2id**(`argon2-cffi` 库,内存 64MB/迭代 3/并行度 1);② 实现 **RSA-2048** 密码传输加密(服务端启动时生成密钥对,通过 `/auth/pubkey` 暴露公钥);③ JWT 改为**双 Token 体系**(Access 2h + Refresh 7d),Refresh Token 走 Redis 存储;④ **设备指纹绑定**(User-Agent + IP 段 + 客户端生成的 UUID,哈希后存 Redis);⑤ Redis **Token 黑名单**(登出时写入,中间件校验) |
| 依赖 | 0.3(需 users 表新增字段:`password_salt`、`device_fingerprint`、`last_login_at`) |
| 涉及文件 | [api/routers/auth.py](file:///e:/Officeagent/officeagent/src/officeagent/api/routers/auth.py)、[services/storage.py](file:///e:/Officeagent/officeagent/src/officeagent/services/storage.py)、[adapters/cache/redis.py](file:///e:/Officeagent/officeagent/src/officeagent/adapters/cache/redis.py)、新增 `core/security/auth/` 子包 |
| 验收标准 | ① 单元测试覆盖 Argon2id 哈希/校验;② RSA 加解密往返测试;③ 双 Token 刷新流程测试;④ 设备指纹不匹配时拒绝 Refresh;⑤ 登出后 Access Token 在 1s 内失效;⑥ 全链路 burp 抓包仅见密文 |
| 工作量 | 2 sprint |
| 风险 | Argon2id 参数需压测,过高会拖慢登录 |

#### 0.5 nginx 反向代理配置

| 项 | 内容 |
|---|---|
| 任务 | ① 写 `deploy/nginx/officeagent.conf`(HTTPS TLS 1.3 + HSTS + gzip + 静态资源缓存 + 反向代理到 `officeagent:8000`);② 写 `deploy/nginx/nginx.conf`(主配置);③ 生成自签证书脚本(开发用)+ Let's Encrypt 集成说明(生产用) |
| 依赖 | 0.2 |
| 涉及文件 | `deploy/nginx/`(新增) |
| 验收标准 | ① `curl https://localhost/api/v1/health` 返回 200;② SSL Labs 评级 A+;③ 静态资源 `Cache-Control` 正确 |
| 工作量 | 0.5 sprint |

#### 0.6 CI/CD 基础

| 项 | 内容 |
|---|---|
| 任务 | ① `.github/workflows/ci.yml`:Python 3.11 + 3.13 矩阵,`pytest + flake8 + black --check + mypy`;② `.github/workflows/build.yml`:Docker 镜像构建推送 GHCR;③ `.github/workflows/release.yml`:tag 触发,构建桌面端安装包(Phase 1 起接入) |
| 依赖 | 0.2、0.3 |
| 涉及文件 | `.github/workflows/`(新增) |
| 验收标准 | ① PR 合并前 CI 必过;② main 分支推送后镜像自动构建;③ release tag 触发安装包构建 |
| 工作量 | 1 sprint |

#### 0.7 配置文件与数据目录补全

| 项 | 内容 |
|---|---|
| 任务 | ① 创建 `config/topology_schema.yaml`(KTG 固定 Schema 声明);② 创建 `config/skill_bindings.yaml`(STP 初始绑定关系);③ 创建 `config/flywheel_rules.yaml`(MFP 飞轮触发规则);④ `settings.yaml` 追加 `topology` / `skills` / `flywheel` 三个配置域;⑤ 创建项目根级 `assets/` 数据目录(`topology/`、`traces/`、`snapshots/`、`skills/`、`flywheel/`、`meta/` 子目录) |
| 依赖 | 无 |
| 涉及文件 | [config/](file:///e:/Officeagent/officeagent/config/)、`assets/`(项目根新增) |
| 验收标准 | ① 自进化模式启动后能从 `assets/` 加载快照;② 配置变更无需改代码 |
| 工作量 | 0.5 sprint |

#### 0.8 持久化存储层替换

| 项 | 内容 |
|---|---|
| 任务 | 将 [services/storage.py](file:///e:/Officeagent/officeagent/src/officeagent/services/storage.py) 中 4 个 Store(UserStore/ApiKeyStore/DocumentStore/TaskStore)从内存实现改为 PostgreSQL 持久化,接口签名不变(适配器模式) |
| 依赖 | 0.3 |
| 涉及文件 | [services/storage.py](file:///e:/Officeagent/officeagent/src/officeagent/services/storage.py)、[models/db/models.py](file:///e:/Officeagent/officeagent/src/officeagent/models/db/models.py)、[adapters/db/postgres.py](file:///e:/Officeagent/officeagent/src/officeagent/adapters/db/postgres.py) |
| 验收标准 | ① 重启服务后数据不丢;② 现有 65 个 API 单元测试全部通过(可能需调整 fixture);③ 并发写入无冲突 |
| 工作量 | 1.5 sprint |

---

### 阶段 1:核心功能闭环(P0,1-2 个月)

> **目标**:完成可正常使用的桌面客户端 + 基础账号体系 + 管理后台,实现本地 Agent 全功能跑通。

#### 1.1 前端工程脚手架

| 项 | 内容 |
|---|---|
| 任务 | ① `apps/web` 初始化(Vite + React 18 + TS);② `packages/ui` 共享组件库(shadcn/ui + Tailwind);③ `packages/sdk` 自动生成的 TypeScript API client(从 OpenAPI);④ pnpm workspace 配置;⑤ ESLint + Prettier + TypeScript strict |
| 依赖 | 阶段 0 完成 |
| 涉及文件 | `apps/web/`、`packages/ui/`、`packages/sdk/`、`pnpm-workspace.yaml`、`package.json`(新增) |
| 验收标准 | ① `pnpm dev` 启动后能访问 `http://localhost:5173`;② `pnpm typecheck` 零错误;③ `pnpm lint` 零错误 |
| 工作量 | 1 sprint |

#### 1.2 OpenAPI SDK 自动生成

| 项 | 内容 |
|---|---|
| 任务 | ① 后端启动时导出 `openapi.json`(FastAPI 自动生成);② `packages/sdk` 用 `openapi-typescript` + `openapi-fetch` 生成类型安全 client;③ CI 中加入 schema 漂移检测 |
| 依赖 | 1.1 |
| 涉及文件 | `packages/sdk/`、`scripts/gen-sdk.sh` |
| 验收标准 | ① 后端新增端点后,前端 `pnpm gen:api` 可一键同步;② 前端调用任意端点均有类型提示 |
| 工作量 | 0.5 sprint |

#### 1.3 Electron 壳工程

| 项 | 内容 |
|---|---|
| 任务 | ① `apps/desktop` 用 electron-vite 初始化;② 主进程/渲染进程/预加载脚本分层;③ IPC 通信封装(`ipc-main` / `ipc-renderer` / `preload` 三层);④ 主进程托管文件操作与 Agent 调用(通过 HTTP 调后端);⑤ 集成 `safeStorage` 封装 |
| 依赖 | 1.1 |
| 涉及文件 | `apps/desktop/`、`apps/desktop/src/main/`、`apps/desktop/src/preload/` |
| 验收标准 | ① `pnpm dev:desktop` 启动后弹出 Electron 窗口;② 主进程能调用后端 `/api/v1/health`;③ 渲染进程无法直接 `require('fs')`(沙箱生效) |
| 工作量 | 1.5 sprint |

#### 1.4 三栏极简布局

| 项 | 内容 |
|---|---|
| 任务 | ① 左侧文件树(支持本地目录扫描、拖拽导入、右键菜单);② 中间文档编辑区(Monaco Editor 集成);③ 右侧 AI 对话面板(消息流 + 输入框 + 工具调用展示);④ 顶部工具栏(用户头像/设置/主题切换);⑤ 暗色模式 |
| 依赖 | 1.3 |
| 涉及文件 | `apps/desktop/src/renderer/components/`、`packages/ui/components/` |
| 验收标准 | ① 三栏可拖拽调整宽度;② 文件树点击文件后中间编辑器加载内容;③ 暗色模式切换无闪烁 |
| 工作量 | 2 sprint |

#### 1.5 Monaco Editor 集成

| 项 | 内容 |
|---|---|
| 任务 | ① `@monaco-editor/react` 集成;② 支持 .md/.txt/.py/.json/.yaml 语法高亮;③ 文档预览模式(Markdown 渲染);④ 文件保存(Ctrl+S)通过 IPC 写回磁盘;⑤ 自动保存(防丢失) |
| 依赖 | 1.4 |
| 涉及文件 | `apps/desktop/src/renderer/components/Editor/` |
| 验收标准 | ① 打开 10MB 文件不卡顿;② Ctrl+S 后磁盘文件 mtime 更新;③ 异常退出后重启能恢复未保存内容 |
| 工作量 | 1 sprint |

#### 1.6 AI 对话面板(对接自进化 Agent)

| 项 | 内容 |
|---|---|
| 任务 | ① 消息流 UI(用户/AI/工具调用三种气泡);② 流式输出对接 `/api/v1/chat/stream`(SSE);③ 自进化模式对接 `/api/v1/chat/evolve`;④ 工具调用过程可视化(展开/折叠);⑤ 拓扑路径展示(调用 `/api/v1/topology/stats`);⑥ 错误重试 |
| 依赖 | 1.4、阶段 0 完成 |
| 涉及文件 | `apps/desktop/src/renderer/components/Chat/` |
| 验收标准 | ① 发送消息后 200ms 内出现首字符;② 工具调用过程可展开查看入参出参;③ 网络断开后自动重连 |
| 工作量 | 2 sprint |

#### 1.7 登录鉴权页面(对接双 Token)

| 项 | 内容 |
|---|---|
| 任务 | ① 登录页(账号/密码 + 记住我);② 注册页(用户名/邮箱/密码/确认密码);③ 调用 `/auth/pubkey` 获取 RSA 公钥;④ 客户端用公钥加密密码后 POST `/auth/login`;⑤ 收到双 Token 后通过 `safeStorage` 存储;⑥ axios 拦截器自动附加 Access Token,401 时自动刷新;⑦ 设备指纹生成客户端 UUID 持久化 |
| 依赖 | 0.4、1.3 |
| 涉及文件 | `apps/desktop/src/renderer/pages/Auth/`、`packages/sdk/auth.ts` |
| 验收标准 | ① burp 抓包仅见密文密码;② Access Token 过期后自动刷新无感知;③ Refresh Token 失效后跳登录页;④ 不同设备登录互不踢 |
| 工作量 | 1.5 sprint |

#### 1.8 极简管理后台

| 项 | 内容 |
|---|---|
| 任务 | ① `apps/admin` 独立 Vite 应用;② 复用 `packages/ui` 组件库;③ 账号列表(分页/搜索/禁用/重置密码);④ 操作日志查询(按时间/用户/操作类型筛选);⑤ 系统配置管理(从 `settings.yaml` 暴露的运行时可改项);⑥ 管理员 RBAC 中间件(仅 admin 角色可访问) |
| 依赖 | 0.4、1.1 |
| 涉及文件 | `apps/admin/`、后端新增 `api/routers/admin.py` |
| 验收标准 | ① 普通用户访问 `/admin` 跳 403;② 禁用用户后该用户立即无法登录;③ 配置修改后服务热加载(无需重启) |
| 工作量 | 2 sprint |

#### 1.9 客户端打包与分发

| 项 | 内容 |
|---|---|
| 任务 | ① `electron-builder.yml` 配置(Win nsis + macOS dmg);② 代码签名(Windows 用 EV 证书,macOS 用 Developer ID + Notarization);③ 自动更新(`electron-updater` + GitHub Releases);④ 安装包 CDN 分发脚本 |
| 依赖 | 1.3-1.7 |
| 涉及文件 | `apps/desktop/electron-builder.yml`、`.github/workflows/release.yml` |
| 验收标准 | ① Windows 安装包在 Win10/Win11 干净环境可装可运行;② macOS 安装包通过 Notarization;③ 自动更新能从 v1.0.0 升级到 v1.0.1 |
| 工作量 | 1.5 sprint |
| 风险 | macOS Notarization 流程长,需提前申请 Apple Developer 账号 |

#### 1.10 一键部署验证

| 项 | 内容 |
|---|---|
| 任务 | ① 验证 `docker compose up` 在干净 Linux 主机上一键起服务;② 验证 nginx 反向代理 + HTTPS;③ 验证桌面客户端连接远程后端;④ 写 `docs/DEPLOY.md` 部署手册(含故障排查) |
| 依赖 | 0.2、0.5、1.9 |
| 涉及文件 | [docker-compose.yml](file:///e:/Officeagent/officeagent/docker-compose.yml)、`deploy/nginx/`、`docs/DEPLOY.md` |
| 验收标准 | ① 新人按文档 30 分钟内完成部署;② 客户端能连接远程后端并完成登录/对话/文件上传全流程 |
| 工作量 | 1 sprint |

**阶段 1 工作量小计**:约 14.5 sprint(按 2 周一 sprint,约 7 个月,可与阶段 0 并行启动部分前端工作)

---

### 阶段 2:企业级能力加固(P1,3-4 个月)

> **目标**:完善用户管理、运维监控、合规安全、系统集成,达到企业级可用标准。

#### 2.1 RBAC 细粒度权限 + 组织架构

| 项 | 内容 |
|---|---|
| 任务 | ① 数据模型:角色/权限/部门/职位 4 表;② 角色-权限多对多映射;③ 用户-角色多对多(一个用户可多角色);④ 后端 RBAC 中间件(装饰器风格 `@require_permission("document:read")`);⑤ 前端菜单/按钮级权限控制;⑥ 组织架构树形管理 UI |
| 依赖 | 阶段 1 完成 |
| 涉及文件 | [models/db/models.py](file:///e:/Officeagent/officeagent/src/officeagent/models/db/models.py)、新增 `core/security/rbac.py`、`api/routers/admin.py` |
| 验收标准 | ① 不同角色看到不同菜单;② 接口级权限拦截生效;③ 角色变更后用户权限实时刷新 |
| 工作量 | 2 sprint |

#### 2.2 LDAP/AD 域集成

| 项 | 内容 |
|---|---|
| 任务 | ① `ldap3` 库集成;② LDAP 服务器配置 UI;③ 用户登录时同步 LDAP 用户到本地;④ LDAP 用户与本地用户映射(按邮箱);⑤ 定时同步 LDAP 组织架构 |
| 依赖 | 2.1 |
| 涉及文件 | 新增 `core/auth/ldap.py`、`api/routers/admin.py` |
| 验收标准 | ① 配置企业 LDAP 后,域账号可直接登录;② LDAP 用户变更后 24h 内同步 |
| 工作量 | 1.5 sprint |

#### 2.3 SSO 单点登录(OAuth2.0/SAML)

| 项 | 内容 |
|---|---|
| 任务 | ① OAuth2.0 Client(GitHub/Google/企业 IdP);② SAML 2.0 SP(对接 Azure AD/Okta);③ SSO 登录入口 UI;④ SSO 用户与本地用户绑定 |
| 依赖 | 2.1 |
| 涉及文件 | 新增 `core/auth/oauth.py`、`core/auth/saml.py` |
| 验收标准 | ① GitHub OAuth 登录成功;② SAML IdP 发起的登录成功 |
| 工作量 | 2 sprint |

#### 2.4 多因素认证 MFA

| 项 | 内容 |
|---|---|
| 任务 | ① TOTP(Google Authenticator 兼容);② 短信验证码(对接阿里云/腾讯云);③ 邮箱验证码(SMTP);④ MFA 强制策略(管理员可配置哪些角色必须开 MFA);⑤ 备用恢复码 |
| 依赖 | 2.1 |
| 涉及文件 | 新增 `core/auth/mfa.py` |
| 验收标准 | ① 开启 MFA 后,密码登录后需输入 TOTP;② 备用码可用且一次性 |
| 工作量 | 1.5 sprint |

#### 2.5 全量审计日志

| 项 | 内容 |
|---|---|
| 任务 | ① 独立审计日志库(避免与业务库混用,可用 Elasticsearch 或独立 PostgreSQL schema);② 敏感操作自动埋点(登录/权限变更/数据导出/删除);③ 审计日志查询 UI(按时间/用户/操作类型/IP 筛选);④ 日志导出(JSON/CSV);⑤ 日志防篡改(WORM 存储或哈希链) |
| 依赖 | 2.1 |
| 涉及文件 | 新增 `core/audit/` 子包、`api/routers/audit.py` |
| 验收标准 | ① 任意敏感操作 1s 内可查;② 日志无法被管理员篡改;③ 可导出最近 90 天日志 |
| 工作量 | 2 sprint |

#### 2.6 全平台客户端 + 代码签名

| 项 | 内容 |
|---|---|
| 任务 | ① Linux 安装包(AppImage + deb + rpm);② 自动更新支持 Linux;③ Windows EV 代码签名;④ macOS Notarization 自动化 |
| 依赖 | 1.9 |
| 涉及文件 | `apps/desktop/electron-builder.yml`、`.github/workflows/release.yml` |
| 验收标准 | ① Ubuntu 22.04 可安装 AppImage;② Windows SmartScreen 不拦截;③ macOS Gatekeeper 不拦截 |
| 工作量 | 1 sprint |

#### 2.7 Kubernetes Helm Charts

| 项 | 内容 |
|---|---|
| 任务 | ① `deploy/helm/officeagent/` Chart;② Values 可配置镜像/副本数/存储/PVC/Ingress;③ Secret 管理(对接 Sealed Secrets 或外部密钥管理);④ StatefulSet 用于 PostgreSQL/Redis(或对接云托管);⑤ HPA 自动扩缩容 |
| 依赖 | 0.2 |
| 涉及文件 | `deploy/helm/`(新增) |
| 验收标准 | ① `helm install officeagent ./deploy/helm/officeagent` 在 KIND 集群可起;② `kubectl scale` 后 Pod 正常扩缩 |
| 工作量 | 2 sprint |

#### 2.8 Terraform 基础设施

| 项 | 内容 |
|---|---|
| 任务 | ① AWS/Aliyun 模块(VPC + EKS/RKE + RDS + ElastiCache + S3/OSS + CloudFront/CDN);② 状态后端配置(S3 + DynamoDB 锁);③ 多环境(dev/staging/prod)隔离 |
| 依赖 | 2.7 |
| 涉及文件 | `deploy/terraform/`(新增) |
| 验收标准 | ① `terraform apply` 在干净 AWS 账号可起完整环境;② `terraform destroy` 可完全清理 |
| 工作量 | 2 sprint |

#### 2.9 备份与容灾

| 项 | 内容 |
|---|---|
| 任务 | ① PostgreSQL 定时全量 + WAL 增量备份;② Redis RDB + AOF;③ Milvus/MinIO 数据备份;④ 异地备份(跨可用区/跨区域);⑤ 一键恢复工具 + 恢复演练手册 |
| 依赖 | 2.7 |
| 涉及文件 | `deploy/scripts/backup.sh`、`deploy/scripts/restore.sh` |
| 验收标准 | ① 每日备份自动执行;② 恢复演练 RTO < 1h、RPO < 15min |
| 工作量 | 1.5 sprint |

#### 2.10 全链路监控运维

| 项 | 内容 |
|---|---|
| 任务 | ① 业务监控:用户活跃度/功能使用率统计大盘;② 系统监控:CPU/内存/磁盘/网络/QPS/延迟/P99;③ 应用监控:LangGraph 节点耗时/飞轮触发次数/拓扑增长;④ 安全监控:异常登录/高危操作/限流触发;⑤ 告警规则(分级:info/warning/critical);⑥ 自动扩缩容(基于 CPU/QPS) |
| 依赖 | 2.7 |
| 涉及文件 | `deploy/observability/`(新增 prometheus.yml / grafana dashboards / alertmanager rules) |
| 验收标准 | ① Grafana 大盘可查看全链路指标;② 告警 5min 内触达 oncall;③ HPA 生效 |
| 工作量 | 2 sprint |

#### 2.11 内容合规审核

| 项 | 内容 |
|---|---|
| 任务 | ① 输入审核:敏感词(已有 [sensitive_words.yaml](file:///e:/Officeagent/officeagent/config/security/sensitive_words.yaml))+ AI 二次审核;② 输出审核:LLM 输出内容审核(色情/暴力/政治);③ 审核服务独立部署(避免影响主链路性能);④ 审核日志可追溯 |
| 依赖 | 阶段 1 |
| 涉及文件 | [core/security/moderation.py](file:///e:/Officeagent/officeagent/src/officeagent/core/security/moderation.py)(已有,需增强)、新增 `services/moderation_service.py` |
| 验收标准 | ① 违规输入 100ms 内拦截;② 违规输出不上屏;③ 审核日志可查 |
| 工作量 | 1.5 sprint |

#### 2.12 数据本地化与隐私合规

| 项 | 内容 |
|---|---|
| 任务 | ① 数据不出域(私有部署所有数据本地存储);② 用户隐私中心(查看/导出/删除个人数据);③ 账号注销(软删除 + 30 天硬删除);④ 数据脱敏(日志/审计中手机号/身份证脱敏) |
| 依赖 | 2.5 |
| 涉及文件 | 新增 `api/routers/privacy.py`、[core/security/desensitize.py](file:///e:/Officeagent/officeagent/src/officeagent/core/security/desensitize.py)(已有,需应用到全链路日志) |
| 验收标准 | ① 用户可一键导出全部个人数据(JSON);② 注销后 30 天数据彻底删除;③ 日志中无明文敏感信息 |
| 工作量 | 1.5 sprint |

#### 2.13 等保/SOC2 合规筹备

| 项 | 内容 |
|---|---|
| 任务 | ① 等保三级定级/备案/整改/测评;② SOC2 Type II 审计准备;③ 安全开发流程落地(SDL);④ 漏洞管理(定期 pentest + 修复跟踪) |
| 依赖 | 2.5、2.10、2.11、2.12 |
| 涉及文件 | `docs/compliance/`(新增) |
| 验收标准 | ① 通过等保三级测评;② SOC2 审计无重大发现 |
| 工作量 | 持续(非 Sprint 化) |

#### 2.14 Office 365/WPS 插件

| 项 | 内容 |
|---|---|
| 任务 | ① Office Add-in(基于 Office.js,支持 Word/Excel/PPT);② WPS 加载项(基于 WPS 开放平台);③ 插件内调用 Agent 能力(通过 Webhook 对接后端);④ 插件市场发布 |
| 依赖 | 阶段 1 |
| 涉及文件 | `apps/office-addin/`(新增)、`apps/wps-addon/`(新增) |
| 验收标准 | ① Word 内可呼出 Agent 面板;② 选中文本可直接发送给 Agent;③ Agent 返回结果可插入文档 |
| 工作量 | 3 sprint |

#### 2.15 企业 IM 内嵌应用

| 项 | 内容 |
|---|---|
| 任务 | ① 企业微信自建应用;② 钉钉企业内部应用;③ 飞书机器人;④ IM 内 @机器人 触发 Agent;⑤ 消息回调安全校验 |
| 依赖 | 阶段 1 |
| 涉及文件 | 新增 `core/integration/wecom.py`、`core/integration/dingtalk.py`、`core/integration/feishu.py` |
| 验收标准 | ① 企业微信群内 @机器人 可触发 Agent;② 回调签名校验通过 |
| 工作量 | 2 sprint |

#### 2.16 Webhook 回调接口

| 项 | 内容 |
|---|---|
| 任务 | ① 通用 Webhook 接收端点;② Webhook 签名校验(HMAC-SHA256);③ Webhook 配置 UI(URL/Secret/事件类型);④ 失败重试(指数退避,最多 5 次) |
| 依赖 | 阶段 1 |
| 涉及文件 | 新增 `api/routers/webhook.py`、`core/integration/webhook.py` |
| 验收标准 | ① 第三方系统可注册 Webhook;② 事件触发后 5s 内推送;③ 失败自动重试 |
| 工作量 | 1 sprint |

**阶段 2 工作量小计**:约 28 sprint(约 14 个月,可选择性并行)

---

### 阶段 3:架构升级与生态扩展(P2,6 个月+)

> **目标**:架构解耦、多端覆盖、性能升级、国际化支持。

#### 3.1 微服务架构升级

| 项 | 内容 |
|---|---|
| 任务 | ① 拆分用户中心/Agent 调度中心/文件处理服务;② 服务间 gRPC 通信;③ 数据库按服务拆分(每服务独立库);④ 分布式事务(Saga 模式) |
| 依赖 | 阶段 2 完成 |
| 涉及文件 | 全架构重构 |
| 验收标准 | ① 单服务故障不影响其他服务;② 服务可独立部署 |
| 工作量 | 5 sprint |

#### 3.2 消息队列 + 异步任务

| 项 | 内容 |
|---|---|
| 任务 | ① Kafka 或 RabbitMQ 接入;② 长任务(文档转换/批量检索)走异步;③ ACK 机制保障一致性;④ 任务状态查询接口 |
| 依赖 | 3.1 |
| 涉及文件 | 新增 `core/messaging/` |
| 验收标准 | ① 10 万级文档转换不阻塞主链路;② 消息丢失率 < 0.01% |
| 工作量 | 2 sprint |

#### 3.3 API 网关

| 项 | 内容 |
|---|---|
| 任务 | ① Kong 或 APISIX 部署;② 统一鉴权/限流/日志;③ 灰度发布(基于 Header/IP);④ API 编排(聚合多个微服务) |
| 依赖 | 3.1 |
| 涉及文件 | `deploy/gateway/`(新增) |
| 验收标准 | ① 限流生效;② 灰度路由正确 |
| 工作量 | 2 sprint |

#### 3.4 服务网格(Istio)

| 项 | 内容 |
|---|---|
| 任务 | ① Istio 注入;② 流量管控(金丝雀/蓝绿);③ 熔断降级;④ 链路追踪(Jaeger) |
| 依赖 | 3.1 |
| 涉及文件 | `deploy/istio/`(新增) |
| 验收标准 | ① 金丝雀发布 5% 流量;② 熔断器生效 |
| 工作量 | 2 sprint |

#### 3.5 多语言 SDK

| 项 | 内容 |
|---|---|
| 任务 | ① Python SDK(已有,封装为 pip 包);② JavaScript/TypeScript SDK(已有 `packages/sdk`,发布到 npm);③ Java SDK(OpenAPI Generator);④ Go SDK(OpenAPI Generator) |
| 依赖 | 阶段 1 |
| 涉及文件 | `sdks/python/`、`sdks/java/`、`sdks/go/` |
| 验收标准 | ① 4 语言 SDK 均通过集成测试;② 文档完整 |
| 工作量 | 2 sprint |

#### 3.6 开发者开放平台

| 项 | 内容 |
|---|---|
| 任务 | ① 应用注册/UI;② 密钥管理;③ 示例代码;④ 在线 API 调试器(Swagger UI);⑤ 配额与限流 |
| 依赖 | 3.5 |
| 涉及文件 | `apps/developer-portal/`(新增) |
| 验收标准 | ① 开发者可自助注册应用;② API 调试器可在线测试 |
| 工作量 | 2 sprint |

#### 3.7 小程序 + H5 适配

| 项 | 内容 |
|---|---|
| 任务 | ① 微信小程序(Taro 或原生);② 移动端 H5(响应式);③ 核心功能(对话/文档查看)移动端可用 |
| 依赖 | 阶段 1 |
| 涉及文件 | `apps/miniprogram/`、`apps/mobile-h5/` |
| 验收标准 | ① 小程序可发布;② H5 在 iOS/Android 浏览器正常 |
| 工作量 | 3 sprint |

#### 3.8 国际化 i18n

| 项 | 内容 |
|---|---|
| 任务 | ① 前端 i18n 架构(react-i18next);② 中/英/日/韩 4 语言;③ 后端多语言(错误消息/邮件模板);④ 各区域数据法规适配(GDPR/CCPA) |
| 依赖 | 阶段 1 |
| 涉及文件 | `packages/ui/locales/`、后端 `core/i18n/` |
| 验收标准 | ① 切换语言后全 UI 翻译;② 后端错误消息按 Accept-Language 返回 |
| 工作量 | 2 sprint |

#### 3.9 高可用与性能优化

| 项 | 内容 |
|---|---|
| 任务 | ① 多可用区部署(99.99% SLA);② CQRS 读写分离;③ CDC 变更数据捕获(Debezium);④ CDN 静态资源加速;⑤ 离线模式(断网基础文档功能可用) |
| 依赖 | 3.1 |
| 涉及文件 | 全架构 |
| 验收标准 | ① 单可用区故障不影响服务;② 读 QPS 提升 5x;③ 断网后可编辑本地文档 |
| 工作量 | 3 sprint |

**阶段 3 工作量小计**:约 23 sprint(约 12 个月,长期演进)

---

## 三、执行原则

1. **安全基线前置**:所有新功能必须先满足统一安全规范,鉴权、加密、审计逻辑优先于业务功能开发。Phase 0.4(安全规范对齐)是 Phase 1.7(登录页面)的硬依赖。

2. **复用最大化**:桌面端、管理后台、多端适配共用 `packages/ui` 与 `packages/sdk`,减少重复开发。后端业务逻辑一次性写好,前端只做交互。

3. **渐进式迭代**:
   - Phase 0 修后端地基(2-3 周)
   - Phase 1 跑通核心闭环(1-2 个月)
   - Phase 2 加固企业级能力(3-4 个月,可选择性落地)
   - Phase 3 架构升级(6+ 个月,按需启动)
   - 避免早期过度设计,Phase 3 仅在 Phase 2 出现瓶颈时启动。

4. **质量优先**:核心链路必须经过压测与安全校验,稳定性优先于新功能上线。每个 Sprint 必须包含:
   - 单元测试覆盖率 ≥ 80%
   - 集成测试覆盖核心链路
   - 安全扫描(Bandit/Semgrep)零 critical
   - 性能回归(关键接口 P99 < 500ms)

5. **文档同步**:每个任务交付时必须同步更新:
   - `DEVELOPMENT.md`(模块说明/API/部署)
   - `ARCHITECTURE.md`(架构决策)
   - `docs/DEPLOY.md`(部署手册)
   - API 端点的 OpenAPI 注释

---

## 四、优先级矩阵(快速决策)

| 任务 | 优先级 | 阻塞 | 工作量 |
|---|---|---|---|
| 0.1 Day 7 集成收尾 | P0 | 无 | 0.5 |
| 0.2 Docker 修复 | P0 | 无 | 1 |
| 0.3 数据库迁移 | P0 | 0.2 | 1 |
| 0.4 安全规范对齐 | P0 | 0.3 | 2 |
| 0.5 nginx 配置 | P0 | 0.2 | 0.5 |
| 0.6 CI/CD 基础 | P0 | 0.2、0.3 | 1 |
| 0.7 配置文件补全 | P0 | 无 | 0.5 |
| 0.8 持久化存储层 | P0 | 0.3 | 1.5 |
| 1.1 前端脚手架 | P0 | 阶段 0 | 1 |
| 1.2 OpenAPI SDK | P0 | 1.1 | 0.5 |
| 1.3 Electron 壳 | P0 | 1.1 | 1.5 |
| 1.4 三栏布局 | P0 | 1.3 | 2 |
| 1.5 Monaco 编辑器 | P0 | 1.4 | 1 |
| 1.6 AI 对话面板 | P0 | 1.4、阶段 0 | 2 |
| 1.7 登录鉴权页 | P0 | 0.4、1.3 | 1.5 |
| 1.8 管理后台 | P0 | 0.4、1.1 | 2 |
| 1.9 客户端打包 | P0 | 1.3-1.7 | 1.5 |
| 1.10 一键部署验证 | P0 | 0.2、0.5、1.9 | 1 |
| 2.1 RBAC | P1 | 阶段 1 | 2 |
| 2.2 LDAP/AD | P1 | 2.1 | 1.5 |
| 2.3 SSO | P1 | 2.1 | 2 |
| 2.4 MFA | P1 | 2.1 | 1.5 |
| 2.5 审计日志 | P1 | 2.1 | 2 |
| 2.6 全平台客户端 | P1 | 1.9 | 1 |
| 2.7 Helm Charts | P1 | 0.2 | 2 |
| 2.8 Terraform | P1 | 2.7 | 2 |
| 2.9 备份容灾 | P1 | 2.7 | 1.5 |
| 2.10 监控运维 | P1 | 2.7 | 2 |
| 2.11 内容合规 | P1 | 阶段 1 | 1.5 |
| 2.12 数据本地化 | P1 | 2.5 | 1.5 |
| 2.13 等保/SOC2 | P1 | 2.5、2.10、2.11、2.12 | 持续 |
| 2.14 Office 插件 | P1 | 阶段 1 | 3 |
| 2.15 企业 IM | P1 | 阶段 1 | 2 |
| 2.16 Webhook | P1 | 阶段 1 | 1 |
| 3.x 阶段三全部 | P2 | 阶段 2 | 23 |

---

## 五、与现有 SELF_EVOLUTION_AGENT_PLAN 的关系

| SELF_EVOLUTION_AGENT_PLAN | 本计划 |
|---|---|
| Day 1-7 自进化 Agent 后端 | **已完成**,作为阶段 0 的基础 |
| 第十部分·留存资产(topology/traces/snapshots 数据目录) | 阶段 0.7 落地 |
| Day 7·services/service.py 改写为 build_graph | 阶段 0.1 收尾 |
| 第八部分·代码复用清单 | 阶段 0.8(存储层)+ 阶段 1(前端复用 packages/) |

本计划是 SELF_EVOLUTION_AGENT_PLAN 的**横向扩展**(从后端扩展到前端/客户端/部署/合规),不替代原计划的后端深度设计。

---

## 六、风险登记簿

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| Argon2id 参数不当导致登录延迟 | 中 | 高 | 压测选定参数,生产环境可调 |
| Electron 跨平台兼容性问题(尤其 macOS Notarization) | 高 | 中 | 提前申请 Apple Developer 账号,CI 自动化签名 |
| Milvus 在生产环境稳定性 | 中 | 高 | 可选降级为 pgvector,Phase 2 评估 |
| LangGraph 在高并发下性能瓶颈 | 中 | 高 | Phase 3 拆分微服务时优先拆 Agent 调度 |
| 前端零基础团队学习曲线 | 高 | 中 | 选 shadcn/ui(源码可读)+ 严格 TypeScript |
| 数据库迁移与现有内存 Store 数据兼容 | 低 | 中 | Phase 0.8 提供数据迁移脚本 |
| 等保/SOC2 测评周期长 | 高 | 中 | Phase 2 早期启动,与开发并行 |

---

**计划版本**:v2.0  
**生成时间**:2026-07-04  
**基线扫描**:779 测试通过 / 后端 12 子模块全部就位 / 前端零基础  
**下一步**:启动 Phase 0.1(Day 7 集成收尾)+ Phase 0.2(Docker 修复)并行
