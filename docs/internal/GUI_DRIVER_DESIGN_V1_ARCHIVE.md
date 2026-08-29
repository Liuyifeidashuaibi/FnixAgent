# FnixAgent 界面驱动设计方案：比肩 Codex / Trae / WorkBuddy

> 设计日期：2026-08-28　|　前置文档：`GUI_DRIVER_ASSESSMENT.md`（评估与选型，含全部实测数据）
> 本文档是工程设计，不是调研。所有选型结论在评估报告 §8 已实测验证。

---

## 0. 设计目标

让 FnixAgent 具备与 Codex、Trae、WorkBuddy、OpenClaw 同级的界面驱动能力：

1. **内置浏览器**：用户可见、可共驾的浏览器面板，AI 在其中自主操作
2. **接管已登录浏览器**：复用用户日常 Chrome/Edge 的登录态，不做"截图-点击"的笨循环
3. **不干扰用户**：AI 活动隔离在自己的 tab 组 / 后台进程，不抢用户的光标和窗口
4. **桌面操控**：操作原生应用（非浏览器），作为浏览器能力的降级补充
5. **分级降级**：CDP 优先 → 隔离浏览器 → 系统桌面，逐级回退且过程对用户透明
6. **安全可控**：权限分级、高危确认、全程审计

---

## 1. 对标能力矩阵

数据来源：Codex 官方发布（2026-04/05/06）、Trae 官方与文档、WorkBuddy web-access skill（本机即有）、OpenClaw 文档（§8 已拆解）。

| 能力 | Codex | Trae | WorkBuddy | OpenClaw | FnixAgent 现状 | 本方案 |
|---|---|---|---|---|---|---|
| 内置浏览器面板 | ✅ in-app browser | ✅ 内置预览 | ✅ | ✅ CLI | ✅ **已有**（截图流） | 保留增强 |
| 接管已登录会话 | ✅ Chrome 扩展 | ❌ | ✅ CDP proxy | ✅ user profile | ❌ | **L1（本方案核心）** |
| 隔离 tab 组，不垄断用户浏览器 | ✅ | — | ✅ 后台 tab | ✅ | 部分（独立实例） | L1 必备 |
| 桌面操控（原生应用） | ✅ computer use | ❌ | ❌ | ✅ CUA | ❌ | **L3（cua-driver）** |
| 多 tab 并行任务 | ✅ | ✅ | ✅ | ✅ | ❌ 单 page | L1 支持 |
| 页面上直接评论/圈选元素 | ✅ 页面评论 | ✅ 十字准星 | ❌ | ❌ | 坐标点击（近似） | P2 引入 |
| 语义快照（非纯截图） | ✅ CDP | ✅ Playwright | ✅ DOM/eval | ✅ a11y+uid | ⚠️ 有 ARIA 树无 uid | **token 契约** |
| 自动等待/重试/自愈 | ✅ | ✅ 遮挡先滚动、失效换文本 | ✅ | ✅ | ⚠️ 部分（click_text 兜底） | 统一 executor |
| 新站点/高危操作确认 | ✅ | — | — | ✅ 权限模式 | ❌ | **安全模型** |
| 操作审计留痕 | ✅ | — | — | ✅ | ❌ | 事件流落盘 |
| 三层动态切换 | ✅ 插件→扩展→内置 | ✅ | — | ✅ profile 路由 | ❌ 单层 | **降级链** |

**结论**：FnixAgent 已有全行业罕见的起点——截图流浏览器面板是人机共驾的正确形态，直接保留。真正缺的是三块：**接管登录态（L1）、桌面操控（L3）、分级路由与安全层**。全部有开源底座，不需要发明新技术。

---

## 2. 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│  前端 workbench（已有 oai-main + StudioPanel）                    │
│  浏览器面板（截图流）│ 桌面预览面板 │ 确认弹层 │ 操作时间线          │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP 轮询 /api/v1/browser/*、/api/v1/desktop/*
┌──────────────▼──────────────────────────────────────────────────┐
│  FastAPI 后端                                                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ DriverRouter（新增，core/tools/driver_router.py）       │     │
│  │ · 能力探测 → 选驱动 · 失败逐级降级 · 事件流分发          │     │
│  └──────────┬─────────────────┬─────────────────┬─────────┘     │
│             ▼                 ▼                 ▼               │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ L1 CDP 接管   │  │ L2 托管浏览器 │  │ L3 桌面 cua-driver │    │
│  │ connect_over │  │ launch()     │  │ EMBEDDED, 56 工具   │    │
│  │ _cdp()       │  │ （现状保留）  │  │ 经 relay 子进程     │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│             │                 │                  │               │
│  ┌──────────▼─────────────────▼──────────────────▼─────────┐    │
│  │ computer.use syscall 执行器（kernel.py 空壳补全）        │    │
│  │ 权限闸（已有 COMPUTER 高危标记）→ 审计落盘              │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 分层职责

| 层 | 模块 | 文件 | 状态 |
|---|---|---|---|
| 路由 | `DriverRouter` | `core/tools/driver_router.py` | 新增 |
| L1 | `CdpBrowserDriver` | `core/tools/browser.py` 扩展 | 改造（约 150 行） |
| L2 | `ManagedBrowserDriver` | `core/tools/browser.py` 现有 `BrowserSession` | 保留 |
| L3 | `DesktopDriver` | `core/tools/desktop.py` | 新增 |
| relay | `desktop_relay` 子进程 | `core/tools/desktop_relay.py` | 新增（P3 可选先行内嵌） |
| syscall | `computer.use` 执行器 | `core/agent/kernel.py:796` | 补全空壳 |
| API | `/api/v1/desktop/*` | `api/routers/desktop.py` | 新增（仿 browser.py） |

### 2.2 降级决策（DriverRouter）

```
请求到达（目标 URL 或应用名）
  │
  ├─ 目标是网页？
  │    ├─ 探测 9222/9223（GET /json/version, 2s 超时）
  │    │    ├─ 通 → L1 CDP 接管（复用登录态）
  │    │    └─ 不通 → 询问用户"接管浏览器？"（一次确认，记住选择）
  │    │         ├─ 同意 → 引导开调试端口 → L1
  │    │         └─ 拒绝 → L2 托管浏览器
  │    └─ L1 执行失败 ≥2 次 → 自动降 L2，事件流告知用户
  │
  └─ 目标是原生应用/桌面？
       └─ L3 cua-driver（degraded 时回退截图+坐标模式）
```

**两条铁律**（来自 OpenClaw 的教训，§8.3）：
1. **降级是显式事件，不是静默行为**——切换驱动必须写入事件流并告知用户
2. **失败不逐动作回退**——L1 挂了就整体切 L2，不在同一个动作上反复横跳

---

## 3. 模块设计

### 3.1 DriverRouter（新增）

```python
# core/tools/driver_router.py（骨架）
class DriverRouter:
    """统一驱动入口：能力探测、路由、降级、事件流。"""

    async def probe_cdp(self, ports=(9222, 9223)) -> str | None:
        """GET http://127.0.0.1:{port}/json/version，2s 超时，返回 endpoint 或 None。"""
        # 实测依据：评估报告 §2.1，Chrome 151 Protocol 1.3 全通

    async def route(self, intent: dict) -> "Driver":
        """intent = {kind: web|desktop, url?, app_name?} → 选择驱动。"""

    async def execute(self, action: "DriverAction") -> "DriverResult":
        """执行动作；失败计数；连续 2 次失败触发降级并广播事件。"""

    # 事件流（前端时间线 + 审计落盘共用）
    def events(self) -> AsyncIterator[DriverEvent]: ...
```

**统一动作契约**（三个驱动都实现，LLM 只见这一套）：

```python
@dataclass
class DriverAction:
    op: str            # navigate|click|type|scroll|snapshot|screenshot|read|...
    target: str | None # opaque token（e.g. "e12"）；坐标动作用 (x, y)
    text: str | None
    meta: dict

@dataclass
class DriverResult:
    ok: bool
    summary: str          # 给 LLM 的文本摘要
    screenshot_b64: str | None   # 前端展示
    snapshot_text: str | None    # 语义快照（含 token）
    error: str | None
    degraded: bool        # 驱动能力降级标记（cua-driver 原生支持）
```

### 3.2 L1：CdpBrowserDriver（改造 browser.py）

核心改动——`_ensure()` 从"只会 launch"改为"先接管再自起"：

```python
async def _ensure(self):
    if self._page is not None:
        return self._page
    from fnixagent.core.tools.driver_router import router
    endpoint = await router.probe_cdp()
    if endpoint:
        # 接管用户浏览器（实测依据：评估报告 §2.1 connect_over_cdp OK）
        self._browser = await self._pw.chromium.connect_over_cdp(endpoint)
        ctx = self._browser.contexts[0]
        # 隔离 tab 组：永远 new_page，绝不碰用户已有 tab（Codex/WorkBuddy 同款原则）
        self._page = await ctx.new_page()
        self._mode = "cdp-attach"
    else:
        # 现有逻辑不变：launch headless + storage_state
        ...
```

**L1 下的行为约束**（对标 Codex "No session hijacking"）：
- 只在自己 `new_page()` 出来的 tab 里操作，关闭会话时只关自己的 tab
- 沿用现有 `asyncio.Lock` 串行化
- cookie 持久化（`storage_state`）仅在 L2 模式启用——L1 的登录态在用户浏览器里，不该被复制落盘（安全边界）

**多 tab 并行**（Codex 卖点）：`BrowserSession` 增加页面池 `_pages: dict[str, Page]`，工具层暴露 `browser_tab`（list/select/new/close），调度器给并行任务分配不同 tab。P2 实现，P0 先单 tab。

### 3.3 L2：ManagedBrowserDriver

即现有 `BrowserSession.launch()` 路径，原样保留。仅在 L1 不可用时由 Router 选用。**不改动现有 8 个 `browser_*` 工具的对外签名**——它们已经过打磨（click_text 兜底、降级重拍、协议白名单）。

### 3.4 L3：DesktopDriver（新增，依赖 cua-driver）

```python
# core/tools/desktop.py（骨架）
import cua_driver as cd

class DesktopDriver:
    """cua-driver 封装。EMBEDDED 模式零配置（评估报告 §8.4 实测）。"""

    def __init__(self):
        self._d = None  # lazy: cd.CuaDriver.create()

    async def _drv(self):
        if self._d is None:
            self._d = cd.CuaDriver.create()
        return self._d

    async def call(self, tool: str, args: dict) -> "DriverResult":
        d = await self._drv()
        r = await d.call_tool(tool, json.dumps(args))
        return DriverResult(
            ok=not r.is_error,
            summary=r.text,
            screenshot_b64=self._img(r),      # r.images → b64
            degraded=r.degraded,              # 直接透传 cua 的诚实降级标记
            error=r.error_code,
        )
```

暴露给 LLM 的工具（统一 `desktop_*` 前缀，不出现 cua 字样——adapter 层收敛第三方）：

| 工具 | 映射 cua-driver | 权限 |
|---|---|---|
| `desktop_state` | `get_desktop_state` | LOW |
| `desktop_apps` | `list_apps` | LOW |
| `desktop_windows` | `list_windows` | LOW |
| `desktop_window_state` | `get_window_state` | LOW（返回 snapshot_id + element_token） |
| `desktop_launch` / `desktop_kill` | `launch_app` / `kill_app` | **HIGH（确认）** |
| `desktop_click` / `desktop_type` / `desktop_hotkey` | `click` / `type_text` / `hotkey` | MIDDLE |
| `desktop_set_value` | `set_value`（token 定位） | MIDDLE |
| `desktop_bring_front` | `bring_to_front` | MIDDLE |

**录制回放**（cua-driver 原生 `start_recording`/`replay_trajectory`，OpenClaw 同款）作为 P3 亮点：用户演示一遍操作，agent 可重放。

### 3.5 relay（本地子进程模式）

**为什么需要**：cua-driver 的 `EMBEDDED` 模式已经免 daemon，但仍建议把 L3 放独立子进程：

1. **权限隔离**：若未来需要驱动提权进程（UIPI，评估报告 §4.2），只有 relay 子进程需要管理员权限，FastAPI 主进程保持普通权限
2. **崩溃隔离**：原生运行时段错误不拖垮后端
3. **生命周期**：GUI 会话可独立于 API 服务重启

**P0/P1 先内嵌（`DesktopDriver` 直接 `create()`），P3 抽成子进程**——契约不变，只换传输层（stdout JSONL，同 `_bench2.py` 已验证的 NDJSON 模式）：

```
FastAPI ──stdout JSONL──▶ desktop_relay 子进程 ──UniFFI──▶ cua-driver 原生运行时
        ◀──stdout JSONL──
```

### 3.6 computer.use syscall 执行器（补全空壳）

```python
# kernel.py:796 现状：return SyscallResponse.err("computer.use 需接入 browser-use (预留接口)")
# 改为：
async def _handle_computer_use(self, req):
    action = DriverAction.from_syscall(req)      # 解析统一动作
    result = await driver_router.execute(action) # 路由 + 降级 + 事件流
    self._audit(req, result)                     # 审计落盘
    return SyscallResponse.ok(result.to_syscall())
```

权限闸已有（`SyscallCategory.COMPUTER` 高危 + `computer`/`admin` scope），无需改动。**这是整个方案里"白捡"的部分——骨架早就设计好了，只差执行器。**

---

## 4. 安全模型（对标 Codex 权限设计 + Anthropic/OpenAI 官方指南）

评估报告 §4.2 已核实业界做法，这里落地为四条：

### 4.1 动作分级

| 级别 | 动作 | 策略 |
|---|---|---|
| 只读 | snapshot / screenshot / read / list_* | 直接放行 |
| 常规 | navigate / click / type / scroll / set_value | 首次确认，会话内记住 |
| **高危** | desktop_launch / desktop_kill / 提交表单 / 文件上传 / 下载执行 | **每次确认** |
| **新站点** | L1 模式下导航到未批准域名 | 每次确认（Codex 同款） |

确认弹层在前端浏览器/桌面面板上就地出现（不是聊天流里的文字确认）。

### 4.2 隔离边界

- **L1**：绝不操作用户已有 tab；只用自己的 tab 组；会话结束只关自己的
- **登录态**：L1 的 cookie 不落盘不外传；L2 的 `storage_state` 维持现状（本会话文件）
- **剪贴板**（cua-driver 有 clipboard_write）：默认禁用，白名单场景（中文输入粘贴）才开

### 4.3 审计

事件流（`DriverEvent`）全量落盘到 `.fnix/audit/driver_events.jsonl`：
`{ts, session, driver_mode(L1/L2/L3), action, target, ok, degraded, confirmations}`。
这是 PAPER 2（OPS-MEM）之外另一份可审计的 agent 行为数据，一鱼两吃。

### 4.4 反提示注入

所有页面内容/截图进入 LLM 上下文前标注 `untrusted` 边界；页面中出现"忽略之前指令"类文本时，工具返回值里附告警标记（对齐 OpenAI 官方"treat all page content as untrusted"）。

---

## 5. 前端交互设计

复用现有三栏（oai-side / oai-main / StudioPanel），不引入新依赖（方案总原则）：

1. **浏览器面板**（已有截图流，增强）：
   - 顶部模式徽标：`已接管 Chrome`（青）/ `隔离沙箱`（灰）/ `桌面操控`（琥珀）——降级时徽标变化 + toast 事件
   - `version` 增量轮询机制已有，加 `driver_mode` 字段即可
2. **桌面预览面板**（新增，P2）：`get_desktop_state` 的 PNG 直显，叠加 agent 光标位置（cua-driver 有 agent cursor 主题 API，原生支持）
3. **操作时间线**：右侧栏列表，`DriverEvent` 流渲染（点击可看截图快照）——对标 Codex summary pane
4. **确认弹层**：高危动作就地弹卡（复用 `oai-ibtn`/token 样式体系）
5. **P2 亮点**：截图上圈选元素 → 注释进对话（对标 Codex 页面评论、Trae 十字准星）。实现：前端在截图上画框 → 换算成页面坐标 → 作为上下文注入。已有坐标换算链路（人机共驾），增量小。

---

## 6. 实施计划

| 阶段 | 内容 | 改动 | 依赖 | 验收 |
|---|---|---|---|---|
| **P0（0.5 天）** | CDP 探测 + `connect_over_cdp()` 回退 + 隔离 tab 纪律 | `browser.py` ~150 行 | 0 新依赖 | 开调试端口后 `browser_navigate` 能用用户登录态访问内网站点 |
| **P1（1 天）** | `DriverRouter` + 降级事件流 + `computer.use` 执行器接通 | 新文件 + kernel.py 补壳 | 0 | 拔掉调试端口，任务自动落 L2，事件流可见降级记录 |
| **P2（2-3 天）** | `DesktopDriver` + `desktop_*` 工具 + `/api/v1/desktop/*` + 前端桌面面板 | 新文件 ~400 行 | **+`cua-driver`**（MIT） | `desktop_state` 截图回显；`desktop_windows` 中文标题正确 |
| **P3（2 天）** | relay 子进程抽离 + 高危确认弹层 + 审计落盘 | 新文件 | 0 | kill 进程不拖垮后端；审计文件可回放 |
| **P4（可选）** | 多 tab 并行 + 截图圈选注释 + 录制回放 | 前后端 | 0 | 并行任务互不串页 |

**关键路径是 P0**——零依赖、半天、直接解锁"登录态"这个最痛的缺口。P2 引入 `cua-driver` 是唯一的新依赖（MIT，`THIRD_PARTY_NOTICES.md` 已就位）。

**不建议做的**：视觉 grounding 模型（OmniParser CC-BY-4.0 / UI-TARS 需 GPU）——cua-driver 的 `degraded` 回退路径 + 截图 + 多模态模型看图即可覆盖，不背 GPU 依赖。

---

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 用户浏览器没开调试端口（常态） | 首次引导弹层给一键启动命令（`chrome --remote-debugging-port=9222` + 独立 profile 说明）；拒绝则静默走 L2 |
| Chrome 136+ 对 `--remote-debugging-port` 限制默认 profile | 引导用户用独立 profile 目录（browser-use `from_system_chrome` 的做法，评估报告 §3.2）；或 Edge 通道 |
| cua-driver UWP 控件树 degraded（实测，§8.4） | `degraded` 标记触发截图+坐标回退；工具描述里明示能力边界 |
| 中文站点 a11y 树拿不到文本 | 保留截图+坐标双通道（现有设计恰好正确，改革时不砍） |
| cua-driver API 迭代快（0.19→0.22 已有变化） | pin 版本（`cua-driver==0.22.*`）；只在 DesktopDriver 一处触碰其 API，升级面收敛 |
| 用户要求"消除开源痕迹" | 已明确拒绝（法律+工程双理由）；`THIRD_PARTY_NOTICES.md` 合规承载；产品观感靠 adapter 收敛与统一命名实现 |

---

## 8. 与顶级产品的差异化定位

Codex/Trae 是云端产品，浏览器跑在云沙箱；WorkBuddy/OpenClaw 是本地优先。FnixAgent 的定位是**本地 Windows 工作台**，因此：

- 登录态复用是**天然主场**（本地 CDP 直连，云端产品做不到用户本机 cookie）
- 隐私边界更好讲（浏览器数据不出本机）
- 桌面操控补齐后，"浏览器 + 原生应用 + 代码"三域统一在一个 agent loop 里——这是 Codex（macOS 先行）和 Trae（无桌面操控）在 Windows 上的空档

**一句话**：不追云端的规模，把"本机登录态 + 本机桌面"这两件云端产品做不到的事做到 Codex 级的体验水准。
