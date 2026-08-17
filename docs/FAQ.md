# FnixAgent FAQ — 常见问题

> 📌 **速查清单 / Quick Reference**
> 1. 安装问题 → `docs/INSTALL.md` + `install.ps1` / `install.sh`
> 2. 故障排查 → `docs/operations/TROUBLESHOOTING.md`
> 3. 隐私 / 数据 → `SECURITY.md` + `docs/security/PRIVACY.md`
> 4. 商用授权 → `LICENSE-COMMERCIAL.md`

---

## 一、项目定位 / Project

### Q1. FnixAgent 是什么?

A. FnixAgent 是一个**本地优先 (Local-First)** 的桌面 Agent 工作台,用
   **Tauri 2 + Python + Rust** 构建。它能在你的电脑上跑本地 LLM
   (本地 LLM),也能通过 BYOK 调用云端 LLM ( LLM /
    / DeepSeek),同时具备长期记忆、技能调用、三层任务图规划。

### Q2. 与  / Continue / Cline 的差别?

| 维度 |  | Continue | Cline | FnixAgent |
| --- | --- | --- | --- | --- |
| 形态 | IDE | 插件 | 插件 | **桌面 App** |
| 多模态 | 仅代码 | 仅代码 | 仅代码 | **代码+文档+日常** |
| 记忆 | 短时 | 短时 | 短时 | **长期记忆 (Markdown+Git)** |
| 任务图 | 无 | 无 | 无 | **KTG/STP/MFP 三层** |
| 隐私 | 上云 | 上云 | 上云 | **BYOK + 全本地** |
| 商用授权 | 闭源 | 闭源 | Apache | **All Rights Reserved (专有)** |

详见 `docs/COMPARISON.md`。

### Q3. 为什么要写 FnixAgent?

A. 构建一个完整落地的桌面 Agent 工程:覆盖**架构设计 / 跨语言协同 /
 本地优先工程 / 开源治理**全链路。

### Q4. 这个项目是开源的吗?

A. **否**。本项目以 **All Rights Reserved** 方式发布,具体见 [LICENSE](../LICENSE)。
   GitHub 上**可以浏览**,但**禁止**复制、修改、商用、Fork、衍生创作,
   也**不接受**社区代码合入。

### Q5. 我可以看你的代码学习吗?

A. 在浏览器里**阅读**单个文件、提交 GitHub Issue 提问、在 GitHub
   Discussion 中讨论 — 这些都是允许的(详见 LICENSE 中的 "View-Only
   License" 章节)。
   但请**不要**复制源码到本地,也不要基于本项目 fork / 衍生创作。
   如果你想做类似项目,请**凭自己理解写自己的代码**,不要直接搬运。

### Q6. 我能商用 FnixAgent 吗?

A. **不能**。如确有商用需求,请联系 `liuyifeidashuaibi@gmail.com`,详
   见 [LICENSE-COMMERCIAL.md](../LICENSE-COMMERCIAL.md)。

---

## 二、安装与启动 / Install & Run

### Q7. 我的电脑能跑吗?

A. 系统要求:
   - **Windows**:Windows 10 1809+,已装 WebView2 Runtime(Win11 自带)
   - **macOS**:macOS 11 Big Sur+,Intel / Apple Silicon
   - **Linux**:Ubuntu 22.04+ / Fedora 38+,需 WebKitGTK 4.1+
   - **内存**:≥ 8 GB (跑本地 7B 模型建议 ≥ 16 GB)
   - **磁盘**:≥ 5 GB 可用(含 LLM 模型)

### Q8. 安装命令是什么?

A. 一键安装(自动检测环境 + 安装依赖):

```powershell
# Windows PowerShell
irm https://raw.githubusercontent.com/Liuyifeidashuaibi/FnixAgent/main/install.ps1 | iex

# 或本仓库
.\install.ps1
```

```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/Liuyifeidashuaibi/FnixAgent/main/install.sh | bash

# 或本仓库
./install.sh
```

### Q9. 启动后空白怎么办?

A. 见 `docs/operations/TROUBLESHOOTING.md#a1-启动后白屏`。

### Q10. 端口冲突怎么办?

A. agentd 默认 `127.0.0.1:7891`。修改:

```yaml
# config/agentd.yaml
server:
  host: 127.0.0.1
  port: 7891  # 改成可用端口
```

---

## 三、配置 / Configuration

### Q11. 怎么配 API Key?

A. 三种方式(任选其一):

1. **OS Keychain (推荐)**:首次启动时弹出对话框,输入后自动存储
2. **加密便携文件**:`fnix key set --provider=openai --mode=encrypted`
3. **环境变量**:`export OPENAI_API_KEY=sk-...` (开发用)

详细见 `docs/INTEGRATIONS.md`。

### Q12. 怎么切到本地 LLM?

A. 安装本地 LLM 后,`config/agentd.yaml`:

```yaml
llm:
  default_provider: local-llm
  providers:
    local-llm:
      base_url: http://127.0.0.1:11434
      model: qwen2.5-coder:7b
```

### Q13. 怎么禁用遥测?

A. 默认就**不上传任何遥测**。如果你误装了 fork 版本担心,可在
   `config/agentd.yaml` 设置:

```yaml
telemetry:
  enabled: false
  block_all_outbound: true  # 硬阻断所有出站请求
```

---

## 四、使用 / Usage

### Q14. 怎么让 Agent 记住我?

A. 三种方式:

1. 直接说:"记住:我喜欢 Rust 类型系统胜过 Go 的 interface"
2. 写到项目根 `.fnix/rules.md`,Agent 会自动加载
3. 在 UI 的 "Memory" 面板手动添加

记忆默认存 `~/.fnix/memory/`,可手动 git 备份。

### Q15. Skill 怎么写?

A. 见 `docs/development/PLUGINS.md`。一个最小 Skill 示例:

```markdown
---
skill: my-skill
version: 1.0.0
inputs:
  - name: query
    type: string
---

# My Skill

按 ${query} 进行处理...

## Instructions
1. 解析 query
2. 返回结构化结果

## Output Schema
{ "result": "string" }
```

### Q16. 怎么回滚 Agent 的一个错误决定?

A. 三层任务图任意层都可手动干预:
- 打开 "Plan" 面板 → 找到节点 → 点击 "×" 删除
- 在 MFP 层可强制 "Skip" 或 "Retry"

---

## 五、故障 / Troubleshooting

### Q17. agentd 起不来?

A. 见 `docs/operations/TROUBLESHOOTING.md#a3-agentd-启动失败`。

### Q18. LLM 响应慢?

A. 见 `docs/development/PERFORMANCE.md`。

### Q19. 占用内存高?

A. 默认限制:`workers=2`, `max_context_tokens=8192`。调小:

```yaml
runtime:
  workers: 1
  max_context_tokens: 4096
```

---

## 六、安全 / Security

### Q20. 数据会离开我电脑吗?

A. **不会**,除非你主动调用云端 LLM。
   - 本地 LLM:零出站
   - 云端 LLM:仅发送你输入的 prompt 和必要的元数据(模型版本号、token 数)
   - 永远不上传:文件系统内容、API Key、记忆、对话历史

详细审计见 `docs/security/THREAT-MODEL.md`。

### Q21. 发现漏洞怎么报?

A. 见 [SECURITY.md](../SECURITY.md),**不要在公开 Issue 里写漏洞细节**。

---

## 七、贡献 / Contributing

### Q22. 我能贡献代码吗?

A. 本项目不接受外部代码贡献。所有代码均为著作权人独立完成。
   你可以在 GitHub 上**提 Issue 讨论设计**、提文档改进建议,但代码贡献
   不接受合并,因为合入即意味着放弃版权,与 [LICENSE](../LICENSE) 冲突。

详细见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

---


> 📮 没找到答案?提 Issue: https://github.com/Liuyifeidashuaibi/FnixAgent/issues/new/choose

© 2024-2026 FnixAgent. All Rights Reserved.