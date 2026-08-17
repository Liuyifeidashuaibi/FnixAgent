# 维护者入职手册 / Maintainer Onboarding

> 本文件指导新加入的维护者(本项目目前为单人项目,未来若扩大会用此文件)。

---

## 一、角色定义 / Roles

| 角色 | 权限 | 职责 |
| --- | --- | --- |
| **Owner** | 全部 | 项目战略 / 法律 / 发布 |
| **Core Maintainer** | 全部 (除删库 / 转让) | 架构决策 / 评审 / 发布 |
| **Maintainer** | PR 评审 / 合入 | 模块维护 / 用户支持 |
| **Triager** | Issue / Discussion | 问题分诊、贴标签 |

> 由于本项目为专有个人项目([LICENSE](../../LICENSE)),
> 上述角色划分仅在未来**潜在**扩编时使用。当前仅 Owner 一人。

---

## 二、加入流程 / Joining Process

### Step 1: 建立信任

- 过去 6 个月贡献 ≥ 20 个有意义的 PR
- PR 评审质量高,被标 `quality: high`
- 至少 1 位 Core Maintainer 提名
- 社区无负面争议

### Step 2: 提名

Maintainer 在私有频道(目前为 email)发起提名:

```
Subject: Nominate @user for Maintainer

@user 在过去 6 个月贡献了 [list]。
具体:
- [PR 1]: 解决了 ...
- [PR 2]: 重构了 ...
- 评审了 N 个 PR,平均响应 1.2d

提名 @user 成为 Maintainer。
```

### Step 3: 投票

需要 **所有** Core Maintainer 同意,Owner 一票否决权。

### Step 4: 授予权限

- 添加到 `.github/CODEOWNERS`
- 加入 `MAINTAINERS.md`
- 添加 GitHub Maintainer 权限
- 加入私有邮件列表

### Step 5: 公开宣布

在 GitHub Discussion 发"Welcome @user as Maintainer"。

---

## 三、初始任务清单 / First Tasks

新 Maintainer 加入后第一周:

- [ ] 阅读 [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [ ] 阅读 [docs/adr/](../adr/) 全部 5 个 ADR
- [ ] 阅读 [CONTRIBUTING.md](../../CONTRIBUTING.md)
- [ ] 阅读 [GOVERNANCE.md](../../GOVERNANCE.md)
- [ ] 阅读 [SECURITY.md](../../SECURITY.md)
- [ ] 阅读 [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md)
- [ ] 本地 build / run / test 全套跑通
- [ ] 评审 3 个已存在的 PR(找历史中的 PR,作为练习)
- [ ] 加入私有通讯渠道(邮件列表 / Discord)
- [ ] 自我介绍(Discussion / 邮件)
- [ ] 领取一个 `good first issue`(从 [Issue 列表](https://github.com/fnixagent/fnixagent/issues?q=label%3A%22good+first+issue%22)挑)

---

## 四、必读文档 / Required Reading

### 必读(优先级 1)

1. [LICENSE](../LICENSE.md)
2. [NOTICE](../NOTICE)
3. [README.md](../README.md)
4. [ARCHITECTURE.md](../ARCHITECTURE.md)
5. [SECURITY.md](../SECURITY.md)
6. [GOVERNANCE.md](../GOVERNANCE.md)

### 强烈推荐(优先级 2)

7. [docs/adr/](../adr/) — 所有架构决策
8. [docs/security/THREAT-MODEL.md](../security/THREAT-MODEL.md)
9. [docs/security/PRIVACY.md](../security/PRIVACY.md)
10. [docs/development/TESTING.md](../development/TESTING.md)
11. [docs/development/PERFORMANCE.md](../development/PERFORMANCE.md)
12. [docs/operations/REVIEWER-GUIDE.md](REVIEWER-GUIDE.md)
13. [docs/operations/INCIDENT-RESPONSE.md](INCIDENT-RESPONSE.md)

### 选择性(按模块)

14. [docs/development/PLUGINS.md](../development/PLUGINS.md)
15. [docs/development/I18N.md](../development/I18N.md)
16. [docs/development/ACCESSIBILITY.md](../development/ACCESSIBILITY.md)
17. [docs/INTEGRATIONS.md](../INTEGRATIONS.md)

---

## 五、决策权 / Decision Authority

### Maintainer 可自行决定

- 修 bug(无 API 变更)
- 优化(无 API 变更)
- 添加测试
- 文档修改
- 依赖小升级(同主版本)

### 需 Core Maintainer 批准

- 新增功能(影响 API)
- 重构核心模块
- 新增依赖
- 性能基准变化
- 重大依赖升级(主版本)

### 需 Owner 批准

- 修改 LICENSE
- 修改 GOVERNANCE
- 修改 CODE_OF_CONDUCT
- 转让项目所有权
- 关闭项目
- 法律相关决定

---

## 六、退出流程 / Offboarding

Maintainer 退出:

1. 提前 30 天公告
2. 转移手上活跃 PR / Issue
3. 从 `CODEOWNERS` / `MAINTAINERS.md` 移除
4. 撤销 GitHub 权限
5. 退出私有邮件列表
6. 公开感谢(可选)

紧急退出(如违反 CoC):

1. 立即撤销所有权限
2. 公开说明(不透露隐私)
3. 通知其他 Maintainer

---

## 七、通讯渠道 / Communication

由于项目为个人项目,主要通讯:

| 渠道 | 用途 |
| --- | --- |
| GitHub Issue | 公开 bug / 特性 |
| GitHub Discussion | 公开讨论 / 设计 |
| Email | 私下 / 安全 / 法务 |
| (未来) Discord | 实时 chat(若团队扩张) |

Maintainer 响应时间:

- Issue: 48h
- 安全邮件: 24h
- Discussion: 72h
- PR 评审: 24h

---

## 八、激励 / Incentives

由于本项目是个人作品集,**不**对外发放:

- ❌ 薪资
- ❌ 股权
- ❌ 现金奖励

可能的激励:

- ✅ GitHub 协作者身份
- ✅ 个人简历中可写"FnixAgent Maintainer"
- ✅ 在 CHANGELOG / Release Note 中致谢
- ✅ 推荐信(若 Maintainer 求职)
- ✅ 项目周边的优先体验权

---

## 九、参考 / References

- [Rust Governance](https://www.rust-lang.org/governance)
- [Kubernetes Community](https://www.kubernetes.dev/)
- [Python Steering Council](https://wiki.python.org/psc/)

---

© 2024-2026 FnixAgent. All Rights Reserved.