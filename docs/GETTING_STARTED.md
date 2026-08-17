# Fnix Harness — 2 分钟上手（对标 Hermes）

> **无需账号 · 无需 Docker · BYOK 自带 API Key**

---

## 方式 A：下载安装包（推荐 · 像 Hermes Desktop 一样）

1. 打开 [GitHub Releases](https://github.com/Liuyifeidashuaibi/FnixAgent/releases)
2. 下载对应平台安装包（Windows `.exe` / macOS `.dmg` / Linux `.deb` 或 AppImage）
3. 安装并打开 **Fnix**
4. 首次引导：**选提供商 → 填 API Key → 测试连接 → 选文件夹**
5. 开始 **Work**（办公）或 **Code**（编程）

数据保存在本机：

- `~/.fnix` — 全局配置与会话
- `{你的工作区}/.fnix` — 项目 Harness 数据

---

## 方式 B：一条命令（开发者 · 像 `hermes` CLI 安装）

### Windows (PowerShell)

```powershell
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent
powershell -ExecutionPolicy Bypass -File install.ps1
pnpm dev
```

### macOS / Linux

```bash
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent
chmod +x install.sh && ./install.sh
pnpm dev
```

---

## 方式 C：CLI（可选 · 与 Desktop 共享 `~/.fnix`）

在 Desktop 设置里保存 API Key 后，CLI 会自动读取 `~/.fnix/secrets.json`：

```bash
fnixagent setup    # 初始化 ~/.fnix
fnixagent doctor   # 环境检查
fnixagent serve    # 启动 API（Desktop 会自动拉起，一般不必手动）
fnixagent chat     # 终端对话
```

---

## 与 Hermes 的相同点

| | Hermes | Fnix Harness |
|---|--------|--------------|
| 开源 MIT/Apache | ✅ | ✅ Apache-2.0 |
| 下载/安装即用 | ✅ | ✅ Release |
| 无云账号 | ✅ | ✅ |
| BYOK | ✅ | ✅ |
| 本地数据目录 | `~/.hermes` | `~/.fnix` |
| Setup 向导 | `hermes setup` | 首次引导 + Settings |
| Doctor | `hermes doctor` | `pnpm doctor` / `fnixagent doctor` |

## Fnix 差异化

- **Work** — 办公任务交付（docx/xlsx 等）
- **Code** — Diff 预览 → Accept 写盘
- **KTG/STP/MFP** — 自进化内核

---

## 验证安装

```bash
pnpm smoke:hermes    # 无登录 + harness API 冒烟
pnpm doctor          # 环境诊断
```

---

更多：[INSTALL.md](./INSTALL.md) · [HERMES_ALIGNMENT.md](./HERMES_ALIGNMENT.md) · [RELEASE_DESIGN.md](./RELEASE_DESIGN.md)
