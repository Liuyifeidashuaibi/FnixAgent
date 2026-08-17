# Fnix Harness — 安装与运行指南

> **产品定位**：本地优先的 AI Harness 工作台（对标 [Hermes Agent](https://github.com/NousResearch/hermes-agent) / OpenHarness），Work 办公 + Code 编程，**无账号、仅 BYOK**。

---

## 方式 A：下载安装包（推荐最终用户）

1. 打开 [GitHub Releases](https://github.com/Liuyifeidashuaibi/FnixAgent/releases)
2. 下载对应平台的安装包：
   - **Windows**：`.exe` (NSIS)
   - **macOS**：`.dmg`
   - **Linux**：`.deb` 或 AppImage
3. 安装并启动 Fnix Desktop（**无需登录**）
4. 首次引导或 **设置 → AI** → 填写您自己的 API Key（OpenAI / Qwen / DeepSeek / GLM / 兼容端点）
5. 选择本地工作区文件夹 → 开始使用 Work 或 Code

> Desktop 不会使用服务端 LLM Key；Key 保存在本机。

---

## 方式 B：从源码运行（开发者 / 贡献者）

### 前置条件

| 工具 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| pnpm | 9+ |
| Rust | stable（Tauri，[安装指引](https://v2.tauri.app/start/prerequisites/)） |

### 一键安装

**Windows**

```powershell
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent
powershell -ExecutionPolicy Bypass -File install.ps1
```

**macOS / Linux**

```bash
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent
chmod +x install.sh && ./install.sh
```

### 启动

```bash
pnpm dev:all          # Tauri + agentd:8003 + fnix-local:8710
# 或
pnpm dev              # 仅 Tauri（Standalone 自动 spawn 后端）
```

浏览器/API 健康检查：`http://127.0.0.1:8003/health`

### 首次使用

1. **首次引导**：配置 API Key → 选择工作区 → 选择 Work / Code
2. **Work**：描述办公任务，产出 docx/xlsx 等
3. **Code**：Agent 改代码，Diff 预览后 Accept 写盘

---

## 环境变量（`.env`）

从源码运行时复制模板：

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `FNIXAGENT_PROFILE=standalone` | 零 Docker 本地模式（默认） |
| `FNIX_API_ONLY=1` | 后端强制 BYOK（默认开启） |
| `JWT_SECRET_KEY` | 本地 dev 可默认；**公开部署务必修改** |
| `FNIX_LOCAL_URL` | sidecar 地址，默认 `http://127.0.0.1:8710` |

**Desktop 用户的 LLM Key 在应用内 Settings 填写**，不必写入 `.env`（除非 headless API 调试）。

---

## 磁盘空间

Cursor / Agent 编译可能在 **C:\Users\<you>\AppData\Local\Temp\cursor-sandbox-cache** 占用数十 GB。

```bash
node scripts/clean-dev-cache.mjs
# 深度清理（含 npm/pip/cargo + 3 天前 temp）
node scripts/clean-dev-cache.mjs --aggressive
```

Windows 也可定期运行：

```powershell
pnpm clean:cache
```

---

## 打包发布

```bash
pnpm prepare:release
pnpm build
# 产物: apps/desktop-tauri/src-tauri/target/release/bundle/
```

推送 tag 触发 CI：见 [`BETA_RELEASE.md`](./BETA_RELEASE.md)

---

## 架构

```
Desktop (Tauri 2)  →  agentd :8003  →  fnix-local :8710
        ↘ ~/.fnix + {workspace}/.fnix
```

详见 [`ARCHITECTURE_LOCAL_HARNESS.md`](./ARCHITECTURE_LOCAL_HARNESS.md)

---

## 故障排除

| 问题 | 处理 |
|------|------|
| C 盘满 | `pnpm clean:cache` |
| 后端离线 | `pnpm dev:api` 或检查 8003 端口（agentd 默认） |
| 无 LLM 响应 | Settings → AI 检查 API Key |
| fnix-local 离线 | Work/Code 仍可用 Python fallback；可选 `pnpm stack:sidecar` |

---

## 参与贡献

见 [CONTRIBUTING.md](../CONTRIBUTING.md) · [SECURITY.md](../SECURITY.md)
