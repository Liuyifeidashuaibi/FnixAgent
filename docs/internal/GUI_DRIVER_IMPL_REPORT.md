# FnixAgent GUI 驱动实施记录（P0-P3）

> 实施日期：2026-08-29　|　依据：`GUI_DRIVER_DESIGN.md`（同目录）
> 状态：P0-P3 已落地并通过编译/单测/回归/类型检查；P4 可选未实施。

## 已落地能力

- **L1 接管登录态**：`core/tools/browser.py` 的 `_ensure()` 先探测 CDP（9222/9223），探测到则 `connect_over_cdp()` 接管用户浏览器，只在自己 `new_page()` 的 tab 操作，cookie 不落盘，关闭只关自己的 tab。
- **L3 桌面操控**：`core/tools/desktop.py` 封装 cua-driver（MIT，`THIRD_PARTY_NOTICES.md` 已登记），EMBEDDED 默认零配置，`FNIX_DESKTOP_MODE=relay` 走 `desktop_relay.py` 子进程隔离；12 个 `desktop_*` 工具 + 高危动作（launch/kill）确认闸。
- **分级路由与安全层**：`core/tools/driver_router.py` 统一路由 + DriverEvent 事件流 + `~/.local/share/fnixagent/driver_events.jsonl` 审计；两条铁律（降级是显式事件 / 失败不逐动作回退，连续 2 次失败整体切换）。
- **computer.use 执行器**：`core/agent/kernel.py` 的 `_handle_computer_use` 从空壳接入 DriverRouter。
- **前端**：`BrowserView` 驱动模式徽标；`DesktopPanel` 桌面操控面板（截图流 + 窗口列表 + 启动应用 + 坐标点击确认 + 事件时间线）；work/code 两模式均新增「桌面」tab。

## 新增/改动文件

| 文件 | 说明 |
|---|---|
| `src/fnixagent/core/tools/driver_router.py` | 新增：DriverRouter + DriverEvent |
| `src/fnixagent/core/tools/desktop.py` | 新增：DesktopDriver + desktop_* 工具 |
| `src/fnixagent/core/tools/desktop_relay.py` | 新增：relay 子进程 |
| `src/fnixagent/api/routers/desktop.py` | 新增：/api/v1/desktop/* |
| `src/fnixagent/core/tools/browser.py` | 改造：L1 CDP 接管 |
| `src/fnixagent/core/agent/kernel.py` | 改造：computer.use 执行器 |
| `src/fnixagent/api/routers/browser.py` | 改造：/api/v1/browser/events |
| `src/fnixagent/main.py` / `services/work_agent.py` | 改造：路由挂载 + 工具注册 |
| `apps/workbench/src/shell/desktop/*` | 改造/新增：模式徽标 + DesktopPanel + tab |
| `requirements.txt` | 登记 playwright / cua-driver |

## 关键实测（cua-driver 0.22.2）

- `CuaDriver.create()` 同步；`call_tool()` 异步。
- 截图在 `images[0].data_base64`；`mime_type="image/png"`。
- 裸坐标 click/type/hotkey/scroll 需 `scope="desktop"`；kill_app 需 `pid`，hotkey 需 `keys`。

## 验证

- py_compile 全过；单测 18 条全绿；`tests/unit` 全量 exit 0；`tsc -b` 零错误；TestClient `/desktop/state` 等 200；cua-driver 实机返回 1707x960 截图，事件流端到端。

## 待办

- L1 实机验证需 Chrome 开 `--remote-debugging-port=9222`（前端引导弹层属后续增强）。
- relay 子进程实机集成测试。
- P4（多 tab 并行 / 截图圈选注释）未实施；录制回放已在 2026-08-29 Phase 5 提前完成，详见 `GUI_DRIVER_ROADMAP.md`。

## 第二轮修复（2026-08-29，用户反馈：内置搜索外泄系统浏览器）

根因：① 搜索关键词被 `_normalize_url` 当域名拼接；② Tauri 壳下 `_blank` 外链落入系统默认浏览器；③ Agent 可用 `start <url>` 唤起系统浏览器。

修复（内置浏览器优先）：
- `core/tools/browser.py::_normalize_url`：关键词（空格/无后缀）→ 内置百度搜索；危险协议检查前置（消除 `file:` 误转搜索回归）。
- `core/tools/workspace.py`：`run_command` 拦截 start/explorer/xdg-open/Start-Process/Invoke-Item/open + URL，引导 `browser_act(action="goto")`。
- `services/work_agent.py`：系统提示词规则 12（内置浏览器优先 + 桌面操控指引）。
- 前端：`BrowserView.toNavigableUrl`（镜像后端契约）+ 地址栏支持关键词；`DesktopApp` 全局捕获拦截 `http(s)` 链接 → 派发事件 → 内置浏览器面板渲染。

验证：策略单测 13/13、前端 vitest 6/6、tsc 零错误、驱动单测 18/18 无回归；真实复测「北京天气」内置百度搜索完成（标题《北京天气_百度搜索》）；桌面驱动 launch notepad → 确认闸 → 真实启动（pid 31376）→ 枚举命中 → 截图 → 关闭，全链路通过。

## 第三轮：系统性逐项核验 + 差距修复（2026-08-29 晚）

对照 `GUI_DRIVER_DESIGN.md` 全部承诺逐项机械核验，结论：

**已落地（核验通过）**：P0（CDP 探测 9222/9223·2s 超时、connect_over_cdp、只开自己 new_page、L1 cookie 不落盘、关闭只关自己 tab、连续 2 失败显式降级）；P1（DriverRouter 两条铁律、事件流、审计 jsonl 实存 29 事件、computer.use 已接通无空壳）；P2（12 工具双模驱动、7 端点、LOW/MIDDLE/HIGH 分级）；P3（relay 子进程 + 失败自恢复、前端就地确认弹层、批准后正确重试消费令牌、时间线轮询）；剪贴板零暴露（比设计"默认禁用"更彻底）；THIRD_PARTY_NOTICES 合规齐全。

**本轮发现并修复的差距**：
1. §4.4 反提示注入未落地 → `browser_view`（原 `browser_snapshot` / `browser_read`，Phase 5 已收敛）/ `desktop_window_state` 返回值统一前置 `_UNTRUSTED_NOTICE` 不可信边界标注。
2. §4.1 新站点确认未落地 → 新增纯函数 `_l1_domain_gate`：仅 `cdp-attach` 模式下，首访未批准域名拦截并发一次性确认令牌，批准后本会话免询；令牌单次消费、域名不可串用、300s 过期；`managed` 沙箱不拦（隔离无风险）。BrowserState/API/工具全链路透传 `requires_confirmation` + `confirmation_id`。
3. 设计文档内部不一致（录制回放 §3.4 "P3 亮点" vs §6 P3 行未含）→ 已在 `GUI_DRIVER_DESIGN_V2.md` §5 明确归入 N4。

新增验证：L1 闸单测 4 组（管理态放行 / 拦截→单次消费→批准免询 / 令牌不可跨域复用 / 标注常量）。
第三轮测试：31/31 全绿（策略 13 + 路由 10 + 桌面 8），py_compile 通过。

**环境受限项（非产品缺陷）**：受限助手沙箱中 `Path.unlink()` 会被执行环境拦截（"移入回收站"提示文案不在产品源码中），导致 `test_workspace_delete::test_delete_file_inside_workspace` 仅在该沙箱内失败；真实用户环境无此拦截。同类：Playwright 浏览器缓存 HOME 重定向、powershell 派生限制。
