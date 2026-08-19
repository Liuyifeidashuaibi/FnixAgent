# 事故响应手册 / Incident Response

> 本文件定义 FnixAgent 的事故分级、响应流程和事后复盘制度。

---

## 一、事故分级 / Severity Levels

### SEV-1 🔴 P0 致命

- 大规模服务不可用(> 50% 用户)
- 安全漏洞被利用,数据泄露
- 法律 / 合规问题
- 全平台启动失败

**响应 SLA**:15 分钟

### SEV-2 🟠 P1 严重

- 核心功能不可用(对话、记忆、Skill)
- 性能严重退化(> 5x 慢)
- 安全漏洞被发现但未利用
- 单平台启动失败

**响应 SLA**:1 小时

### SEV-3 🟡 P2 中等

- 部分 Skill 不可用
- 性能退化(1.5-5x 慢)
- 非核心功能 bug
- 文档错误

**响应 SLA**:4 小时

### SEV-4 🟢 P3 轻微

- UI 小瑕疵
- 警告信息文案错误
- 增强需求

**响应 SLA**:1 工作日

---

## 二、响应流程 / Response Workflow

### 2.1 事故检测

触发源:

1. **用户报告**:GitHub Issue / Discussion
2. **监控告警**:Grafana / Prometheus / Sentry(本项目默认关闭)
3. **CI 报警**:GitHub Actions 失败
4. **CodeQL 报告**:Dependabot 安全告警
5. **自我监控**:agentd 健康检查失败

### 2.2 启动响应

```
[0-15 min]  On-Call 接报 → 评估严重度 → 拉战时频道
   ↓
[15-60 min] 启动缓解(回滚 / 临时禁用 / 配置修复)
   ↓
[1-4 h]     根因分析 → 修复 → 灰度
   ↓
[4-24 h]    全量发布 / 跟进
   ↓
[24-72 h]   复盘会议 → 写 Postmortem → 改流程
```

### 2.3 战时角色

| 角色 | 职责 | 谁 |
| --- | --- | --- |
| **Incident Commander (IC)** | 决策、对外沟通 | Maintainer on-call |
| **Tech Lead** | 技术方案、修复 | 资深 Contributor |
| **Comms Lead** | 用户 / 社区沟通 | Maintainer |
| **Scribe** | 时间线记录 | 轮值 |

由于本项目为个人项目,通常 IC + Tech Lead + Scribe 合并为一人。

### 2.4 沟通模板

#### 内部 (Discord / 私聊)

```
🚨 [SEV-2] agentd 启动后 OOM
   - 影响:Mac M1 / macOS 14 用户 100% 不可用
   - 触发:commit abc123 内存泄漏
   - 临时方案:回滚到 v0.4.3
   - ETA 修复:2h
   - IC: @liuyifei
```

#### 外部 (GitHub Issue / Discussion)

```
⚠️ [Incident Report] macOS 14 启动 OOM

时间:2026-08-17 14:30 UTC
影响:macOS 14 + Apple Silicon 用户
状态:已发布 v0.4.4 修复版本
缓解:请升级到 v0.4.4 或回滚到 v0.4.3
根因:详见 #issue_num

如有问题请在本贴评论或发邮件到 liuyifeidashuaibi@gmail.com
```

---

## 三、事故复盘 / Postmortem

每个 SEV-1 / SEV-2 必须写 Postmortem,模板:

```markdown
---
incident_id: inc_2026_08_17_001
title: agentd 在 macOS 14 上 OOM
severity: SEV-2
status: resolved
start_time: 2026-08-17T14:30:00+08:00
end_time: 2026-08-17T16:45:00+08:00
duration: 2h15m
ic: 刘逸飞
commander: 刘逸飞
---

# Postmortem: agentd 在 macOS 14 上 OOM

## TL;DR
v0.5.0-rc.1 在 macOS 14 + Apple Silicon 上启动后 30-60s OOM。
v0.5.0-rc.0 不受影响。根因是新引入的 embedding 索引未设置 LRU 边界。

## 影响
- 用户数:估计 30%(macOS 14 + M1/M2 用户)
- 数据丢失:无
- API Key 泄露:无

## 时间线

| 时间 | 事件 |
| --- | --- |
| 14:30 | 用户 #42 报告 OOM |
| 14:35 | IC 接报,确认 SEV-2 |
| 14:50 | 复现成功,锁定 commit abc123 |
| 15:10 | 决定回滚 v0.4.3 |
| 15:30 | v0.4.3 镜像发布 |
| 16:00 | 用户报告问题解决 |
| 16:30 | 根因定位:embedding cache 无界 |
| 16:45 | 修复合并,v0.5.0-rc.2 发布 |

## 根因分析 (5 Whys)

1. **为什么 OOM?** 进程 RSS 涨到 8GB
2. **为什么涨到 8GB?** embedding 缓存持续增长
3. **为什么持续增长?** LRU 边界设为 `None` (无限)
4. **为什么设 None?** commit abc123 重构时漏改 default
5. **为什么没发现?** 单元测试 mock 了 embedding,集成测试只跑 5min 没暴露

## 修复

- [x] PR #1234: 显式设置 LRU maxsize=10000
- [x] 添加集成测试:模拟 1h 持续 embedding
- [x] 添加内存阈值监控:`runtime.max_memory_mb`

## 行动项 / Action Items

| 优先级 | 项 | 负责人 | 截止 |
| --- | --- | --- | --- |
| P1 | 加内存监控 | @liuyifei | 2026-08-20 |
| P1 | 集成测试加内存阈值断言 | @liuyifei | 2026-08-20 |
| P2 | 所有缓存组件统一 review | @liuyifei | 2026-09-01 |
| P3 | 增加 staging 环境(发布前实测 24h) | @liuyifei | 2026-10-01 |

## 学到的教训

1. **mock 容易掩盖问题** — 集成测试要覆盖真实资源消耗
2. **LRU 设 None 等于内存炸弹** — 默认必须有限界
3. **macOS 14 用户量大** — 必须在 release 前在 macOS 14 实测

## 致谢

感谢用户 #42 第一时间反馈。
```

存放路径:`docs/postmortems/YYYY-MM-DD-<short-title>.md`

---

## 四、安全事故专项 / Security Incidents

发现安全漏洞时,**不能**走常规流程,必须:

1. **不**在公开 Issue / Discussion 写漏洞细节
2. **立即**邮件 `liuyifeidashuaibi@gmail.com`(PGP 加密)
3. **72 小时**内决定 CVE 编号与修复时间线
4. **修复完成后 90 天**(或与 reporter 商定)再公开披露

完整流程见 [SECURITY.md](../../SECURITY.md)。

---

## 五、值班 / On-Call

由于项目为个人项目,**无正式 on-call 轮值**,但:

- Maintainer 收到 SEV-1 / SEV-2 邮件后,**24 小时内**响应
- 用户报告走 GitHub Issue,正常工作时间回复
- 严重安全漏洞 7×24 响应

未来若项目增长,会引入 PagerDuty / OpsGenie。

---

## 六、工具 / Tooling

| 用途 | 工具 |
| --- | --- |
| 监控 | Prometheus + Grafana |
| 日志 | 本地文件 + `fnix logs` |
| 错误聚合 | **不启用** Sentry / Rollbar |
| 告警 | GitHub Actions + Email |
| 通信 | GitHub Issue + Email |
| 文档 | `docs/postmortems/` |

---

## 七、/ References

- [Google SRE Book — Incident Management](https://sre.google/sre-book/managing-incidents/)
- [Atlassian Incident Handbook](https://www.atlassian.com/incident-management/handbook)
- [PagerDuty Incident Response](https://response.pagerduty.com/)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.