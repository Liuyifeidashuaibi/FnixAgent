# PR 评审指南 / Reviewer Guide

> 本文件是 FnixAgent 代码评审的标准化指南,**仅供维护者本人参考**。
> (本项目不接受外部代码贡献 — 见 [LICENSE](../../LICENSE) 与 [CONTRIBUTING.md](../../CONTRIBUTING.md))

---

## 一、评审原则 / Principles

### 1.1 友好但严格

- **礼貌**:提问而非指责
- **直接**:指出问题,不绕弯
- **及时**:工作时间内 24h 内首响应
- **彻底**:不放过真正的问题

### 1.2 关注点

评审顺序(从重到轻):

1. **正确性**:逻辑是否正确
2. **安全性**:是否引入漏洞
3. **性能**:是否显著退化
4. **可维护性**:未来改动是否容易
5. **测试**:是否充分
6. **文档**:是否同步更新
7. **风格**:lint / format

### 1.3 不是评审什么

- ❌ 不是代码风格警察(让 CI 做)
- ❌ 不是改名建议机器
- ❌ 不是 PR 阻塞者

---

## 二、评审清单 / Checklist

### 2.1 通用

- [ ] PR 标题符合 Conventional Commits(`feat:`, `fix:`, `docs:`, ...)
- [ ] PR 描述含"为什么",不只是"做了什么"
- [ ] 单 PR 不超过 400 行变更(超出请拆分)
- [ ] 没有遗留 `console.log` / `print` / `dbg!`
- [ ] 没有遗留 TODO / FIXME(必须 issue 化)
- [ ] 没有引入破坏性变更,如不可避免则 ADR

### 2.2 安全

- [ ] 没有硬编码密钥、token、密码
- [ ] 没有引入新依赖未经审查(评估维护、漏洞、license)
- [ ] 用户输入经过校验
- [ ] 文件路径经过沙箱检查
- [ ] IPC 命令经过 capability 检查
- [ ] SQL 用了参数化(不拼接)
- [ ] HTML 用了 React 转义(不用 dangerouslySetInnerHTML)

### 2.3 性能

- [ ] 没有 N+1 查询
- [ ] 大量循环用生成器/向量
- [ ] LLM 调用没在循环里串行(应 gather)
- [ ] 大文件流式读取(不一次性 load)
- [ ] 缓存用了 LRU 边界(无 None)

### 2.4 可维护性

- [ ] 函数不超过 50 行(超长请拆)
- [ ] 文件不超过 500 行(超大请拆)
- [ ] 没有过度抽象(避免 YAGNI)
- [ ] 没有魔法数字(常量命名)
- [ ] 公共 API 有文档字符串

### 2.5 测试

- [ ] 新功能有测试
- [ ] bug 修复有回归测试
- [ ] 覆盖率不下降
- [ ] 测试不依赖外部资源(must mock)
- [ ] 测试确定性(不依赖时间、网络)

### 2.6 文档

- [ ] API 变更更新 `API.md`
- [ ] 配置变更更新示例
- [ ] ADR 记录架构决策
- [ ] CHANGELOG 更新

---

## 三、评审语言 / Communication

### 3.1 评论分类前缀

| 前缀 | 含义 | 处理 |
| --- | --- | --- |
| `blocking:` | 必须解决才能合 | 作者改 |
| `important:` | 强烈建议改 | 作者改 / 解释 |
| `nit:` | 小问题(拼写/格式) | 可忽略 |
| `question:` | 提问 | 作者回答 |
| `praise:` | 表扬 | 不需要回复 |
| `suggestion:` | 建议 | 作者考虑 |
| `discuss:` | 通用讨论 | 后续聊 |

示例:

```
blocking: 这里 fs.read 没有验证 path 是否在白名单内,请加上 `path_guard.check()`。
important: 建议把 magic number 100 提成常量 `MAX_RETRIES`。
nit: 拼写错误 "recieve" → "receive"
question: 为什么这里用 dict 而不是 dataclass?
praise: 这个错误处理很优雅!
```

### 3.2 LGTM 文化

合并前至少 1 个 `LGTM`(Looks Good To Me)。

格式:
```
LGTM 🚀

blocking: 已修复
important: 已处理,见 f8a3c12
```

---

## 四、特殊场景 / Edge Cases

### 4.1 大型重构 (>1000 行)

- 必须先开 Issue 讨论设计
- 拆分多个小 PR,每个 < 400 行
- 在 RFC / ADR 中记录决策

### 4.2 安全敏感变更

- 至少 2 人 review
- 必须有 threat model 更新
- 单独评审会话,不开盲合

### 4.3 依赖升级

- 检查 changelog
- 运行完整测试
- 在 PR 描述里贴 diff
- 评估 lockfile 大小变化

### 4.4 Breaking Change

- 必须新增 ADR
- 提供 migration guide
- CHANGELOG 标注 `💥 BREAKING`
- 提前至少 1 个 minor 预告

---

## 五、自评模板 / Self-Review Template

PR 作者提交前先自己填:

```markdown
## Self-Review Checklist

### 做了什么
- ...

### 怎么测的
- [ ] 单元测试
- [ ] 集成测试
- [ ] 手动测试 (mvp / win / linux)
- [ ] 性能测试 (如适用)

### 评审重点
请评审者重点看:
- `src/foo.rs` 的边界条件处理
- `tests/test_foo.py` 的 mock 真实性

### 已知局限
- 没有覆盖的边角场景:...

### 后续 TODO
- (issue 链接)
```

---

## 六、SLA / Response Time

| 严重度 | 首响应 | 决定 |
| --- | --- | --- |
| SEV-1 | 15 min | 立即评审 |
| SEV-2 | 1 h | 当天评审 |
| 普通 PR | 24 h | 1-3 天 |
| 文档 PR | 48 h | 1 周 |

---

## 七、参考 / References

- [Google Engineering Practices — Code Review](https://google.github.io/eng-practices/review/)
- [Conventional Comments](https://conventionalcomments.org/)
- [GitHub — Reviewing changes](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests)

---

© 2024-2026 FnixAgent. All Rights Reserved.