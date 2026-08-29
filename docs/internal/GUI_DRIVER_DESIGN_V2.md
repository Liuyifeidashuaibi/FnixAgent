# FnixAgent 界面驱动设计方案 V2：内置浏览器优先原则 + 对标刷新

> 版本日期：2026-08-29　|　前置文档：`GUI_DRIVER_DESIGN.md`（V1）、`GUI_DRIVER_ASSESSMENT.md`、`GUI_DRIVER_IMPL_REPORT.md`
> 本文档是 V1 的增量修订：竞品再调研结论刷新 + "内置浏览器优先"产品原则确立 + 第二轮缺陷修复记录 + 剩余差距路线。
> V1 的架构（DriverRouter 三级 + 两条铁律 + 安全模型）不变，经本轮实测继续有效。

---

## 0. 触发原因

用户实测反馈：**「内置浏览器搜索网页，结果电脑自带的浏览器跳出来了」**。期望形态是：

1. **内置浏览器**：搜索/浏览像普通浏览器一样在软件内完成，不唤起系统浏览器；
2. **桌面驱动**：操控电脑本身——打开浏览器、打开 QQ、登录 QQ 等；
3. **后台自主**：软件最小化/去打游戏时，任务（如截图任务）仍能自己完成。

本修订据此做竞品再调研、原则固化、缺陷修复与差距盘点。

---

## 1. 竞品再调研（2026-08-29，一手公开来源）

| 产品 | 内置浏览器形态 | 电脑操控 | 后台/不打扰 | 登录态复用 |
|---|---|---|---|---|
| **Codex**（OpenAI，4/16 大更新） | in-app browser 面板；6 月起对内置浏览器 live 控制；CDP 直连读网络/JS/DOM 并可实时改写；Browser Comment Mode（圈选元素截图+DOM 作上下文） | Mac computer use（4 月）→ **Windows computer use（5 月底：看/点/打原生应用，任务运行期间占用前台）** | background computer use（云端线程持续运行）；本机 Windows 任务**抢前台** | Chrome 扩展接管（5 月） |
| **Trae**（字节） | 官方内置浏览器工具双轨：**OpenPreview**（保留用户登录态，适合浏览/登录/发帖/填表）+ **agent-browser**（独立 headless 实例，不共享 cookies 需重登）；每次打开前强制弹框让用户选浏览器 | 无原生桌面操控（走 MCP/Playwright 扩展） | 编辑器内页签执行 | OpenPreview 保留登录态 |
| **WorkBuddy**（腾讯，3/9 上线，月活 2000 万+） | Agent Browser skill（SkillHub 安装：打开/滚动/点击/展开/截图/读取）；**BrowserSkill 直接操作用户已登录浏览器**，复用登录态、数据不出本机、不抢窗口 | 以本地执行能力（命令行/文件/Python）驱动 Computer Use 路线 | 不抢窗口 | ✅ 已登录浏览器直操 |
| **百度搭子 / DuMate**（百度，3 月上线） | **桌面端内嵌浏览器（7 月正式上线）**：客户端内直接打开并操作网页——检索整理、电商比价、数据填写；全程可视化、关键节点可干预 | "看见屏幕、操作软件"，预装安全沙箱，**高危操作强制二次确认**，数据默认本地处理 | **云端浏览器锁屏不中断**；电脑手机接力（上下文/进度/记忆交接），手机遥控电脑 | 关键动作（登录/授权/提交）用户随时接手 |

**结论**（刷新 V1 对标矩阵）：

1. **内置浏览器已是头部产品标配形态**（Codex in-app browser / 百度搭子内嵌浏览器 / Trae OpenPreview）——FnixAgent 的截图流面板与"搜索在内置浏览器内完成"的修复方向完全对齐主流，且人机共驾（用户在截图上点击/滚动转发）比 Codex 的纯 live-control 更早具备。
2. **"打开网页前让用户选择/优先内置"成为行业规则**：Trae 官方工具强制先弹选择框；百度搭子内嵌浏览器内执行网页任务。FnixAgent 的"内置浏览器优先"（链接/搜索一律进内置面板，系统浏览器唤起被拦截）与该规则同向，且更彻底（默认内置，无需每次选）。
3. **后台执行是差异化重点**：百度搭子把"锁屏不中断"做成卖点；Codex 的 Windows computer use **任务期间占用前台**——FnixAgent 的 cua-driver 后台注入（不抢光标/焦点，THIRD_PARTY_NOTICES 已注明其设计目标即"background control without stealing cursor or focus"）在本机场景优于 Codex 现状。
4. **登录态复用三家都有**（Codex Chrome 扩展 / WorkBuddy BrowserSkill / Trae OpenPreview）——对应 FnixAgent L1 CDP 接管，仍是 P0 之后的第一优先级（见 §4）。

---

## 2. 新增产品原则：内置浏览器优先（Built-in Browser First）

V2 确立为一级原则，与 V1 两条铁律并列：

> **一切网页搜索与浏览默认在内置浏览器中完成；任何唤起系统默认浏览器的路径都是缺陷。**

落地为五道闸（本轮已全部实现并测试）：

| 闸 | 位置 | 行为 |
|---|---|---|
| 1. 地址栏语义闸 | `BrowserView.toNavigableUrl`（前端）+ `_normalize_url`（后端，镜像契约） | 完整 URL 原样；域名补 `https://`；**搜索关键词（含空格/无域名后缀）→ 内置百度搜索**；危险协议检查前置 |
| 2. 链接拦截闸 | `DesktopApp` 全局捕获阶段点击拦截 | `http(s)` 链接一律路由到内置浏览器面板（派发事件 + 自动切面板），下载链接除外 |
| 3. 命令拦截闸 | `workspace.run_command` | `start/explorer/xdg-open/Start-Process/Invoke-Item/open + URL` 拦截，引导 `browser_act(action="goto")` |
| 4. 模型引导闸 | `WORK_SYSTEM_PROMPT` 规则 12 | 搜索/浏览/操作页面用 `browser_view`（只读）与 `browser_act`（写）；**严禁** run_command start / desktop_launch 打开系统浏览器；操控原生应用才用 `desktop_*` |
| 5. Tauri 壳兜底（建议项） | capabilities / webview 事件 | `shell:allow-open` 保留给本地产物文件；外链不进入 opener 路径（前端闸已覆盖，Rust 侧可作为纵深防御，后续增强） |

**协议正确性要点**（本轮实测确认）：高危动作确认闸是**单次消费**模型——`action → 拦截（发 confirmation_id）→ confirm(approve) → action 重试（消费令牌执行）`。前端确认卡需在批准后自动重试 action（桌面面板已如此实现）。

---

## 3. 第二轮缺陷修复记录（2026-08-29）

| # | 缺陷 | 根因 | 修复 | 验证 |
|---|---|---|---|---|
| 1 | 内置搜索外泄/打不开 | `_normalize_url` 把搜索关键词当域名拼 `https://北京天气` | 关键词 → 内置百度搜索（前后端镜像） | 真实驱动实测：「北京天气」→《北京天气_百度搜索》（managed 模式，未唤起系统浏览器） |
| 2 | 修复中引入的回归 | 危险协议（`file:` 等）被新逻辑误转搜索 | 协议检查前置到搜索转换之前 | 单测当场捕获并回归通过 |
| 3 | 外链落系统浏览器 | Tauri WebView2 未拦截的外链走系统默认 | 前端全局拦截 → 内置面板 | tsc 零错误 + vitest 6/6 |
| 4 | Agent 可用 `start <url>` 唤起系统浏览器 | 工具层无策略 | run_command 拦截 + 提示词规则 12 | 策略单测 13/13（17 组命令正反形态） |

验证总账：策略单测 13/13、前端 vitest 6/6、tsc 零错误、GUI 驱动既有单测 18/18 无回归、集成测试 12/12。

---

## 4. 桌面驱动能力边界（实测基线）与用户场景映射

实测（notepad 全链路，2026-08-29）：`launch notepad` → 确认闸 → 批准 → **真实启动（pid 31376）** → 窗口枚举命中「*新建 文本文档.txt - Notepad」→ 桌面截图留证 → 确认闸关闭。

用户场景映射（打开浏览器 / 打开 QQ / 登录 QQ）：

| 步骤 | 工具链 | 权限 |
|---|---|---|
| 打开应用（浏览器/QQ） | `desktop_launch`（HIGH，确认闸） | 每次确认 |
| 定位登录窗/输入框 | `desktop_window_state`（snapshot_id + element_token） | 只读 |
| 输入账号/密码、点登录 | `desktop_click` / `desktop_type` / `desktop_set_value`（中文走剪贴板粘贴路径） | MIDDLE，会话内记住 |
| 验证登录结果 | `desktop_state` 截图 + `verification` 证据链 | 只读 |

后台执行保证（"打游戏时仍能完成任务"）：Agent 循环在独立后端进程；内置浏览器为 headless 托管实例（无可见窗口）；桌面驱动经系统级注入（cua-driver 明确以"不抢光标/焦点"为设计目标）。**前端面板只是观察窗，不是执行依赖。**

---

## 5. 剩余差距与路线（V2 刷新）

| 优先级 | 项 | 对标 | 说明 |
|---|---|---|---|
| **N1（下一优先）** | L1 接管引导层 | Codex Chrome 扩展 / WorkBuddy BrowserSkill | CDP 探测代码已就位；补"一键启动调试端口"引导弹层 + 首次询问记忆。零新依赖 |
| N2 | 截图圈选注释 | Codex Comment Mode / Trae 十字准星 | 前端在截图上画框 → 坐标换算注入上下文（坐标链路已有人机共驾基础） |
| N3 | 多 tab 并行 | Codex/百度搭子连续打开多站 | `BrowserSession` 页面池；面板 tab 条 |
| N4 | 录制回放 | cua-driver 原生 start_recording/replay_trajectory | **Phase 5 已提前完成**：`browser_trajectory.py` + `/browser/trajectory/*`；按元素名找回漂移 ref、每步状态断言拦截静默失败、输入值默认不落盘；真 Chromium 已验证登录重放与同名诱饵拒绝 |
| N5（观察） | 跨端接力/远程 | 百度搭子手机遥控 + 锁屏不中断 | 与 ASSESSMENT §5.4 的远程 relay 对齐：需长连接+鉴权+白名单，量级另立项目 |
| 不做 | 视觉 grounding 模型 | — | 维持 V1 决策（GPU + CC-BY-4.0 许可证，cua `degraded` 回退已覆盖） |

---

## 6. 一句话定位（V2 不变，补充佐证）

> 不追云端规模，把"本机登录态 + 本机桌面 + 内置浏览器优先 + 后台不打扰"做到 Codex/百度搭子级体验——其中"不抢前台的桌面操控"与"链接绝不出软件的内置浏览器"是 FnixAgent 在 Windows 本地场景对 Codex（抢前台）与云端产品（无本机登录态/桌面）的明确差异点。
