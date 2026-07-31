# Fnix Harness — 开源用户使用方案（冻结设计）

> **原则**：普通用户 **零编译**；开发者 **一条命令**；贡献者 **可验证**。  
> **产品主设计** → [FNIX_PRODUCT.md](./FNIX_PRODUCT.md)（学 Cursor/Trae/Codex/Hermes，落实 Fnix 自己的 Work/Code）。  
> 参考对照（非需求清单）→ [HERMES_ALIGNMENT.md](./HERMES_ALIGNMENT.md)

---

## 1. 三类用户，三条路径

```text
                    ┌─────────────────────────────────────┐
                    │         GitHub: FnixAgent            │
                    └─────────────────────────────────────┘
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
   【A】最终用户                  【B】开发者                    【C】贡献者
   只想用工具                    改 UI / 接 API                 提 PR
          │                           │                           │
          ▼                           ▼                           ▼
   Releases 安装包              git clone + pnpm setup          clone + doctor + test
   无 Rust/Python              pnpm dev（三进程）               verify:beta + check:plan
```

| 角色 | 占比（目标） | 入口 | 需要安装 |
|------|-------------|------|----------|
| **A 最终用户** | ~90% | [GitHub Releases](https://github.com/Liuyifeidashuaibi/FnixAgent/releases) | 无（安装包内置 Python sidecar） |
| **B 开发者** | ~8% | `git clone` + `pnpm setup` + `pnpm dev` | Python 3.11、Node 18、pnpm、Rust（仅编译 Tauri 壳） |
| **C 贡献者** | ~2% | Fork + `pnpm doctor` + `pnpm verify:beta` | 同 B + 测试环境 |

**绝不要求**最终用户：clone 仓库、装 Rust、改 `.env`、了解 fnix-local / agentd 端口。

---

## 2. 路径 A：最终用户（主路径 · 必须优先做好）

### 2.1 体验流程（5 步）

```text
下载安装包 → 打开 Fnix → 首次引导填 API Key → 选工作区文件夹 → Work / Code
```

1. **Download** — GitHub Release 对应平台（Windows `.exe` / macOS `.dmg` / Linux `.deb`）
2. **Install** — 标准安装向导，无额外依赖
3. **BYOK** — 首次引导或 **设置 → AI** → 选提供商 + Key（OpenAI / Qwen / DeepSeek / GLM / 自定义 Base URL）
4. **Workspace** — 选一个本地文件夹；自动创建 `{workspace}/.fnix`
5. **Run** — Work（办公交付）或 Code（Diff 审阅后写盘）

### 2.2 安装包内嵌什么（Standalone 冻结）

```text
Fnix.app / Fnix.exe
  ├── Tauri UI（WebView）
  ├── 内嵌 Python agentd（:8000，仅本机）
  ├── fnix-local sidecar（:8710，Python 或 Rust 二进制）
  └── 配置 ~/.fnix（sessions / config）
```

- **LLM**：100% BYOK，Key 存本机（Settings / OS Keychain），不上传服务端
- **网络**：默认仅 `127.0.0.1`，无云依赖
- **账号**：**无** — 开源 Desktop 无需注册/登录（对标 Hermes 自托管）；`standalone` profile 下 API 网关对本机匿名放行

### 2.3 发布责任（维护者）

| 动作 | 命令 / 触发 |
|------|------------|
| 打 tag | `git tag v1.0.0-beta.1 && git push origin v1.0.0-beta.1` |
| CI 构建 | `.github/workflows/release.yml`（三平台矩阵） |
| 产物 | NSIS / DMG / deb+AppImage |
| Release Notes | 安装步骤 + BYOK 说明 + 已知限制 |

**当前缺口**：Release 尚未发布首个 tag → README Download 链接暂时空。维护者需优先打 `v1.0.0-beta.1`。

---

## 3. 路径 B：从源码运行（开发者）

### 3.1 前置条件（按平台）

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | agentd |
| Node.js | 18+ | UI 构建 |
| pnpm | 9+ | monorepo |
| Rust stable | Tauri 壳 | 仅 `pnpm dev` 时需要 |
| **Windows 额外** | [VS Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) + WebView2 | Tauri 链接（MSVC） |

> Windows 上 **GNU MinGW 工具链不可靠**（大 DLL 链接失败 + 易与 FnixAi `CARGO_TARGET_DIR` 冲突）。
> 开源文档必须写清：**Windows 源码编译需要 MSVC**，或直接用 Release 安装包。

### 3.2 标准命令（冻结为 4 个）

```bash
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent

pnpm setup      # 安装 Python + Node 依赖，复制 .env.example
pnpm doctor     # 检查环境是否就绪（端口、工具链、WebView2）
pnpm dev        # 启动 fnix-local + agentd + Tauri Desktop（三进程）
pnpm clean:cache  # C 盘 / Cursor sandbox 缓存满时
```

**不要**再暴露：`dev:all:tauri`、`dev:electron`、FnixAi 姊妹仓路径给普通开发者。

### 3.3 架构（开发者需知）

```text
Tauri UI (:5175 dev / 窗口 prod)
    ↕ HTTP 127.0.0.1:8000
Python agentd（KTG/STP/MFP、Work/Code 大脑）
    ↕ HTTP 127.0.0.1:8710
fnix-local（索引 / 沙箱；离线时 Python fallback）
    ↘ ~/.fnix + {workspace}/.fnix
```

- API Key：**在 Desktop Settings 填**，不必写进 `.env`（除非 headless 调试）
- `.env`：仅 `JWT_SECRET_KEY`、`FNIXAGENT_PROFILE=standalone` 等后端配置

---

## 4. 路径 C：贡献者

```bash
pnpm setup
pnpm doctor          # 必须全绿
pnpm verify:beta     # pytest + typecheck + cargo check + e2e
pnpm check:plan      # Mega Plan 验收
# 改代码 → PR → CI 绿
```

PR 要求见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

---

## 5. 产品边界（开源版不做什么）

| 不做 | 原因 |
|------|------|
| 托管 LLM / 代付 Key | BYOK 产品策略 |
| Electron 壳 | 已废弃，仅 Tauri |
| 要求 Docker / PG / Redis | Standalone 零依赖 |
| 要求 clone FnixAi | 姊妹仓可选，非用户路径 |
| Web 版主产品 | Desktop Harness 为主 |

---

## 6. 维护者待办（按优先级）

### P0 — 用户能装上

- [ ] 发布 `v1.0.0-beta.1` GitHub Release（三平台安装包）
- [ ] `pnpm doctor` 脚本 + README 指向
- [ ] Windows：Release 用 CI MSVC 构建；文档写清源码编译需 VS Build Tools
- [ ] 修复 `.cargo/config.toml`：仅隔离 `target-dir`，不强制 MSVC（CI 跨平台）

### P1 — 开发者体验

- [ ] 统一 `pnpm setup`（合并 install.ps1/sh）
- [ ] 所有 cargo 调用走 `tauri-cargo-env`（防 FnixAi target 污染）
- [ ] `verify:beta` 去掉 Electron typecheck
- [ ] bundle 脚本只写 `desktop-tauri/resources`

### P2 — 增长

- [ ] Demo GIF + 官网/README 首屏
- [ ] Issue 模板 + Discussions「用法问答」
- [ ] 可选：`pip install fnixagent` headless 模式文档

---

## 7. 用户常见问题（FAQ 设计）

**Q: 需要登录吗？**  
A: **不需要。** 开源 Desktop 对标 Hermes：下载打开即用；数据在 `~/.fnix`，无云账号。

**Q: 必须填 API Key 吗？**  
A: 是。Fnix 仅 BYOK，Key 保存在本机。

**Q: 必须装 Python/Rust 吗？**  
A: 用 Release 安装包 **不需要**。只有从源码 `pnpm dev` 才需要。

**Q: Windows 编译失败 link.exe not found？**  
A: 安装 [VS Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)（「使用 C++ 的桌面开发」），或直接用 Release 安装包。

**Q: C 盘满了？**  
A: `pnpm clean:cache`（Cursor sandbox 缓存可达 60GB+）。

**Q: fnix-local 离线？**  
A: Work/Code 仍可用 Python fallback，索引功能降级。

---

## 8. 与 Hermes / OpenHarness 对齐点

| Hermes Agent | Fnix Harness |
|--------------|--------------|
| 下载即用，无云账号 | ✅ 无 LoginPage，首次引导 BYOK |
| BYOK 多提供商 | ✅ Settings AI 预设 |
| 本地 `~/.hermes` 数据 | ✅ `~/.fnix` + `{workspace}/.fnix` |
| Desktop + CLI 同源配置 | 🟡 Desktop 为主；CLI `fnixagent` 可选 |
| Release 安装包 | 🟡 CI 已有，待首 tag |

| OpenHarness | Fnix Harness |
|-------------|--------------|
| 本地 Agent 工作台 | ✅ Tauri + agentd |
| 自带 API Key | ✅ Settings BYOK |
| 工作区文件夹 | ✅ Workspace First |
| Release 安装包 | 🟡 CI 已有，待首 tag |
| 一条命令 dev | 🟡 `pnpm dev` 目标，待 setup/doctor |

**差异化**：Work（办公交付）+ Code（Diff Accept）+ KTG/STP/MFP 自进化内核。
