# 集成指南 / Integrations

> 如何把 FnixAgent 与第三方系统集成。

---

## 目录

- [LLM Providers](#llm-providers)
- [本地运行时](#本地运行时)
- [IDE / 编辑器](#ide--编辑器)
- [CI / CD](#ci--cd)
- [数据源](#数据源)
- [消息渠道](#消息渠道)
- [自定义工具](#自定义工具)

---

## LLM Providers

###  LLM

**配置**:

```yaml
# config/agentd.yaml
llm:
  providers:
    openai:
      type: openai_compat
      base_url: https://api.openai.com/v1
      api_key_ref: keychain:openai  # 从 OS Keychain 读
      default_model: gpt-4o
      models:
        gpt-4o:
          input_cost_per_1k: 0.0025
          output_cost_per_1k: 0.01
        gpt-4o-mini:
          input_cost_per_1k: 0.00015
          output_cost_per_1k: 0.0006
```

**API Key**:

```bash
fnix key set --provider=openai
# 输入 sk-... → 存入 OS Keychain
```

###

```yaml
llm:
  providers:
    anthropic:
      type: anthropic_native
      base_url: https://api.anthropic.com
      api_key_ref: keychain:anthropic
      default_model: claude-sonnet-4-5
```

### DeepSeek

```yaml
llm:
  providers:
    deepseek:
      type: openai_compat
      base_url: https://api.deepseek.com/v1
      api_key_ref: keychain:deepseek
      default_model: deepseek-chat
```

### 通义千问 / Qwen

```yaml
llm:
  providers:
    qwen:
      type: dashscope
      base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
      api_key_ref: keychain:qwen
      default_model: qwen-max
```

### 自定义  LLM 兼容端点(OneAPI / LiteLLM / vLLM)

```yaml
llm:
  providers:
    vllm_local:
      type: openai_compat
      base_url: http://127.0.0.1:8000/v1
      api_key_ref: ""  # 不需要
      default_model: meta-llama/Llama-3-70b
```

---

## 本地运行时

### 本地推理引擎

**安装**:参见本地推理引擎官方文档

**配置**:

```yaml
llm:
  providers:
    local-llm:
      type: local-llm
      base_url: http://127.0.0.1:11434
      default_model: qwen2.5-coder:7b
      keep_alive: 30m
      num_ctx: 4096
      num_gpu: 1
```

**拉模型**:

```bash
local-llm pull qwen2.5-coder:7b
local-llm pull llama3.1:8b
local-llm pull bge-small-zh  # embedding
```

### 本地推理引擎

**安装**:https://local-llm.ai/

本地推理引擎 启动  LLM 兼容服务:

```yaml
llm:
  providers:
    local-llm:
      type: openai_compat
      base_url: http://127.0.0.1:1234/v1
      default_model: loaded-model-identifier
```

### llama.cpp

```yaml
llm:
  providers:
    llamacpp:
      type: openai_compat
      base_url: http://127.0.0.1:8080/v1
      default_model: local-model
```

---

## IDE / 编辑器

### VS Code

**方式 1:装 FnixAgent Workbench 扩展**(本仓库提供)

```bash
code --install-extension ./apps/workbench/vsix/fnixagent-workbench-0.5.0.vsix
```

**方式 2:用 MCP 协议**

VS Code 1.86+ 支持 MCP,在 `settings.json`:

```json
{
  "mcp.servers": {
    "fnixagent": {
      "command": "fnixagent",
      "args": ["mcp", "serve", "--port=7891"]
    }
  }
}
```

### JetBrains IDEs

Settings → Plugins → Marketplace → 搜 "FnixAgent"

### Vim / Neovim

```vim
" ~/.vimrc
nnoremap <Leader>f :!fnixagent prompt --editor-mode<CR>
```

### Emacs

```elisp
;; ~/.emacs
(defun fnixagent-send-region ()
  (interactive)
  (shell-command (concat "fnixagent prompt --editor-mode --input="
                         (shell-quote-argument (buffer-substring (region-beginning) (region-end))))))
(global-set-key (kbd "C-c f") 'fnixagent-send-region)
```

---

## CI / CD

### GitHub Actions

```yaml
# .github/workflows/agent-review.yml
name: Agent Code Review
on: [pull_request]

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run FnixAgent Review
        uses: Liuyifeidashuaibi/FnixAgent-action@v1
        with:
          task: review-diff
          llm-provider: openai
          api-key: ${{ secrets.OPENAI_API_KEY }}
```

### GitLab CI

```yaml
# .gitlab-ci.yml
agent-review:
  image: fnixagent/agentd:latest
  script:
    - fnixagent task run review-diff --input ./diff.patch
  only:
    - merge_requests
```

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/Liuyifeidashuaibi/pre-commit-hooks
  rev: v1.0.0
  hooks:
    - id: fnixagent-lint
    - id: fnixagent-secrets-scan
```

---

## 数据源

### GitHub

```yaml
integrations:
  github:
    type: github
    token_ref: keychain:github_token
    repos:
      - Liuyifeidashuaibi/FnixAgent
    events:
      - issues
      - pull_request
```

启用后,FnixAgent 可读取 Issue / PR 内容并辅助回复。

### Linear

```yaml
integrations:
  linear:
    type: linear
    api_key_ref: keychain:linear
    team: ENG
```

### Notion

```yaml
integrations:
  notion:
    type: notion
    integration_token_ref: keychain:notion
    workspace: "My Workspace"
```

### Obsidian Vault

```yaml
integrations:
  obsidian:
    type: filesystem
    vault_path: ~/Documents/ObsidianVault
    read_only: true
    watch_for_changes: true
```

Agent 可读你的笔记,作为长期记忆的补充。

---

## 消息渠道

### Slack

```yaml
channels:
  slack:
    type: slack
    bot_token_ref: keychain:slack_bot
    channels:
      - "#agent-alerts"
```

### Discord

```yaml
channels:
  discord:
    type: discord
    bot_token_ref: keychain:discord_bot
    webhook_url: https://discord.com/api/webhooks/...
```

### Email (SMTP)

```yaml
channels:
  email:
    type: smtp
    smtp_host: smtp.gmail.com
    smtp_port: 587
    username: your@gmail.com
    password_ref: keychain:email_password
```

---

## 自定义工具

### 1. 本地脚本 Skill

```bash
# ~/.fnix/skills/git-status/SKILL.md
mkdir -p ~/.fnix/skills/git-status
```

参见 `docs/development/PLUGINS.md`。

### 2. Python 工具

```python
# ~/.fnix/skills/my_tool.py
from fnixagent.tools import tool

@tool(name="my_tool", description="My custom tool")
async def my_tool(query: str) -> str:
    """Process query."""
    return f"Processed: {query}"
```

### 3. HTTP API Skill

```yaml
# ~/.fnix/skills/http-api/SKILL.md
---
skill: http-api
type: http
endpoint: https://api.example.com/v1
auth:
  type: bearer
  token_ref: keychain:example_api
---
```

### 4. MCP 协议服务器

```yaml
integrations:
  my_mcp:
    type: mcp_server
    command: python
    args: ["/path/to/my_mcp_server.py"]
    transport: stdio
```

---

## 故障排查

集成失败?先查:

1. **API Key**:`fnix key list` 看是否已配
2. **网络**:`fnix network test --provider=openai`
3. **日志**:`fnix logs --filter=integration`

更多见 `docs/operations/TROUBLESHOOTING.md`。

---

© 2024-2026 FnixAgent. All Rights Reserved.