# 迁移指南 / Migration Guide

> 从旧版本升级或从其他工具迁移到 FnixAgent 的指南。

---

## 目录

- [从 FnixAgent 旧版本升级](#从-fnixagent-旧版本升级)
- [从 Continue / Cline 迁移配置](#从-continue--cline-迁移配置)
- [从  迁移](#从-aider-迁移)
- [从 LangChain / LlamaIndex 应用迁移](#从-langchain--llamaindex-应用迁移)
- [数据迁移(换电脑)](#数据迁移换电脑)

---

## 从 FnixAgent 旧版本升级

### v0.4 → v0.5 (2026-08-17)

**Breaking Changes**:

1. `~/.fnix/memory/` 目录结构升级
2. `config.yaml` 字段重命名:`agent.llm` → `llm.default_provider`
3. Python SDK API 从同步改为全异步

**迁移步骤**:

```bash
# 1. 升级安装
fnixagent update --to v0.5

# 2. 自动迁移(会备份 ~/.fnix 到 ~/.fnix.bak-YYYYMMDD)
fnixagent migrate --from v0.4 --to v0.5

# 3. 手动校对
diff ~/.fnix/config.yaml ~/.fnix.bak-YYYYMMDD/config.yaml

# 4. 重启
fnixagent restart
```

**API 变化示例**:

```python
# v0.4
from fnixagent import Agent
agent = Agent(provider="openai")
result = agent.run("hello")

# v0.5
import asyncio
from fnixagent import Agent
agent = Agent(provider="openai")
result = await agent.run("hello")  # 必须 await
```

### v0.5 → v0.6 (计划中)

无 breaking change,仅新增:
- `KTG` 知识任务图层
- 协作模式(多个 Agent 协同)

---

## 从 Continue / Cline 迁移配置

### 1. 导出 Continue 配置

```bash
# Continue 配置通常在 ~/.continue/
cp ~/.continue/config.json ~/continue-config.json
```

### 2. 转换为 FnixAgent 格式

```bash
fnixagent migrate-config \
  --from continue \
  --input ~/continue-config.json \
  --output ~/.fnix/config.yaml
```

### 3. 字段映射

| Continue 字段 | FnixAgent 字段 |
| --- | --- |
| `models[].provider` | `llm.providers.<name>` |
| `models[].apiKey` | OS Keychain (BYOK) |
| `systemMessage` | `prompts.system` |
| `tabSize` | `editor.tab_size` |
| `slashCommands[].name` | `skills.<name>` |

### 4. Slash Command → Skill

Continue 的 Slash Command 转换为 Skill:

```bash
fnixagent migrate-slash-commands \
  --continue-dir ~/.continue/prompts/ \
  --output ~/.fnix/skills/
```

转换不是 100% 等价,**核心 prompt 需要人工 review**。

---

## 从  迁移

### 1. 提取 `~/.aider.conf.yml`

```yaml
# aider.conf.yml → fnix-agent.yaml
model: gpt-4o                → llm.providers.openai.model: gpt-4o
weak-model: gpt-4o-mini      → llm.providers.openai.weak_model: gpt-4o-mini
api-key: sk-...              → (删除,改用 Keychain)
auto-commits: true           → git.auto_commit: true
```

### 2. `.aiderignore` → `.fnixignore`

```gitignore
# aider
node_modules/
dist/
*.min.js

# fnix (兼容格式,几乎一致)
node_modules/
dist/
*.min.js
```

直接重命名即可:`mv .aiderignore .fnixignore`

### 3. Conversation 历史

 历史是 `~/.aider.chat.history.md`,无法自动迁移。
可手动浏览后挑选重要对话,粘到 FnixAgent 的 "Memory" 面板。

---

## 从 LangChain / LlamaIndex 应用迁移

### 概念映射

| LangChain | LlamaIndex | FnixAgent |
| --- | --- | --- |
| `AgentExecutor` | `ReActAgent` | `MFPRunner` (MFP) |
| `Tool` | `QueryEngineTool` | `Skill` |
| `Memory` | `ChatMemoryBuffer` | `MemoryBackend` (多类型) |
| `VectorStore` | `VectorStoreIndex` | `sqlite-vec` |
| `Chain` | `QueryPipeline` | `STP` 计划 |

### 示例:LangChain ReAct → FnixAgent Skill

**LangChain**:

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import tool

@tool
def search(query: str) -> str:
    """Search for query."""
    return google_search(query)

agent = create_react_agent(llm, [search], prompt)
executor = AgentExecutor(agent=agent, tools=[search])
result = executor.invoke({"input": "今天天气?"})
```

**FnixAgent Skill** (`.fnix/skills/search/SKILL.md`):

```markdown
---
skill: search
version: 1.0.0
tools:
  - search
inputs:
  - name: query
    type: string
---

# Search Skill

## Instructions
调用 ${search} 工具搜索 ${query}。

## Output
返回 top-3 结果,markdown 格式。
```

**调用**:

```python
from fnixagent import Agent
agent = Agent(provider="openai")
result = await agent.run("今天天气?", skills=["search"])
```

---

## 数据迁移(换电脑)

### 场景:Windows → macOS

#### 步骤 1:在旧机器备份

```powershell
fnixagent backup --output D:\fnix-backup.tar.gz
```

#### 步骤 2:把备份文件拷到新机器

#### 步骤 3:在新机器恢复

```bash
fnixagent restore --input ~/Downloads/fnix-backup.tar.gz
```

### 包含什么

- `~/.fnix/memory/` (记忆)
- `~/.fnix/skills/` (技能)
- `~/.fnix/config.yaml` (配置)
- `~/.fnix/keystore.enc` (加密凭据)
- **不包含**:LLM 模型(太大,按需单独下载)

### API Key 怎么办?

#### 模式 A(OS Keychain)

**不能跨平台迁移**。需要重新输入。

#### 模式 B(加密便携文件)

`keystore.enc` 可以直接拷过去,**但需要同样的 master password** 才能解密。

```bash
# 旧机器导出
fnixagent key export --output ~/keystore-encrypted.json

# 新机器导入
fnixagent key import --input ~/keystore-encrypted.json
```

---

## 故障:迁移后问题

### "Memory schema 不兼容"

```bash
fnix memory upgrade-schema --target v5
```

### "Skill 加载失败"

```bash
fnix skill validate --all
fnix skill doctor
```

### 配置文件被改字段名

```bash
fnix config lint --fix
```

---

## 寻求帮助

- 📖 本文档未覆盖?提 Issue
- 💬 紧急问题:`liuyifeidashuaibi@gmail.com`(请勿发敏感信息)

© 2024-2026 FnixAgent. All Rights Reserved.