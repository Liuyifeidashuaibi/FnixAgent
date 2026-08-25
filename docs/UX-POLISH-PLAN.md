# FnixAgent Workbench 前端体验打磨计划（UX-POLISH-PLAN）

> 目标：以 OpenCode / Claude Code 的成熟交互为标尺，把 Workbench 打磨到可录制宣传视频的水准。
> 原则：不推翻你已设计好的布局与视觉体系（glass kit / 桌面 shell），只做交互细节的对标补齐。
> 来源标注：[OC]=OpenCode TUI/CLI，[CC]=Claude Code，[审计]=本项目前端现状勘察。

---

## 一、现状事实基线（审计结论摘录）

| 区域 | 现状 | 缺口 |
|---|---|---|
| 流式渲染 | RAF 批处理打字机、整段去重、live 光标 ✅ | CoT 只进 StatusLine 不入气泡 |
| 思考块 | spinner「思考中→分析完成」+80字摘要，**不可展开** | 无透明感 |
| 工具卡 | 名称/参数摘要/结果折叠/验证徽标 ✅ | **无耗时**；无同工具聚合 |
| Token/成本 | **不存在**（persist 硬编码 token_count:0） | BYOK 用户最关心 |
| 消息时间戳 | **无** | 排查/回放不便 |
| HITL 审批 | ApprovalPanel 只在 设置→系统 分区 | 不在聊天链路，错过审批即卡死感知差 |
| 权限模式 | work_mode 有 ask/plan/craft 但 Composer 无快捷切换 | 每次都要打字说明模式 |
| 错误呈现 | 顶部 banner + humanize 文案 + 重试 ✅ | 无轻量 toast（非致命提示也用大banner） |
| 会话管理 | resume()/checkpoint 后端齐备，前端仅恢复按钮 | 无会话列表/切换/fork UI |
| 快捷键 | ⌘K面板/评审组/Alt+/ ✅ | 无历史反向搜索、无 transcript 全文视图 |
| 通知 | 无完成/需审批提醒 | 切走窗口错过完成时机 |
| i18n | 中文硬编码混英文按钮 | 录中文视频没问题，国际化留后 |
| 结构债 | fnixRuntime 1485行(chunk分发~400行if)、DesktopSettings 1554行、tokens.css 10122行、孤儿组件×4 | 不阻录像，长期还 |

---

## 二、P0 — 录制视频前必须（直接决定观感与可信度）

### P0-1 会话成本可见化 [OC /cost][CC /cost]
BYOK 用户的第一信任来自「花了多少钱一清二楚」。
- 每条 assistant 气泡右下角：`tokens · 用时`（数据源：loop 的 StepTrace.tokens_used/duration_ms 已存在，需在 done chunk 里透出 per-message usage 与累计）
- Composer 上方状态条追加本次会话累计 tokens（估算即可，±15% 可接受，标注"约"）
- 涉及文件：`fnixRuntime.ts`(chunk分发新增 usage 通道) → `useChatFlow.ts` → `MessageBubble` props → `StatusLine`
- 验收：任意任务结束后，气泡与状态条都能看到数字

### P0-2 思考过程可展开 [CC thinking blocks][OC]
- ThinkingBlock 点击展开完整推理文本（已有数据流，只是被截断）；默认收起保持现在的克制风格
- 展开后提供「复制思考」
- 文件：`ThinkingBlock.tsx`

### P0-3 工具卡补耗时 + 同工具聚合 [CC "Called slack 3 times"]
- ToolCallCard 右侧加 `1.2s`（StepTrace.duration_ms 已有）
- 连续同名工具 ≥3 次 → 折叠为单行「read_file ×5 (6.3s)」，点击展开逐条
- 文件：`ToolCallCard.tsx`、`MessageBubble` blocks 渲染处

### P0-4 HITL 审批内联进聊天流
- 拦截事件发生时，在气泡流中插入一张内联审批卡（工具名/risk 徽章/批准·拒绝按钮），复用 ApprovalPanel 的逻辑但嵌入 MessageList；同时保留设置页入口
- 数据源现成：guardrail/requires_approval 已随 NDJSON 下发；`/hitl/pending` 轮询兜底
- 文件：新 `components/chat/InlineApprovalCard.tsx` + `useChatFlow` 接线
- 这是产品差异化功能，必须在视频里出现

### P0-5 权限模式快捷切换器 [CC Shift+Tab]
- Composer 左下角三档 pill：`手动确认` / `自动写盘(craft)` / `仅规划(plan)` —— 映射现有 work_mode + FNIX_TOOL_AUTO_APPROVE 会话级开关，点击循环或下拉
- 状态条同步显示当前档位（对齐 CC 的 ⏵⏵ accept edits on 心智）
- 文件：`Composer.tsx`、`StatusLine.tsx`

### P0-6 消息时间戳 + 完成/失败桌面通知 [CC Ctrl+O 时间戳][OC attention]
- 每条消息 hover 或角标显示 HH:mm
- run 结束且窗口失焦时发 Tauri 桌面通知「任务完成/需要你的审批」（tauri notification plugin，一次性授权）
- 文件：`MessageBubble.tsx`、`DesktopApp.tsx`（focus 监听）、`src-tauri` 配置

---

## 三、P1 — 体验质感（视频后两周内）

1. **会话中心** [OC /sessions]：侧栏会话列表（标题=首句截断）、点击切换、fork 按钮；后端 `/sessions`+resume API 已备
2. **消息级 Undo** [OC /undo]：气泡菜单「撤回到此」——结合现有 checkpoint resumeRun 实现"删除该轮并还原文件"
3. **Ctrl+R 提示词历史反向搜索** [CC]：草稿已有 localStorage，扩成全历史索引弹窗
4. **Ctrl+O 全文转录视图** [CC]：只读抽屉，含时间戳/模型名/全部工具明细，支持复制导出 Markdown [OC export]
5. **轻量 toast 系统**：guardrail 提示、复制成功等降级为右下 toast；错误仍用 banner
6. **空态打磨**：Work home hero 下加 3 个一键示例任务 chip（也是视频素材）；StudioPanel 各 tab empty 态配插图
7. **语言统一**：按钮类英文(Copy/Show more)统一中文化；i18n 框架暂缓
8. **@file 补全 Web 模式可用**：目前仅 Tauri 可用（依赖目录 walk），补一个基于 workspace ensure 后的文件列表缓存通道

## 四、P2 — 结构健康度（不影响录制，排后）

- `fnixRuntime.ts` chunk 分发 if-chain(≈400行) 重构为 `{chunk_type: handler}` 表驱动；顺带补单测
- `fnixBridge.ts` 20+ 处重复 fetch try/catch 收敛为 `withBridge()` 高阶函数
- `DesktopSettings.tsx`(1554行) 按分区拆文件；`tokens.css`(10122行) 按 glass kit/页面拆分
- 孤儿组件处置：JobsPanel/ProcessTimeline/GlassProcessList/useStreamStatus —— 接入工作台或删除
- `.cluster/taskboard-review` 遗留目录清理；无障碍焦点陷阱库引入

## 五、录制视频前的 Checklist（硬件级验收）

- [ ] 冷启动到可输入 ≤ 5s；全程 DevTools 零红错
- [ ] 流式打字丝滑无跳变；停止按钮 <500ms 生效
- [ ] 一个带 Office 产物的任务：产物预览(ArtifactCanvas)是视觉高潮点，提前准备一个 HTML/SVG 华丽样例
- [ ] HITL 内联审批卡演示一次拒绝一次批准
- [ ] 权限模式 pill 切换入镜；token 计数入镜
- [ ] 失焦后完成 → 桌面通知弹出镜头
- [ ] 准备好干净的工作区目录与预置素材，避免现场等待超过 60s 的环节（长任务剪掉或加速）

## 六、明确不做（本阶段 scope 控制）

- 不换 UI 框架/不重做视觉体系；不做移动端；不做多语言框架；
- 不做 OC 式 share 公网链接（本地优先定位冲突）；
- LSP 集成 [OC] 列入 Code 模式后续路线，不挤占本阶段。
