# SampleFlawedAgent — FnixForge 演示靶子

一个**故意带着 5 类典型缺陷**的半成品 Agent，用于演示 FnixForge 的
「测评 → 诊断 → 自动修复 → 复测」完整闭环。

故意埋下的缺陷：

1. 写文件时附带"已完成任务。"等解释性前缀 —— 违背精确输出契约
2. 每次运行都在沙箱里乱写 `agent.log` —— 作用域越界
3. "去重排序"只去重不排序 —— 中文指令理解不精确
4. 统计任务写"一共有 4 行"而不是纯数字 `4` —— 输出格式不遵守契约
5. 不认识的任务直接放弃 —— 能力覆盖不足

## 用法

```bash
# 看看它能得几分（只测不改）
fnixagent forge test benchmarks/forge/sample-agent --suite core

# 让 FnixForge 自动修到生产级
fnixagent forge fix benchmarks/forge/sample-agent --suite core --rounds 3 --report report

# 生成后打开 report.html 查看能力矩阵和各轮迭代
```

修复由 FnixAgent 的 LLM 完成（需要 `fnixagent setup` 配置好 API Key），
修复历史以 git commit 记录，任何引入回归的修复会被自动回滚。
