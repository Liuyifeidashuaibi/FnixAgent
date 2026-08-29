# 界面驱动能力评估：CDP 优先 → 系统 GUI 降级

> 调研日期：2026-08-28　|　环境：Windows / Chrome 151 / Python 3.13 / Node 22
> 范围：FnixAgent 项目现状盘点 + 本机能力实测 + 市面方案调研 + 选型建议
> 所有结论均基于本机实测或一手来源，未核实项已明确标注

---

## 0. 结论速览

| 层次 | 项目现状 | 本机可用性 | 结论 |
|---|---|---|---|
| **CDP（优先层）** | ❌ 无原生实现，仅一份依赖外部 CLI 的 SKILL.md | ✅ **实测全通，且可零依赖** | **最大缺口，也是最高性价比的补法** |
| **Playwright（现役层）** | ⚠️ 有 691 行完整实现，但只会 `launch()` 独立 headless 实例 | ✅ 已装，`connect_over_cdp()` 实测可用 | 改一行即可接入 CDP，复用登录态 |
| **系统 GUI（降级层）** | ❌ 完全空白，`computer.use` 是返回错误字符串的空壳 | ✅ **cua-driver 实测开箱即用（56 工具）** | 直接依赖，勿自研 |

**一句话建议**：不要把 `browser.py` 推倒重来。它缺的只是**接管用户浏览器**的能力——加上 `connect_over_cdp()` 就跨过了"复用登录态/降低反爬风险"这道最大的坎。桌面操控层**不要自研**，直接依赖 `cua-driver`（MIT）——本机实测 Windows 零配置可用，且 OpenClaw（387k star）在 Windows 上用的就是它。详见 §8。

> ⚠️ **§4.3 的结论已被 §8 推翻**。§4.3 依据 README 判断"cua-driver 偏 macOS、Windows 文档薄弱，建议自研 uiautomation"——实测证明该判断错误。以 §8 为准。

---

## 1. 项目现状盘点

### 1.1 已有资产

| 文件 | 内容 | 评价 |
|---|---|---|
| `src/fnixagent/core/tools/browser.py` | 691 行。`BrowserSession` 进程级单例 + 8 个 `browser_*` 工具（navigate/click/type/scroll/history/snapshot/read/viewport），asyncio.Lock 串行化，JPEG 截图流，cookie 持久化到 `~/.local/share/fnixagent/browser_state.json` | 工程质量不错：锁、降级重拍、协议白名单都做了 |
| `src/fnixagent/api/routers/browser.py` | 前端轮询截图的 HTTP API | 人机共驾链路已通 |
| `src/fnixagent/core/skills/builtin/electron/SKILL.md` | 通过 CDP + `agent-browser` CLI 自动化 Electron 桌面应用（VS Code/Slack/Figma…），含 Windows 启动参数 | **纯文档**，依赖外部 CLI，非项目代码 |
| `src/fnixagent/core/skills/builtin/webapp-testing/SKILL.md` | Playwright UI 验证（视觉/响应式/a11y） | 纯文档 |
| `src/fnixagent/core/agent/kernel.py:796` | `computer.use` syscall 处理器 | **空壳**，直接 `return SyscallResponse.err("computer.use 需接入 browser-use (预留接口)")` |

### 1.2 三个关键缺口

**缺口 1：不能接管用户已有的浏览器（最致命）**

```python
# browser.py:151 — 现状
self._browser = await self._pw.chromium.launch(headless=True, args=[...])
```

`launch()` 每次起一个全新 Chromium，后果是：
- **登录态为零**：用户的微信公众平台、企业微信、内部系统全部要重新登录
- **指纹暴露**：headless + 无 profile，中文站点的反爬风控命中率显著上升（实测 `example.com` 这类静态站无感，但登录态站点会直接被拦）
- 现状靠 `storage_state` 持久化 cookie 缓解，但这只解决"上次登录过"，解决不了"用户在自己浏览器里刚登录过"

改法只有一行：

```python
# 优先接管，失败再自起
self._browser = await self._pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
```

**缺口 2：系统 GUI 层完全不存在**

`computer.use` 是设计好但没实现的入口。syscall 层已经把权限标好了（`SyscallCategory.COMPUTER`、高危标记、需要 `computer`/`admin` scope），骨架是现成的，缺执行器。

**缺口 3：没有 relay / 远程 GUI 驱动**

全项目搜索 `relay` 只命中 SAML 的 `RelayState`（CSRF 参数，与界面驱动无关）。**项目中不存在任何 GUI 指令中继机制**。

> 这里需要澄清需求："relay" 有两种截然不同的东西，成本差一个数量级：
> - **本地 relay**：后端进程 ↔ 本机 GUI 驱动进程之间的 IPC 转发（本机内，解决权限/生命周期隔离）
> - **远程 relay**：Agent 在云端，把 GUI 指令下发到用户机器执行（跨网络，需要长连接、鉴权、NAT 穿透）
>
> 本文的架构建议按**本地 relay** 设计。若目标是远程，安全模型要重做（见 §6.4）。

---

## 2. 本机能力实测

所有结果均为本次调研在本机实跑，非推断。

### 2.1 CDP 链路：全通，且可做到零第三方依赖

启动独立 Chrome（独立 profile，不干扰用户浏览器）后逐项探测：

```
CDP /json/version OK
  Browser: Chrome/151.0.7922.175
  Protocol-Version: 1.3
  webSocketDebuggerUrl: ws://127.0.0.1:9333/devtools/browser/<id>
WebSocket 直连 OK                      ← Node 22 原生 WebSocket，无需 ws 包
Target.createTarget OK
Runtime.evaluate OK
Accessibility.getFullAXTree OK (3 nodes)
Page.captureScreenshot OK (37 KB)
Input.dispatchMouseEvent OK
```

**要点**：Node 22 内置 `fetch` + 原生 `WebSocket`，意味着一个**零依赖**的 CDP 客户端用标准库就能写出来。不必引入 `puppeteer-core` / `ws`。

Python 侧复测（项目 `.venv` 已装 playwright）：

```
Chrome: Chrome/151.0.7922.175
connect_over_cdp OK, contexts = 1
aria_snapshot OK, len = 232
   -> - heading "Example Domain" [level=1] | - paragraph: This domain is for use...
new_cdp_session Runtime.evaluate OK -> 2
Accessibility.getFullAXTree nodes = 15
```

`connect_over_cdp()` 与 `aria_snapshot()` 均可用，**§1.2 缺口 1 的修法已被实测验证可行**。

### 2.2 系统 GUI 层：UIA 控件树可用

在隔离 venv 装 `uiautomation` 后实测（未污染项目 `.venv`）：

```
uiautomation import OK
顶层窗口数: 9 | 有名称: 8
  [PaneControl] 任务栏  (2560x72)
  [WindowControl] 下载 - 文件资源管理器  (0x0)
  [WindowControl] Clash Verge  (0x0)
  [PaneControl] WorkBuddy  (0x0)
子控件数: 3  → PaneControl | DesktopWindowXamlSource ...
InvokePattern / ValuePattern / LegacyIAccessiblePattern → API 存在
```

三点解读：

1. **能直接拿到中文控件名**（"任务栏"）。这是 UIA 相比视觉模型在中文场景的决定性优势——`Name` 属性本身就是中文，没有 OCR 误差，不受分辨率和 DPI 缩放影响。
2. **`BoundingRectangle` 全是 `0x0`** —— 因为这些窗口处于最小化状态。**这不是 bug，是 Windows GUI 自动化的头号陷阱的实测证据**：最小化窗口拿不到可点击坐标。所有依赖坐标的方案（PyAutoGUI、纯视觉 CUA）在这里直接失效，而 UIA 的 `InvokePattern` / `ValuePattern` 不依赖前台，仍可工作。这直接决定了降级层的技术选型。
3. **WorkBuddy 自身是 `PaneControl`**：Electron/Chromium 系应用，理论上开 `--remote-debugging-port` 后连它自己也能走 CDP。

### 2.3 环境清单

| 项 | 状态 |
|---|---|
| Chrome 151.0.7922.175 | ✅ `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| Edge | ✅ 已安装（x86 路径） |
| 调试端口 9222 / 9223 / 3456 | ❌ 当前**无监听**（用户浏览器未开调试端口） |
| `agent-browser` CLI | ✅ 已装（Node shim，支持 `connect <port>` / `snapshot` / `click @ref`） |
| Node 依赖 | ✅ workspace 已有 `playwright-core`、`puppeteer-core`、`devtools-protocol`、`ws`、`chromium-bidi` |
| Python `playwright` | ✅ 项目 `.venv` 与系统 Python 均有 |
| Playwright 浏览器二进制 | ✅ `ms-playwright` 缓存含 chromium-1208/1223/1228/1234 |
| Python GUI 库 | ❌ `pyautogui` / `uiautomation` / `pywinauto` / `pyperclip` / `mss` **全部未装** |
| PowerShell `Add-Type` | ❌ **被本环境安全策略拦截**，不能靠 `Add-Type -AssemblyName UIAutomationClient` 临时拼方案 |

---

## 3. 调研：CDP / 浏览器自动化

数据源：GitHub REST API、npm registry、PyPI JSON、各仓库 README（2026-08-28 抓取）。

### 3.1 横向对比

| 项目 | 定位 | CDP 直连 | 快照类型 | 许可证 | 活跃度(star/最近提交) | 集成方式 | 主要局限 |
|---|---|---|---|---|---|---|---|
| **chrome-devtools-mcp** | Google 官方，Chrome DevTools for agents | ✅ `--browser-url` / `--wsEndpoint` / `--autoConnect` | **a11y 树 + uid** | Apache-2.0 | [49.9k](https://api.github.com/repos/ChromeDevTools/chrome-devtools-mcp) / 2026-08-28 | MCP server（npm v1.8.0，**0 运行时依赖**） | 只官宣支持 Chrome；`--browser-url` 需用户预先开端口 |
| **Playwright MCP** | Microsoft 官方 MCP 封装 | ✅ `--cdp-endpoint` / `--extension` / `--user-data-dir` | a11y 树，可选坐标 | Apache-2.0 | [36.6k](https://api.github.com/repos/microsoft/playwright-mcp) / 2026-08-27 | MCP server（npm @playwright/mcp v0.0.79） | 需下载浏览器二进制；持久 profile 单实例独占 |
| **browser-use** | 一体化 Browser Agent（Python） | ✅ 原生 CDP，**已移除 Playwright 依赖** | DOM + 截图双通道 | MIT | [111.5k](https://api.github.com/repos/browser-use/browser-use) / 2026-08-28 | Python 包 v0.13.8（py≥3.11） | 依赖极重（约 35 个硬依赖，含多家 LLM SDK） |
| **cdp-use** | **纯 CDP 的 Python 类型安全客户端** | ✅ 原生，唯一用途 | 无（纯协议层） | MIT | [315](https://api.github.com/repos/browser-use/cdp-use) / 2026-07-29 | Python 包 v1.4.5（py≥3.11） | star 少、社区小；无 locator/等待/自愈等高层抽象 |
| **Stagehand** | "Playwright for agents"，自研 CDP 引擎 | ⚠️ 自启 Chrome + 固定端口 | DOM/a11y + 自愈定位 | MIT | [24.1k](https://api.github.com/repos/browserbase/stagehand) / 2026-08-28 | TS/Python/Go 三 SDK（v4.0.2） | 商业导向，默认走 Browserbase 云 |
| **puppeteer / puppeteer-core** | Node 端 CDP 底层库 | ✅ `puppeteer.connect()` | 无内置快照 | Apache-2.0 | [95.5k](https://api.github.com/repos/puppeteer/puppeteer) / 2026-08-28 | Node 包 v25.9.0 | 无 agent 抽象；headless 指纹易识别 |
| **playwright-python** | 对照：Python 版 Playwright | ✅ `connect_over_cdp()` | a11y / ARIA snapshot | Apache-2.0 | [15.0k](https://api.github.com/repos/microsoft/playwright-python) / 2026-08-27 | Python 包 v1.62.0 | Node 驱动 + 需下载浏览器；CDP 模式下部分高级 API 受限 |
| **browserbase / Anchor / Steel / Kernel** | 商业云浏览器 BaaS | ✅ 提供 CDP endpoint | 云端托管 | 闭源（组件级部分开源） | 未核实 | REST/CDP API | 云端新开浏览器，**与"复用本地登录态"目标相反**；数据出境；计费 |
| **Firecrawl** | 内容抓取层（非操控） | ❌ | Markdown/HTML | **AGPL-3.0** | [173k](https://api.github.com/repos/firecrawl/firecrawl) | HTTP API | 只能读不能操作；AGPL 有传染性，闭源分发勿入主链路 |

### 3.2 值得抄的三件事

1. **`chrome-devtools-mcp` 的 "a11y 树 + uid" 契约**：`take_snapshot` 返回 a11y 树并为每个元素分配 `uid`，后续 `click`/`fill`/`hover` 只传 uid，避免把冗长选择器塞进上下文。官方明确建议 snapshot 优先于 screenshot。还有 `--slim` 精简模式。这是 token 效率上的最佳实践，**项目现在的 `browser_snapshot` 已经返回 ARIA 树，但缺 uid 机制**——点击仍靠坐标或文本匹配，是明显的改进点。

2. **`browser-use` 的 profile 接法**：0.13.x 已从 Playwright 迁到自研 CDP 栈（依赖含 `cdp-use==1.4.5`），并原生支持 `Browser.list_chrome_profiles()` + `Browser.from_system_chrome(profile_directory=...)`，可直接复用用户真实 Chrome profile 的登录态。这正是"CDP 优先"层想要的形态。**但不要直接依赖 browser-use 本体**——35 个硬依赖对一个已有完整架构的项目太重，抄它的 profile 定位思路即可。

3. **`cdp-use` 是做自研分层最干净的底座**：由官方 CDP protocol spec 自动生成 TypedDict 绑定，MIT，纯 Python，零浏览器下载、零 Node，天然落在 FastAPI 进程内。缺点是社区小、缺等待/自愈等工程化封装。

### 3.3 中文场景的两个提醒

- **反爬**：中文站点（微信公众平台、知乎、淘宝、企业微信）的风控与登录态强相关。CDP 直连真实浏览器 + 真实 profile 是**最低风险**路径；headless 云浏览器反而更容易被风控。
- **a11y 树会失效**：中文站点普遍使用 iconfont / 自定义字体图标和 canvas 渲染，a11y 树常拿不到可读文本。**必须同时保留坐标 boxes + 截图通道**，否则纯 a11y 方案在中文页面上会大面积失效。项目现状恰好相反——`browser.py` 是**纯截图流 + 坐标点击**，a11y 只作辅助，这个设计在中文站点上其实更稳，改革时别把截图通道砍掉。

---

## 4. 调研：系统 GUI / Computer Use

### 4.1 横向对比

| 项目 | 定位 | Windows | 元素获取 | 许可证 | 活跃度 | 集成 | 主要局限 |
|---|---|---|---|---|---|---|---|
| **UI-TARS**（bytedance） | 端到端 GUI 视觉模型 | ✅ 推荐桌面场景 | 纯视觉 + 坐标 | Apache-2.0 | [11.4k](https://api.github.com/repos/bytedance/UI-TARS) / 2026-01 | 自部署 vLLM，HTTP | 无控件树；需 GPU；坐标受分辨率/缩放影响 |
| **UI-TARS-desktop** | 桌面 Agent 客户端 | ✅ | 视觉 + sandbox | Apache-2.0 | [38.7k](https://api.github.com/repos/bytedance/UI-TARS-desktop) / 2026-08-05 | 自带前端，难嵌入 | 产品化重，改造成本高 |
| **Agent S3**（simular-ai） | 通用 GUI agent 框架 | ✅ 官方声明全平台 | 视觉 + 可选 UIA | Apache-2.0 | [12.2k](https://api.github.com/repos/simular-ai/Agent-S) / 2026-08-01 | `pip install gui-agents`（0.3.2） | 依赖强推理 LLM，token/延迟开销大 |
| **cua**（trycua） | 全栈 CUA：驱动+VM+基准 | ✅ 明确支持 Win | 视觉；宣称后台操控不抢焦点 | MIT | [22.0k](https://api.github.com/repos/trycua/cua) / 2026-08-28 | `uv tool install`，含 MCP server | 迭代快，API 稳定性未核实 |
| **OpenAdapt** | 录制→确定性重放 | ✅ 含 RDP/Citrix | UIA 控件树 + 录屏 | MIT | [1.7k](https://api.github.com/repos/OpenAdaptAI/OpenAdapt) / 2026-08-28 | pip 包 | 主线是 record→replay，非自由探索 agent |
| **OmniParser**（微软） | 截图→结构化元素 | ✅ | 视觉（YOLO+OCR+图标描述） | 仓库 LICENSE 为 **CC-BY-4.0**（README 徽章写 MIT，**以 LICENSE 为准**） | [25.3k](https://api.github.com/repos/microsoft/OmniParser) / 2026-07-20 | Python 服务 | 许可证不一致需法务确认；需 GPU |
| **pywinauto** | Windows GUI 自动化 | ✅ | **控件树**（win32/uia 双后端） | BSD-3-Clause | [6.2k](https://api.github.com/repos/pywinauto/pywinauto) / 2026-05-23 | `pip install -U pywinauto` | 自述 "hobby project" |
| **uiautomation** | UIA Python 封装 | ✅ | **控件树**（name/controlType/BoundingRectangle） | Apache-2.0 | [3.6k](https://api.github.com/repos/yinkaisheng/Python-UIAutomation-for-Windows) / 2026-06-02 | `pip install uiautomation` | 仅 Windows；README 要求**管理员运行** |
| **PyAutoGUI** | 跨平台键鼠模拟 | ✅ | 无（纯坐标） | BSD-3-Clause | [12.7k](https://api.github.com/repos/asweigart/pyautogui) / **2024-08** | `pip install pyautogui` | **明显停滞**；无元素概念 |
| **bytebot** | 容器化 AI 桌面 | 容器内 Linux | 视觉 | Apache-2.0 | [11.1k](https://api.github.com/repos/bytebot-ai/bytebot) / **已 archived 2025-09-12** | Docker | 停维护，勿用 |
| **Claude Computer Use** | 商业能力 | ⚠️ **官方参考实现仅 Linux/Docker/Xvfb** | 纯视觉 | 闭源 | 17.5k（claude-quickstarts） | `computer_toolset_20260801` | 无 Windows 官方实现 |
| **OpenAI CUA** | 商业能力 | ⚠️ 官方示例仅 Ubuntu 22.04 + Xvfb | 纯视觉 | 闭源 | 1.8k | Responses API `computer` tool | 无 Windows 官方实现 |

### 4.2 Windows GUI 自动化可靠性陷阱清单

这一节是选型真正的决定因素。

| 陷阱 | 事实与对策 |
|---|---|
| **最小化 / 后台窗口** | **本次实测直接命中**：最小化窗口 `BoundingRectangle` 返回 `0x0`。`SetForegroundWindow` 在会话非活动时也会失败。对策：**动作一律优先走 UIA 的 `InvokePattern`/`ValuePattern`（不依赖前台）**，必须先前台时再 `ShowWindow(SW_RESTORE)`。 |
| **锁屏 / RDP 断开** | pywinauto 官方《Remote Execution Guide》明确列出锁屏下失效的方法：所有 `*_input`（`click_input` 等）、`set_focus`、`type_keys`、mouse/keyboard 模块。仍可用：win32 后端 `send_chars`/`send_keystrokes`，双后端 `set_edit_text`。对策：会话保持连接（`tscon`），或改用非输入 API。 |
| **UAC / 安全桌面** | 微软文档：UAC 提升提示显示在独立桌面，其他进程通常无法访问。UIA 客户端要访问受保护系统 UI 必须带 `uiAccess=true` manifest **且程序需数字签名并安装在 ProgramFiles/System32** —— Python 脚本基本做不到。对策：agent 运行在高完整性级别，或**规避**（不触发需提权的操作）。 |
| **UIPI 完整性级别** | UIA 无法驱动更高完整性级别进程的 UI。对策：agent 进程与目标进程保持同一完整性级别。 |
| **DPI 缩放** | UIA 的 `BoundingRectangle`/`GetClickablePoint` 返回**物理像素**，而 `GetCursorPos` 返回**逻辑坐标**；非 96 DPI 下不调 `SetProcessDPIAware` 会算错。对策：启动时 `ctypes.windll.shcore.SetProcessDpiAwareness(2)`，用 `GetPhysicalCursorPos`，**不要与 PyAutoGUI 混用坐标系**。 |
| **中文输入 / IME** | `type_keys` 走键盘布局，中文需经 IME，确定性差。更稳：`send_keys`（支持任意 Unicode）、剪贴板粘贴、或 UIA `set_edit_text`。生产推荐"剪贴板粘贴 + 事后值校验"。 |
| **控件树 vs 视觉** | 控件树：精确、快、免分辨率依赖，但覆盖取决于目标是否实现 UIA（Qt/自绘/Electron 部分支持差）。视觉：普适但受分辨率/主题影响，中文 OCR 与图标语义是额外误差源。**对中文软件优先控件树**——UIA 的 `Name` 本身就是中文，无识别误差。 |

### 4.3 兜底层的推荐组合

**`uiautomation`（或 pywinauto `uia` 后端）做主干 + OmniParser 做视觉补充 + 自研决策层接 `computer.use` syscall。**

理由：
1. **先控件树，后视觉** —— 中文软件上 `Name` 即原生中文，落地成本远低于部署视觉 grounding 模型（UI-TARS 需 GPU，OmniParser 需 GPU 且有 CC-BY-4.0 许可证风险）。
2. **绕开两个最大的坑** —— 管理员/同完整性级别运行（绕 UIPI），动作走 `Invoke`/`SetValue` 而非 `*_input`（绕开锁屏与 RDP 断开）。这一条决定了 agent 能否在无人值守的 Windows 上活着。
3. **决策层不绑定模型** —— Anthropic / OpenAI 的官方参考实现都只有 Linux/Xvfb，Windows 执行层必须自己写。好在他们已把协议定义成"你实现 screenshot/click/type"，把 UIA 接到这套协议上即可，保留换模型的自由度。
4. **不推荐**把 Agent S3 直接当兜底执行层——虽支持 Windows，但引入整套 LLM 编排，作为"降级路径"过重。若要现成框架，它是第二阶段选项。

---

## 5. 推荐架构：三级降级

```
                    ┌─────────────────────────────────────┐
                    │  统一驱动接口 Driver Interface       │
                    │  snapshot / click / type / scroll   │
                    │  / screenshot / wait                │
                    └──────────────┬──────────────────────┘
                                   │ 能力探测 + 失败降级
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│ L1  CDP       │  fail  │ L2  Playwright│  fail  │ L3  系统 GUI   │
│ 直连真实浏览器 │ ─────► │ 自起 headless │ ─────► │ UIA 控件树     │
│               │        │ Chromium      │        │               │
│ 复用登录态    │        │ 隔离沙箱      │        │ 原生桌面应用   │
│ 反爬风险最低  │        │ 兜底通用网页  │        │ 最后手段      │
└───────────────┘        └───────────────┘        └───────────────┘
   connect_over_cdp          launch()              uiautomation
   / cdp-use 原生            （现状即此）           Invoke/SetValue
```

**降级触发条件**（建议）：

| 从 | 到 | 触发条件 |
|---|---|---|
| L1 → L2 | 9222 端口探测超时（>2s）/ 目标 URL 是敏感站点需隔离 / 用户显式要求无痕 |
| L2 → L3 | 目标不是网页（原生桌面应用、Electron 未开调试端口、系统对话框、UAC 提示） |
| 任意 → 人工 | 高危动作（删除/发送/支付/提权）→ 强制人工确认 |

### 5.1 L1 CDP 层（优先）

```
探测顺序：
  1. GET http://127.0.0.1:9222/json/version   （Chrome 默认）
  2. GET http://127.0.0.1:9223/json/version   （Electron / VS Code 常用）
  3. 扫描 9222-9230 常见端口
  4. 全部失败 → 引导用户："请以调试模式重启浏览器" 或自动降级 L2
```

实现选型（三选一，按推荐度）：

| 方案 | 依赖 | 理由 |
|---|---|---|
| **A. `playwright.connect_over_cdp()`** | 已有 | **改动最小**。实测可用，一行接入，且 `browser.py` 现有 8 个工具全部无需改动 |
| B. `cdp-use` | +1 pip 包 | 最干净，类型安全，无 Node 依赖；但要自己补等待/自愈 |
| C. Node 原生 CDP 客户端 | 0 | 实测可行（Node 22 原生 fetch+WebSocket），但要在 Python 主进程外再起一个 Node 进程，架构变复杂 |

**推荐 A**——先落地拿收益，B 作为后续优化。C 不推荐，除非要摆脱 playwright 依赖。

### 5.2 L2 Playwright 层

即现状。保留，但在降级链中它的定位变成"**没有 CDP 时的通用兜底**"，而非主路径。

### 5.3 L3 系统 GUI 层（新建）

模块建议：`src/fnixagent/core/tools/desktop.py`

```
uiautomation (Apache-2.0)
  ├─ 感知：GetRootControl() → 递归枚举 → 序列化为扁平列表
  │        {name, control_type, rect, enabled, is_offscreen}
  ├─ 动作：InvokePattern (点击) / ValuePattern (设值) / 剪贴板粘贴 (中文输入)
  └─ 校验：操作后重新读取控件状态确认生效
```

关键设计约束：
- **必须管理员权限运行**，否则 UIA 拿不到提权进程的控件（UIPI）
- **禁止使用 `*_input` 系列**（锁屏即失效），只用 Pattern 与 `set_edit_text`
- **中文输入走剪贴板粘贴 + 事后值校验**，不走 `type_keys`
- **进程启动即调 `SetProcessDpiAwareness(2)`**，坐标统一物理像素
- 接入现有的 `computer.use` syscall，权限模型已就绪（`SyscallCategory.COMPUTER` + 高危标记）

### 5.4 关于 relay

若目标是**本地 relay**（推荐）：把 L3 的 GUI 驱动放到独立子进程，通过本机 stdio / named pipe 与 FastAPI 主进程通信。收益是 GUI 子进程可用管理员权限跑而主进程不用，且崩溃不拖垮后端。

若目标是**远程 relay**：需要长连接 + 双向鉴权 + 指令白名单 + 全流程审计留痕，且**每一次高危动作强制人工确认**。这是另一个量级的工程，且把完整桌面控制权暴露到网络上，风险显著。建议先明确场景再决策。

---

## 6. 落地路线

| 阶段 | 工作 | 依赖变更 | 收益 |
|---|---|---|---|
| **P0（半天）** | `browser.py` 加 CDP 探测与 `connect_over_cdp()` 回退 | 0 | 复用登录态，反爬风险大降 |
| **P1（1-2 天）** | `browser_snapshot` 引入 uid 机制（抄 chrome-devtools-mcp） | 0 | token 消耗下降，点击准确率提升 |
| **P2（2-3 天）** | 新建 `desktop.py`，实现 UIA 感知 + Invoke/SetValue 动作 | +`uiautomation` | 打通原生桌面应用 |
| **P3（1 天）** | 接入 `computer.use` syscall，接上降级链与安全确认 | 0 | 三级降级闭环 |
| **P4（可选）** | 视觉兜底（OmniParser / UI-TARS），处理自绘界面 | +GPU | 覆盖 UIA 失效场景 |

**P0 + P1 是最高性价比**：零新依赖，两天内完成，直接解决"登录态"和"点击准确率"两个最痛的问题。不建议一上来就做 P4——引入 GPU 依赖和 CC-BY-4.0 许可证问题，收益却只在 UIA 失效的自绘界面上。

---

## 7. 风险与注意事项

1. **Firecrawl 是 AGPL-3.0**，若工作台要闭源分发，引入主链路有传染性风险。Jina Reader（Apache-2.0）是更轻的替代，但只能读不能操作。
2. **OmniParser 仓库 LICENSE 为 CC-BY-4.0**（README 徽章写 MIT，二者不一致），商用前需法务确认。
3. **browser-use 有约 35 个硬依赖**（含 anthropic/openai/genai 等多家 LLM SDK），只适合抄思路，不适合作为依赖引入。
4. **`uiautomation` 要求管理员权限**，意味着 FnixAgent 后端需要提权运行才能驱动提权进程——这会扩大攻击面，建议 GUI 驱动放独立子进程（本地 relay），主进程保持普通权限。
5. **GUI 自动化等于交出完整桌面控制权**。业界共性做法（Anthropic / OpenAI 官方文档）：隔离敏感数据、最小权限、高危动作人工确认、所有页面内容与截图视为不可信输入（防提示注入）。建议：独立低权限 Windows 账号 + 动作白名单 + 全流程截图审计留痕。
6. **未核实项**：Google Mariner 下线日期与 Gemini Computer Use API 能力（仅二手来源）；Manus / Devin 的桌面自动化实现细节；ShowUI 在中文 Windows 软件上的表现；cua 后台操控的 API 稳定性。

---

## 8. 补充调研：OpenClaw 架构拆解与 cua-driver 实测（2026-08-28 晚）

> 本节推翻 §4.3 的部分结论。触发原因：用户指出"顶级产品如 OpenClaw 都开源了这部分"，遂对 OpenClaw 与 cua-driver 做了一手核查与本机实测。

### 8.1 OpenClaw 是什么，开源到什么程度

| 项 | 事实 | 来源 |
|---|---|---|
| 仓库 | `openclaw/openclaw` | [GitHub API](https://api.github.com/repos/openclaw/openclaw) |
| Star | **387,908** | 同上，2026-08-28 |
| 语言 | TypeScript（pnpm workspace） | 同上 |
| 最近提交 | 2026-08-28 | 同上 |
| 许可证 | **MIT** | [LICENSE 原文](https://raw.githubusercontent.com/openclaw/openclaw/main/LICENSE) |

注意：GitHub API 返回的 `license` 字段是 `NOASSERTION`，**容易误判为"非标准许可证"**。读 LICENSE 原文后确认是标准 MIT，只是在末尾追加了一句指引：

> Third-party notices for incorporated or adapted code are recorded in THIRD_PARTY_NOTICES.md.

正是这句追加让 GitHub 的自动识别失败。**结论：OpenClaw 完全可用，可商用、可闭源、可修改，唯一义务是保留版权声明。**

### 8.2 OpenClaw 的浏览器层：profile 模型

来源：[docs.openclaw.ai/cli/browser](https://docs.openclaw.ai/cli/browser)

OpenClaw 把浏览器抽象成**命名 profile**，三种类型：

| Profile 类型 | 行为 | 对应 FnixAgent |
|---|---|---|
| `openclaw`（默认，managed） | 自起一个独立 Chrome，隔离 user-data-dir，独立 cookie | **即 `browser.py` 现状（`launch()`）** |
| `user` | **通过 Chrome DevTools MCP 控制你已登录的 Chrome 会话** | 缺失 → `connect_over_cdp()` |
| custom CDP | 指向本地或远程 CDP endpoint | 缺失 → `connect_over_cdp()` |

能力面：`status` / `doctor` / `start` / `stop` / `profiles` / `tabs` / `open` / `snapshot` / `screenshot` / 输入 / PDF / 文件上传 / JS eval。

**这直接印证了 §1.2 缺口 1 的判断**：FnixAgent 只有 managed 一档，缺的正是 OpenClaw 的 `user` 档——也就是"接管已登录浏览器"。OpenClaw 的实现路径同样是 Chrome DevTools MCP / CDP。

### 8.3 OpenClaw 的电脑操作层：node + provider 架构

来源：[docs.openclaw.ai/nodes/computer-use](https://docs.openclaw.ai/nodes/computer-use)

架构要点：

- **Gateway ↔ Node 分离**：云端/本机 agent（gateway）通过 `computer.act` + `screen.snapshot` 两个命令驱动"配对的桌面"（node）。
- **能力协商**：node 的 descriptor 声明支持的 action / target / observation 族，built-in computer tool **只暴露该 provider 能忠实执行的动作**，不可执行的动作直接省略而非用另一 provider 模拟。
- **Provider 选择**：
  - macOS：`Peekaboo`（默认，进程内坐标动作）或 `CUA`（driver daemon 嵌在 OpenClaw.app 内，继承 Accessibility/Screen Recording 授权）
  - **Windows / Linux：`cua-computer` 插件，直接调用打包的 CUA Driver SDK 0.19.3 运行时**
- **Provider 不逐动作回退**：切换 provider 会关闭当前执行面、轮换 generation。一个 CUA 失败就是 unavailable，不会静默改走 Peekaboo。

OpenClaw 的 v2 动作族（provider 支持时）：`list_apps`、`list_windows`、`get_accessibility_tree`、`get_cursor_position`、`get_window_state`、`launch_app`、`kill_app`、`bring_to_front`、`set_value`、`zoom`、`escalate_scope`、`invoke_menu`。CUA provider 额外暴露 **browser 族**：`get_browser_state`、`browser_prepare`、`browser_navigate`、`browser_click`、`browser_type`、`browser_dialog`、`browser_set_input_files`、`browser_download`、`browser_pointer`，以及录制 `start_recording` / `stop_recording` / `replay_trajectory`。

**关键设计：不透明引用（opaque reference）**。文档明确——坐标动作必须回显截图结果的 `frameId`；而 CUA 的 browser 族用 `browserRef` / `pageRef` / element references 定位元素，而非坐标。导航使 page-element 观察失效，driver 重启使整套 browser reference 失效。

> 这与 §3.2 提到的 chrome-devtools-mcp "a11y 树 + uid" 是同一思想，且 OpenClaw 更进一步——引用绑定了 generation，失效会被显式拒绝而非静默错点。

### 8.4 cua-driver 本机实测（Windows，决定性证据）

§4.3 曾依据 README 判断"cua-driver 偏 macOS，Windows 文档薄弱"，**该判断错误**。实测如下。

**安装与加载**

```
pip install cua-driver        # 0.22.2，MIT，Python >=3.10
PyPI wheels: win_amd64 ✅ / win_arm64 ✅ / macos ✅ / linux ✅
```

注意：PyPI classifier 只列了 `MacOS` 和 `POSIX::Linux`，**但 Windows wheel 是实打实发布的**——classifier 滞后于实际发布，不能作为判断依据。

**核心加载**

```python
import cua_driver as cd
d = cd.CuaDriver.create()
# create OK | available: True | mode: DriverExecutionMode.EMBEDDED
# DriverMetadata(driver_version=0.22.2, contract_version=0.7.0,
#                mcp_protocol_version=2025-06-18, pid=45252, embedded=True)
```

`EMBEDDED` 模式 = **原生运行时直接跑在 Python 进程内，不需要安装 daemon、不需要管理员权限、不需要任何配置**。这对 FnixAgent 是理想形态。

**工具清单：56 个**

```
应用/窗口: list_apps  list_windows  get_window_state  verify_state
          launch_app  kill_app  bring_to_front  set_window_frame
          invoke_menu  debug_window_info
输入:      click  double_click  right_click  drag  type_text
          press_key  hotkey  set_value  scroll
剪贴板:    clipboard_read  clipboard_write
屏幕:      get_screen_size  get_desktop_state  get_cursor_position
          move_cursor  zoom
光标叠加:  set_agent_cursor_enabled/motion/theme  get_agent_cursor_state
无障碍:    get_accessibility_tree
浏览器:    get_browser_state  browser_prepare  browser_navigate  browser_click
          browser_type  browser_dialog  browser_set_input_files
          browser_download  browser_pointer  page
录制:      start_recording  stop_recording  get_recording_state  replay_trajectory
会话:      start_session  escalate_session  get_session  list_sessions
          get_session_state  end_session
运维:      check_permissions  health_report  get_config  set_config  install_ffmpeg
```

**实跑结果**

| 调用 | 结果 |
|---|---|
| `get_screen_size` | ✅ 主显示器 1707x960 @1x |
| `list_apps` | ✅ 266 个应用，13 运行中；中文名正确（抖音 / WorkBuddy AI / Clash Verge / WeGame） |
| `list_windows` | ✅ 13 个窗口，中文标题正确（"抖音"、"设置"），带 `window_id` 与 `[off-screen]` 标记 |
| `get_desktop_state` | ✅ 全屏 PNG 截图 1707x960，base64 直返 |
| `get_cursor_position` | ✅ (1692, 494) |
| `get_window_state`（目标：系统"设置"） | ⚠️ `degraded: True`，元素数 0 |
| `get_accessibility_tree` | ⚠️ 传 `window_id` 时 fallback 为进程列表（该工具 schema 无参数定义） |

**两个实测发现的坑**

1. **UWP 应用控件树拿不到**：对"设置"（`SystemSettings.exe`）调 `get_window_state` 返回 `degraded: True` + 0 元素。好在驱动**诚实标注了 `degraded`**，上层可以据此回退到截图+坐标，而不是静默拿到空树。这正是"生产级接口"该有的样子。
2. **browser 族不能自起隔离浏览器**：`browser_prepare` 的 `strategy.kind` **只接受 `existing_profile`**（传 `isolated_new` 报 `unknown variant`）。也就是说——**它设计上就是用来接管用户已有浏览器 profile 的**，且 `window_id` 是必填的"批准锚点"（approval anchor）。这恰好与"CDP 优先、复用登录态"的目标一致，但也意味着**自起一个干净隔离浏览器仍需 Playwright**。

**接口设计质量**

返回值是统一的 `ToolResult`：

```
ToolResult(text, images, structured_json, is_error, error_code,
           action, verification, degraded, raw_json)
```

- `structured_json` 给 LLM 消费，`images` 单独承载截图，`raw_json` 保留原始 MCP 内容
- `verification` 承载操作后校验证据
- **`degraded` 显式标记能力降级** —— 这是自研方案很难一次做到位的细节

元素定位走 **opaque token**：`get_window_state` 返回 `snapshot_id` + `elements[].element_token`，后续 `set_value` / click 用 token 或 `(snapshot_id, element_index)` 定位，且要求 `snapshot_id` 匹配、过期 snapshot 会被拒绝。**直接抄这个契约即可，无需自己发明 uid 方案。**

### 8.5 修正后的架构

```
                    ┌─────────────────────────────────────┐
                    │  统一驱动接口 Driver Interface       │
                    │  snapshot / click / type / scroll   │
                    └──────────────┬──────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│ L1  CDP 接管  │  fail  │ L2  托管浏览器 │  fail  │ L3  桌面操控   │
│ 用户已登录    │ ─────► │ 隔离 Chromium │ ─────► │ 原生应用      │
│ Chrome/Edge   │        │               │        │               │
├───────────────┤        ├───────────────┤        ├───────────────┤
│ playwright    │        │ playwright    │        │ cua-driver    │
│ connect_over  │        │ launch()      │        │ (MIT, 0.22.2) │
│ _cdp()        │        │ （现状即此）   │        │ EMBEDDED 模式 │
│               │        │               │        │ 56 工具       │
│ 或 cua-driver │        │               │        │               │
│ browser_* 族  │        │               │        │ 含 browser_*  │
└───────────────┘        └───────────────┘        └───────────────┘
```

**L3 由"自研 uiautomation"改为"依赖 cua-driver"**，理由：

1. 56 个工具 vs 手写 5-6 个；应用管理、窗口管理、录制回放、会话升级、权限检查全部现成
2. `EMBEDDED` 模式零配置，不需要管理员权限，不需要 daemon
3. `degraded` 标记 + `verification` 证据链，是自研很难一次做到位的
4. opaque token 定位契约已经设计好，直接对接
5. **OpenClaw 387k star 在 Windows/Linux 上用的就是它**——有顶级产品背书，不是小众方案
6. MIT，可闭源商用

**保留 Playwright 的必要性**：cua-driver 的浏览器族只能接管已有 profile（`strategy.kind` 仅 `existing_profile`），无法自起隔离实例。L2 的隔离浏览器仍须 Playwright。两者是互补而非替代。

### 8.6 合规做法（不要做的 vs 要做的）

**不要做**：删除 LICENSE、改作者、伪装自研。

三个理由：

1. **法律**：MIT/Apache-2.0 允许闭源商用、允许修改、允许售卖，唯一义务就是保留版权声明与许可证文本。"消除痕迹"恰好是唯一被禁止的那件事。FnixAgent 源码头标注 `proprietary and confidential`，作为闭源商业产品，边界只会更严。
2. **技术上藏不住**：原生二进制的符号表、版本字符串、元数据（`DriverMetadata.driver_version` 会直接暴露 `0.22.2`）、包管理依赖树，SBOM 工具一扫即出。项目自身已有 `.gitleaks.toml` / `.secrets.baseline` / `.bandit.yaml` / pre-commit，说明合规基建是有的——反过来，做技术尽调的人同样扫得出来。
3. **没必要**：用户感知的是体验，不是 attribution 放在哪个文件里。

**要做**：已在仓库根目录建立 `THIRD_PARTY_NOTICES.md`，格式照 OpenClaw 的范本（387k star 的顶级产品就是这么做的——它公开写了 "Portions of OpenClaw were adapted from Pi / pi-mono" 并保留原作者 Copyright (c) 2025 Mario Zechner，这丝毫不影响它的地位）。

要做到"产品看起来完全是自己做的"，靠的是工程而非删除：

- 统一工具命名（`browser_*` / `desktop_*`），不对外暴露 `cua-*` 前缀
- 第三方调用全部收敛在 adapter 层，业务代码只依赖自有的 Driver Interface
- 前端面板、错误文案、交互流程全部自有；第三方进程名不出现在 UI 上
- 版本升级、异常降级、权限申请都用自己的话术包装

---

## 附：关键来源

- OpenClaw 仓库与许可证 — https://github.com/openclaw/openclaw （LICENSE 原文：MIT，Copyright (c) 2026 OpenClaw Foundation）
- OpenClaw Browser CLI 文档 — https://docs.openclaw.ai/cli/browser
- OpenClaw Computer Use 文档 — https://docs.openclaw.ai/nodes/computer-use
- OpenClaw THIRD_PARTY_NOTICES.md（范本）— https://raw.githubusercontent.com/openclaw/openclaw/main/THIRD_PARTY_NOTICES.md
- cua / cua-driver — https://github.com/trycua/cua （MIT，Copyright (c) 2025 Cua AI, Inc.）
- cua-driver PyPI — https://pypi.org/pypi/cua-driver/json （0.22.2，含 win_amd64 / win_arm64 wheel）
- chrome-devtools-mcp — https://github.com/ChromeDevTools/chrome-devtools-mcp
- Playwright MCP — https://github.com/microsoft/playwright-mcp
- browser-use — https://github.com/browser-use/browser-use
- cdp-use — https://github.com/browser-use/cdp-use
- Stagehand — https://github.com/browserbase/stagehand
- UI-TARS — https://github.com/bytedance/UI-TARS
- Agent S / gui-agents — https://github.com/simular-ai/Agent-S
- cua — https://github.com/trycua/cua
- OmniParser — https://github.com/microsoft/OmniParser
- uiautomation — https://github.com/yinkaisheng/Python-UIAutomation-for-Windows
- pywinauto Remote Execution Guide — https://pywinauto.readthedocs.io/en/latest/remote_execution.html
- 微软《UI Automation and Screen Scaling》— https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-screenscaling
- 微软《UI Automation Security Overview》— https://learn.microsoft.com/en-us/previous-versions/windows/desktop/dd319580(v=vs.85)
- Anthropic Computer Use — https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/computer-use-tool
- OpenAI Computer Use — https://platform.openai.com/docs/guides/tools-computer-use
