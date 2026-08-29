# FnixAgent 界面驱动设计方案（完整版）

> 设计定稿：2026-08-28　|　本文档为合并终版（整合 V1 设计 + V2 对标刷新 + 三轮实施与审计实测），日期：2026-08-29
> 版本谱系：V1 原版归档于 `GUI_DRIVER_DESIGN_V1_ARCHIVE.md`；V2 增量文件 `GUI_DRIVER_DESIGN_V2.md`；实施逐轮记录见 `GUI_DRIVER_IMPL_REPORT.md`
> 前置文档：`GUI_DRIVER_ASSESSMENT.md`（评估与选型，含全部实测数据）
> **状态标记**：✅ 已实现并验证　🔶 部分实现/后续增强　⬜ 未实施（规划中）

---

## 0. 设计目标

让 FnixAgent 具备与 Codex、Trae、WorkBuddy、百度搭子同级的界面驱动能力：

1. **内置浏览器**：用户可见、可共驾的浏览器面板，AI 在其中自主操作；**搜索与浏览一律在软件内完成，绝不唤起系统浏览器**（2026-08-29 起升级为一级原则，详见 §2.1）
2. **接管已登录浏览器**：复用用户日常 Chrome/Edge 的登录态，不做"截图-点击"的笨循环
3. **不干扰用户**：AI 活动隔离在自己的 tab 组 / 后台进程，不抢用户的光标和窗口；软件最小化/失焦时任务照常执行（✅ 架构保证：Agent 循环在独立后端进程、内置浏览器为 headless 实例、桌面驱动走系统级注入）
4. **桌面操控**：操作原生应用（打开浏览器、打开 QQ、登录 QQ 等），作为浏览器能力的降级补充
5. **分级降级**：CDP 优先 → 隔离浏览器 → 系统桌面，逐级回退且过程对用户透明
6. **安全可控**：权限分级、高危确认、全程审计、页面内容不可信边界

---

## 1. 对标能力矩阵（2026-08-29 再调研刷新）

数据来源：Codex 官方发布（2026-04/05/06/07）、Trae 官方文档与社区、WorkBuddy 官方文档（月活 2000 万+）、百度搭子 AI Day（2026-07）、OpenClaw 文档（§8 已拆解）。

| 能力 | Codex | Trae | WorkBuddy | 百度搭子 | FnixAgent |
|---|---|---|---|---|---|
| 内置浏览器面板 | ✅ in-app browser（4 月）+ live 控制（6 月） | ✅ OpenPreview（保留登录态）+ agent-browser（独立实例）双轨 | ✅ Agent Browser skill | ✅ 桌面端内嵌浏览器（7 月上线） | ✅ 截图流面板 + 人机共驾（点击/滚轮转发） |
| 接管已登录会话 | ✅ Chrome 扩展（5 月） | ✅ OpenPreview 保留登录态 | ✅ BrowserSkill 直操已登录浏览器、数据不出本机 | ✅ 关键动作用户随时接手 | ✅ L1 `connect_over_cdp()`（🔶 引导弹层为后续项） |
| 隔离 tab 组，不垄断用户浏览器 | ✅ | — | ✅ 后台 tab、不抢窗口 | ✅ | ✅ L1 只开自己 `new_page()` 的 tab |
| 桌面操控（原生应用） | ✅ Mac/Windows computer use（**Windows 任务期间占用前台**） | ❌ | 🔶 本地执行能力驱动 Computer Use | ✅ "看见屏幕、操作软件" + 安全沙箱 | ✅ cua-driver EMBEDDED，**后台注入不抢焦点**（差异优势） |
| 搜索在软件内完成（内置搜索） | ✅ | ✅ 打开前强制弹框选浏览器 | ✅ | ✅ 内嵌浏览器内搜索/比价/填表 | ✅ 五道闸"内置浏览器优先"（本轮修复，比行业规则更彻底：默认内置） |
| 多 tab 并行任务 | ✅ | ✅ | ✅ | ✅ 连续打开多站 | ⬜ P4（会话页面池，见 §7） |
| 页面上圈选元素注释 | ✅ Comment Mode | ✅ 十字准星 | ❌ | ❌ | ⬜ P4（坐标换算链路已有基础） |
| 语义快照（a11y/uid/token） | ✅ CDP | ✅ Playwright | ✅ DOM/eval | — | 🔶 ARIA 树已返回；uid/token 契约列入后续 |
| 新站点/高危操作确认 | ✅ | — | — | ✅ 高危两端弹窗 | ✅ 高危每次确认 + L1 新域确认闸（本轮补齐） |
| 操作审计留痕 | ✅ | — | — | — | ✅ `driver_events.jsonl` 全量落盘（实测 29+ 事件） |
| 后台执行（锁屏/最小化不中断） | 🔶 background threads（云端） | — | 🔶 不抢窗口 | ✅ 云端浏览器锁屏不中断 | ✅ 后端独立进程 + headless + 系统级注入 |
| 跨端接力（手机遥控电脑） | — | — | 🔶 多平台集成 | ✅ 电脑手机接力、记忆上云 | ⬜ 观察项（远程 relay 另立项目，见 §7） |
| 三层动态切换 | ✅ 插件→扩展→内置 | ✅ | — | ✅ 智能路由/环境路由 | ✅ DriverRouter 分级路由 + 显式降级事件 |

**结论**：FnixAgent 的截图流浏览器面板是人机共驾的正确形态，行业已集体收敛到同一形态（百度搭子 7 月内嵌浏览器、Codex in-app browser）。经三轮实施，**真正缺过的三块（接管登录态 / 桌面操控 / 分级路由与安全层）已全部落地并实测**；剩余差距集中在 P4 级增强项（§7）。

---

## 2. 产品原则（含两条铁律 + 内置优先）

### 2.1 一级原则：内置浏览器优先（Built-in Browser First）

> **一切网页搜索与浏览默认在内置浏览器中完成；任何唤起系统默认浏览器的路径都是缺陷。**

背景：2026-08-29 用户实测发现"内置浏览器搜索网页，结果电脑自带的浏览器跳出来了"。定位到 3 条漏出路径并全部封堵，落地为五道闸：

| 闸 | 位置 | 行为 | 状态 |
|---|---|---|---|
| 1. 地址栏语义闸 | 前端 `toNavigableUrl` + 后端 `_normalize_url`（镜像契约） | 完整 URL 原样；域名补 `https://`；**本地主机（localhost/127.0.0.1/::1，含 host:port）补 `http://`**（本地开发服务通常无 TLS）；**搜索关键词（含空格/无域名后缀）→ 内置百度搜索**；危险协议检查前置 | ✅ 实测「北京天气」→《北京天气_百度搜索》；实测 `localhost:5175` 打开前端 |
| 2. 链接拦截闸 | `DesktopApp` 全局捕获阶段点击拦截 | `http(s)` 链接一律路由到内置浏览器面板（派发事件 + 自动切面板），下载链接除外 | ✅ |
| 3. 命令拦截闸 | `workspace.run_command` | `start/explorer/xdg-open/Start-Process/Invoke-Item/open + URL` 拦截，引导 `browser_act(action="goto")` | ✅ 17 组命令形态正反例覆盖 |
| 4. 模型引导闸 | `WORK_SYSTEM_PROMPT` 规则 12 | 搜索/浏览/操作页面用 `browser_view`（只读）与 `browser_act`（写，action=goto/click/type/…）；严禁 run_command start / desktop_launch 打开系统浏览器；操控原生应用才用 `desktop_*` | ✅ |
| 5. Tauri 壳兜底 | capabilities / webview 事件 | `shell:allow-open` 仅限本地产物文件；前端闸已覆盖外链，Rust 侧作为纵深防御 | 🔶 后续增强 |

### 2.2 两条铁律（来自 OpenClaw 的教训）

1. **降级是显式事件，不是静默行为**——切换驱动必须写入事件流并告知用户（前端徽标变化：`已接管 Chrome` 青 / `隔离沙箱` 灰 / `桌面操控` 琥珀）
2. **失败不逐动作回退**——L1 挂了就整体切 L2（连续 2 次失败触发，`_FAILURE_THRESHOLD=2`），不在同一个动作上反复横跳

---

## 3. 总体架构（已实现形态）

```
┌─────────────────────────────────────────────────────────────────┐
│  前端 workbench（StudioPanel 四视图：任务摘要/浏览器/桌面/终端）   │
│  BrowserView（截图流+人机共驾）│ DesktopPanel（截图流+确认闸）     │
│  确认弹层 │ 操作时间线 │ 全局链接拦截                              │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP 轮询 /api/v1/browser/*、/api/v1/desktop/*
┌──────────────▼──────────────────────────────────────────────────┐
│  FastAPI 后端（独立进程——最小化/失焦不影响执行）                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ DriverRouter（core/tools/driver_router.py）✅           │     │
│  │ · CDP 探测（9222/9223，2s）· 路由 · 降级 · 事件流 · 审计 │     │
│  └──────────┬─────────────────┬─────────────────┬─────────┘     │
│             ▼                 ▼                 ▼               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ L1 CDP 接管 ✅ │  │ L2 托管浏览器 ✅│  │ L3 桌面 cua-driver✅│    │
│  │ connect_over │  │ launch()      │  │ EMBEDDED, 12 工具   │    │
│  │ _cdp()       │  │ headless +    │  │ 经 relay 子进程可选  │    │
│  │ 只开自己 tab  │  │ storage_state │  │（FNIX_DESKTOP_MODE） │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│             │                 │                  │               │
│  ┌──────────▼─────────────────▼──────────────────▼─────────┐    │
│  │ computer.use syscall 执行器（kernel.py）✅ 已接通          │    │
│  │ 权限闸（COMPUTER 高危标记）→ 审计落盘 driver_events.jsonl  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.1 分层落地清单

| 层 | 模块 | 文件 | 状态 |
|---|---|---|---|
| 路由 | `DriverRouter` + `DriverEvent` | `core/tools/driver_router.py` | ✅ |
| L1 | `CdpBrowserDriver` | `core/tools/browser.py`（`_ensure()` 先探测后接管） | ✅ |
| L2 | `ManagedBrowserDriver` | 同上（`launch()` 路径保留） | ✅ |
| L3 | `DesktopDriver` | `core/tools/desktop.py`（12 个 `desktop_*` 工具） | ✅ |
| relay | `desktop_relay` 子进程 | `core/tools/desktop_relay.py`（stdout JSONL，失败自恢复） | ✅ |
| syscall | `computer.use` 执行器 | `core/agent/kernel.py::_handle_computer_use` | ✅（后台进程禁用为既定策略） |
| API | `/api/v1/desktop/*`（state/screen_size/apps/windows/action/confirm/events） | `api/routers/desktop.py` | ✅ |
| API | `/api/v1/browser/*`（含 events、navigate 支持 confirmation_id） | `api/routers/browser.py` | ✅ |

### 3.2 降级决策（DriverRouter）✅

```
请求到达（目标 URL 或应用名）
  │
  ├─ 目标是网页？
  │    ├─ 探测 9222/9223（GET /json/version, 2s 超时）
  │    │    ├─ 通 → L1 CDP 接管（复用登录态）
  │    │    └─ 不通 → L2 托管浏览器（引导开调试端口的弹层为后续增强）
  │    └─ L1 执行失败 ≥2 次 → 自动降 L2，事件流 driver_demote 显式告知
  │
  └─ 目标是原生应用/桌面？
       └─ L3 cua-driver（degraded 时回退截图+坐标模式，诚实标注）
```

---

## 4. 模块设计与实测状态

### 4.1 DriverRouter ✅

统一动作契约（三驱动共用，LLM 只见这一套）：`DriverAction{op, target, text, meta}` → `DriverResult{ok, summary, screenshot_b64, snapshot_text, error, degraded}`。
事件流 `DriverEvent` 全量落盘 `.fnix` 审计：`{id, ts, session, driver_mode, action, target, ok, degraded, error, confirmations}`，内存环形 200 条 + `~/.local/share/fnixagent/driver_events.jsonl`（实测 29+ 真实事件）。

### 4.2 L1：CdpBrowserDriver ✅

`_ensure()` 先探测后接管；行为约束（对标 Codex "No session hijacking"）：
- 只在自己 `new_page()` 出来的 tab 里操作，关闭会话时只关自己的 tab ✅
- `asyncio.Lock` 串行化 ✅
- **cookie 持久化仅在 L2 启用**——L1 登录态在用户浏览器里，不落盘不外传 ✅
- 连续 2 次失败显式降级 `cdp-attach→managed`（`driver_demote` 事件）✅
- **新域确认闸**（本轮补齐，§6.8）：接管的是用户真实浏览器，首访未批准域名需一次性确认；确认卡已接入 `BrowserView`（带令牌重试，与桌面确认卡同形态）

### 4.3 L2：ManagedBrowserDriver ✅

现有 `BrowserSession.launch()` 原样保留，8 个 `browser_*` 工具签名不变（click_text 兜底、降级重拍、协议白名单）。新增内置搜索语义：`_normalize_url` 把搜索关键词转为内置百度搜索。

### 4.4 L3：DesktopDriver ✅

cua-driver 0.22.2（MIT），EMBEDDED 模式零配置（无 daemon、无管理员权限要求）。12 个工具按权限分级：

| 工具 | 映射 cua-driver | 权限 |
|---|---|---|
| `desktop_state` / `desktop_apps` / `desktop_windows` / `desktop_screen_size` / `desktop_window_state` | get_desktop_state / list_apps / list_windows / get_screen_size / get_window_state | LOW |
| `desktop_click` / `desktop_type` / `desktop_hotkey` / `desktop_bring_front` / `desktop_set_value` / 坐标滚动 | click / type_text / hotkey / bring_to_front / set_value / scroll | MIDDLE |
| `desktop_launch` / `desktop_kill` | launch_app / kill_app | **HIGH（每次确认）** |

实测全链路（2026-08-29）：`launch notepad` → 确认闸（`需要用户确认`，发一次性令牌）→ 批准 → 重试动作消费令牌 → **真实启动（pid 31376）** → 窗口枚举命中「*新建 文本文档.txt - Notepad」→ 桌面截图留证 → 确认闸关闭。"打开浏览器 / 打开 QQ / 登录 QQ"走同一链路（中文输入走剪贴板粘贴路径）。

**剪贴板**：设计要求"默认禁用，白名单才开"——实际落地**零暴露**（12 工具不含 clipboard_read/write），比设计更彻底。

### 4.5 relay 子进程 ✅

`FNIX_DESKTOP_MODE=relay` 启用：主进程经 stdout JSONL 与 `desktop_relay.py` 子进程通信；子进程死亡自动重启下一次调用；收益为权限隔离（未来驱动提权进程时仅 relay 需管理员权限）、崩溃隔离、生命周期独立。P0-P2 默认 EMBEDDED 内嵌。

### 4.6 computer.use 执行器 ✅

`kernel.py::_handle_computer_use` 已从空壳接入 DriverRouter（解析 → 路由 → 审计）。权限闸复用既有 `SyscallCategory.COMPUTER` 高危标记 + scope；后台进程禁止 computer.use 为既定安全策略。

---

## 5. 安全模型（四项全部落地）

### 5.1 动作分级 ✅

| 级别 | 动作 | 策略 |
|---|---|---|
| 只读 | snapshot / screenshot / read / list_* | 直接放行 |
| 常规 | navigate / click / type / scroll / set_value | 首次确认，会话内记住（桌面面板坐标点击有就地确认弹层防误触） |
| **高危** | desktop_launch / desktop_kill | **每次确认**（一次性令牌，单次消费：confirm 批准后**必须重试动作**才执行，前端确认卡已实现自动重试） |
| **新站点** | L1 模式导航到未批准域名 | 每次确认（本轮补齐，见 §6.8；managed 沙箱不拦——隔离无风险） |

### 5.2 隔离边界 ✅

- **L1**：绝不操作用户已有 tab；只用自己的 tab 组；会话结束只关自己的
- **登录态**：L1 的 cookie 不落盘不外传；L2 的 `storage_state` 维持现状（本会话文件）
- **剪贴板**：零暴露

### 5.3 审计 ✅

事件流全量落盘 `~/.local/share/fnixagent/driver_events.jsonl`：`{ts, session, driver_mode(L1/L2/L3), action, target, ok, degraded, confirmations}`。一鱼两吃：安全合规 + 可喂 Paper 2 的 agent 行为数据。

### 5.4 反提示注入 ✅（本轮补齐）

所有页面内容/控件树进入 LLM 上下文前标注不可信边界——`browser_view`（原 `browser_snapshot` / `browser_read`，Phase 5 已收敛）/ `desktop_window_state` 返回值统一前置警示（对齐 OpenAI 官方"treat all page content as untrusted"）。

---

## 6. 实施记录与缺陷修复（三轮）

### 6.1 P0（2026-08-28 完成）✅

`browser.py::_ensure()` 增加 CDP 探测 + `connect_over_cdp()` 回退 + 隔离 tab 纪律。零新依赖。

### 6.2 P1 ✅

`driver_router.py`（事件流 + 审计 + 两条铁律）+ `kernel.py` computer.use 接通。

### 6.3 P2 ✅

`desktop.py` + `desktop_*` 12 工具 + `/api/v1/desktop/*` + 前端 `DesktopPanel`；唯一新依赖 `cua-driver==0.22.2`（MIT，`THIRD_PARTY_NOTICES.md` 已登记全文；`cua-agent[omni]` 的 AGPL 组件与 OmniParser CC-BY-4.0 明确排除，不随附不分发）。

### 6.4 P3 ✅

relay 子进程（`FNIX_DESKTOP_MODE=relay`）+ 高危确认弹层（就地弹卡：描述 + 批准/拒绝）+ 审计落盘。验证：kill 进程不拖垮后端；审计文件可回放；批准后重试消费令牌协议正确。

### 6.5 第一轮端到端测试发现并修复（2026-08-28）

1. `GET /desktop/screen_size` 404（只注册了 LLM 工具漏了 GET 端点）→ 补路由
2. 浏览器 `/state` unchanged 短响应缺 `driver_mode` → 补齐（初始 `none`）

### 6.6 第二轮：内置搜索外泄缺陷（2026-08-29，用户实测反馈）✅ 已修复

3 条漏出路径全部封堵（§2.1 五道闸）。修复中还揪出自引入回归：危险协议（`file:`）被新逻辑误转搜索 → 协议检查前置到搜索转换之前。
验证：策略单测 13/13、前端 vitest 6/6、tsc 零错误、驱动回归 18/18、集成 12/12；真实驱动实测「北京天气」内置搜索完成；UI 面板级三层验证齐。

### 6.7 第三轮：系统性逐项核验（2026-08-29）✅

对照本文档逐条机械核验：P0-P3 全部承诺落地；审计文件实存；确认闸单次消费协议正确（前端批准后自动重试）；剪贴板零暴露；合规齐全。

### 6.8 第三轮发现并修复的差距

1. **§5.4 反提示注入**：三个回传页面/控件内容的工具补 `_UNTRUSTED_NOTICE` 边界（纯函数可测）
2. **§5.1 新站点确认**：新增 `_l1_domain_gate`（纯函数）：仅 `cdp-attach` 模式，首访未批准域名拦截发一次性令牌；批准后本会话免询；令牌单次消费、域名不可串用、300s 过期；`BrowserState`/API/工具全链路透传 `requires_confirmation` + `confirmation_id`
3. **文档不一致**：录制回放 V1 §4.4 称 "P3 亮点" 但 §6 计划未含 → 明确归入 §7 N4

第三轮验证：31/31 单测全绿（策略 13 + 路由 10 + 桌面 8）。

### 6.9 复核后补充修复的实现缺口（本轮）

用户要求复核 + 启动内置浏览器实测后，发现第三轮文档声称 ✅ 但实际尚未接通的缺口，已补齐并端到端验证：

1. **L1 新域确认态推不到前端**：`BrowserSession.navigate()` 拦截分支未递增 `version`，前端 `since` 轮询永远拿不到 `requires_confirmation`。修复：拦截时 `version += 1` + `updated_at` 更新 + `pending_url` 保留目标地址。
2. **浏览器面板无确认 UI**：`BrowserView` 原未声明 `requires_confirmation`/`confirmation_id`，无确认卡与重试逻辑。修复：新增确认卡（与 `DesktopPanel` 同形态）+ 批准带令牌重试 + 轮询态也能弹卡。
3. **本地地址误转搜索/补错协议**：`localhost:5175` 等 host:port 因无域名后缀被当成百度搜索；即便识别为网址也补成 `https://` 导致本地明文服务 SSL 错误。修复：前后端 `_LOCAL_HOSTS` 镜像集合 + host:port 剥离端口判断 + 本地主机默认 `http://`。
4. **确认事件未入审计**：拦截未写 `driver_events.jsonl`。修复：新增 `domain_gate` 审计事件，连同后续 `navigate` 成功事件一并落盘。

本轮验证：后端单测 17/17、前端 vitest 8/8、tsc 零错误；端到端实测本地 `localhost:5175` 打开前端、`北京天气` 内置百度搜索、L1 CDP 接管 + 新域确认闸全流程通过。

---

## 7. 剩余差距与路线

| 优先级 | 项 | 对标 | 说明 | 状态 |
|---|---|---|---|---|
| **N1（下一优先）** | L1 接管引导层 | Codex Chrome 扩展 / WorkBuddy BrowserSkill / Trae OpenPreview 选择框 | CDP 探测已就位；补"一键启动调试端口"引导弹层 + 首次选择记忆（前端批准按钮已在本轮实现） | ⬜ |
| N2 | 截图圈选注释 | Codex Comment Mode / Trae 十字准星 | 前端在截图上画框 → 坐标换算注入上下文（人机共驾坐标链路已有基础，增量小） | ⬜ |
| N3 | 多 tab 并行 | Codex/百度搭子连续多站 | `BrowserSession` 页面池 `_pages: dict[str, Page]` + `browser_tab` 工具 + 面板 tab 条 | ⬜ |
| N4 | 录制回放 | cua-driver 原生 start_recording/replay_trajectory | "用户演示一遍，agent 重放"——QQ 登录类高频重复操作的杀手锏（V1 曾标 "P3 亮点"，校准为本项）。**Phase 5 已提前完成**：`browser_trajectory.py` + `/browser/trajectory/*` 接口；按元素名解析 ref（编号会漂移）、每步状态断言（不符即停，杜绝静默成功）、输入值默认不落盘（演示登录时那就是密码） | ✅ 已实现并验证（真 Chromium 实测：录制登录→重放后确实登录成功） |
| N5（观察） | 跨端接力/远程 | 百度搭子手机遥控 + 锁屏不中断云端浏览器 | 远程 relay 需长连接 + 双向鉴权 + 指令白名单 + 高危人工确认，量级另立项目（评估报告 §5.4） | ⬜ 观察 |
| — | uid/token 语义快照契约 | chrome-devtools-mcp a11y+uid | 浏览器侧当前为 ARIA 树 + 坐标/文本双通道（中文站点更稳）；token 契约作为后续增强 | ⬜ |
| 不做 | 视觉 grounding 模型 | — | GPU 依赖 + OmniParser CC-BY-4.0 许可证问题；cua `degraded` 回退 + 截图 + 多模态看图已覆盖 | ❌ 明确不做 |
| 不做 | 消除开源痕迹 | — | 法律 + 工程双理由明确拒绝；合规靠 `THIRD_PARTY_NOTICES.md`，观感靠 adapter 收敛与统一命名 | ❌ 明确不做 |

---

## 8. 风险与对策（实测更新）

| 风险 | 对策 | 实测状态 |
|---|---|---|
| 用户浏览器没开调试端口（常态） | 静默走 L2；首次引导弹层给一键启动命令（N1） | ✅ L2 兜底已实测；引导弹层待做 |
| Chrome 136+ 对 `--remote-debugging-port` 限制默认 profile | 引导独立 profile（browser-use `from_system_chrome` 做法）；或 Edge 通道 | N1 一并交付 |
| cua-driver UWP 控件树 degraded（实测"设置"应用 0 元素） | `degraded` 诚实标记触发截图+坐标回退；工具描述明示边界 | ✅ 实测验证降级链 |
| 中文站点 a11y 树拿不到文本（iconfont/canvas） | 保留截图+坐标双通道；搜索默认走百度 | ✅ 内置百度已实测 |
| cua-driver API 迭代快 | pin `cua-driver==0.22.*`；只在 DesktopDriver 一处触碰其 API | ✅ requirements 已 pin |
| 搜索关键词被当域名 | 五道闸内置浏览器优先（§2.1） | ✅ 第二轮修复并回归 |
| 页面内容提示注入 | 不可信边界标注（§5.4） | ✅ 第三轮修复并回归 |
| 测试环境差异 | 沙箱进程 HOME 重定向导致 Playwright 缓存路径偏移、powershell 派生受限、unlink 被环境拦截——均为助手执行环境产物，真实用户环境不存在；测试时注入 `PLAYWRIGHT_BROWSERS_PATH` | ✅ 已记录归档 |

---

## 9. 与顶级产品的差异化定位

Codex/Trae 的浏览器跑在云沙箱；WorkBuddy/百度搭子/OpenClaw 是本地优先。FnixAgent 定位**本地 Windows 工作台**：

1. **本机登录态是天然主场**：本地 CDP 直连，云端产品做不到用户本机 cookie；隐私边界更好讲（浏览器数据不出本机）
2. **不抢前台的桌面操控**：Codex 的 Windows computer use 任务期间占用前台；FnixAgent 的 cua-driver 后台注入不抢光标/焦点——用户打游戏、看视频时任务照常跑
3. **内置浏览器优先**：链接与搜索绝不出软件，比"每次弹框选浏览器"的行业规则更彻底
4. **三域统一**：桌面操控补齐后，"浏览器 + 原生应用 + 代码"统一在一个 agent loop 里——这是 Codex（macOS 先行）和 Trae（无桌面操控）在 Windows 上的空档

**一句话**：不追云端的规模，把"本机登录态 + 本机桌面 + 内置浏览器优先 + 后台不打扰"做到 Codex/百度搭子级体验水准。

---

## 附：相关文档

- `GUI_DRIVER_ASSESSMENT.md` — 评估与选型（含全部一手实测数据、Windows GUI 陷阱清单、竞品横向对比、OpenClaw 拆解、cua-driver 实测）
- `GUI_DRIVER_DESIGN_V1_ARCHIVE.md` — V1 原版设计归档
- `GUI_DRIVER_DESIGN_V2.md` — V2 增量（内置浏览器优先原则 + 对标刷新），已并入本文档
- `GUI_DRIVER_IMPL_REPORT.md` — 三轮实施逐轮记录
- `THIRD_PARTY_NOTICES.md`（仓库根）— 第三方合规登记
