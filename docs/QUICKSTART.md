# FnixAgent 快速开始

> **无需域名、无需云服务器、无需 Docker。**
> **BYOK**：LLM API Key 在 Desktop **设置 → AI** 填写，保存在本机。

---

## 方式 1：下载安装包

见 [INSTALL.md](./INSTALL.md#方式-a下载安装包推荐最终用户)

---

## 方式 2：从源码（5 分钟）

### 环境

| 工具 | 版本 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+ |
| pnpm | 9+ |
| Rust | stable（Tauri） |

### 安装

```bash
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent
cp .env.example .env

# Windows: powershell -ExecutionPolicy Bypass -File install.ps1
# macOS/Linux: ./install.sh
```

### 启动

```bash
pnpm dev:all
```

---

## 首次使用

1. 打开 Desktop（无登录步骤）
2. **设置 → AI** → 选择提供商 + 填写 **API Key**
3. 打开本地文件夹（工作区）
4. **Work** — 描述办公任务
5. **Code** — Agent 改代码，Diff 后 Accept

架构：`docs/ARCHITECTURE_LOCAL_HARNESS.md`

---

## 常用命令

| 命令 | 说明 |
|------|------|
| `pnpm dev:all` | Tauri + API + fnix-local |
| `pnpm verify:beta` | 发布前验收 |
| `pnpm clean:cache` | 清理 C 盘  sandbox 等缓存 |
| `pnpm build` | 打安装包 |

---

## 磁盘空间

若 C 盘被占满：

```bash
pnpm clean:cache
pnpm clean:cache:aggressive
```

主要占用：`%TEMP%\cursor-sandbox-cache`（ Agent 编译缓存，可安全删除）
