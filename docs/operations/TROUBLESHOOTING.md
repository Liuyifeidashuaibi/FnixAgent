# 故障排查手册 / Troubleshooting Guide

> 📌 找不到解决方案?在 GitHub Issue 用模板 `template=bug.md` 提交。

---

## 目录 / Contents

- [A. 安装问题](#a-安装问题)
- [B. 启动问题](#b-启动问题)
- [C. LLM 调用问题](#c-llm-调用问题)
- [D. 记忆与 Skill 问题](#d-记忆与-skill-问题)
- [E. UI 问题](#e-ui-问题)
- [F. 网络 / 代理问题](#f-网络--代理问题)
- [G. 性能问题](#g-性能问题)
- [H. 升级 / 回滚](#h-升级--回滚)
- [I. 数据恢复](#i-数据恢复)
- [J. 日志收集](#j-日志收集)

---

## A. 安装问题

### A1. `install.ps1` 提示"无法加载,因为在此系统上禁止运行脚本"

**原因**:PowerShell 执行策略限制。

**解决**(管理员 PowerShell):
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
irm https://raw.githubusercontent.com/Liuyifeidashuaibi/FnixAgent/main/install.ps1 | iex
```

### A2. macOS 提示"无法打开,因为无法验证开发者"

**解决**:
```bash
xattr -d com.apple.quarantine /Applications/FnixAgent.app
```

或在 系统设置 → 隐私与安全性 → 仍要打开。

### A3. Linux 提示缺 WebKitGTK

**Ubuntu / Debian**:
```bash
sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev
```

**Fedora**:
```bash
sudo dnf install -y webkit2gtk4.1-devel gtk3-devel libappindicator-gtk3-devel librsvg2-devel
```

### A4. `cargo build` 失败:linker not found

**Ubuntu / Debian**:
```bash
sudo apt install -y build-essential pkg-config libssl-dev
```

---

## B. 启动问题

### B1. 启动后白屏 / 长时间转圈

**可能原因 + 排查**:

```bash
# 1. 检查 agentd 是否在运行
curl http://127.0.0.1:7891/v1/health

# 2. 看 agentd 日志
tail -f ~/.fnix/logs/agentd.log

# 3. 打开浏览器开发者工具(F12),看 Console 面板有没有红色错误
```

**常见原因**:
- WebView2 没装(Win10 1809 以下)
- agentd 端口被占用
- 首次启动正在下载 embedding 模型,需要 60-120s

### B2. "agentd 启动失败:端口 7891 已被占用"

```bash
# Windows
netstat -ano | findstr :7891
taskkill /PID <PID> /F

# macOS / Linux
lsof -i :7891
kill -9 <PID>
```

或修改 `config/agentd.yaml`:
```yaml
server:
  port: 7892  # 改成空闲端口
```

### B3. "Failed to create Tauri runtime"

**Linux**:
```bash
sudo apt install -y libxdo-dev
```

**macOS**:确认 Xcode Command Line Tools 已装
```bash
xcode-select --install
```

### B4. 启动后立刻退出

**检查 crash dump**:
```bash
# Windows
%LOCALAPPDATA%\fnixagent\logs\crashpad\reports\

# macOS
~/Library/Logs/FnixAgent/

# Linux
~/.local/share/fnixagent/logs/
```

---

## C. LLM 调用问题

### C1. "Connection refused" 调用本地 本地推理引擎

```bash
# 1. 确认 本地推理引擎 在跑
local-llm serve

# 2. 确认端口可达
curl http://127.0.0.1:11434/api/tags

# 3. 检查 config
grep base_url config/agentd.yaml
```

### C2. "401 Unauthorized" 云端 LLM

**可能原因**:
- API Key 未配置或失效
- 余额不足

**排查**:
```bash
# 测试  LLM
curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models

# 测试
curl -H "x-api-key: $ANTHROPIC_API_KEY" https://api.anthropic.com/v1/models
```

### C3. "Rate limit exceeded"

**解决**:
- 升级 API 套餐
- 或切换其他 provider:`fnix config llm.default_provider=anthropic`
- 或启用 fallback 链:`config/agentd.yaml`:

```yaml
llm:
  fallback:
    - openai
    - anthropic
    - local-llm
```

### C4. LLM 响应很慢

**可能原因**:
- 本地模型加载中
- 云端 API 拥堵

**优化**:
```yaml
llm:
  providers:
    local-llm:
      num_ctx: 4096       # 减少上下文
      num_gpu: 1          # 用 GPU
      keep_alive: "30m"   # 模型保留
```

---

## D. 记忆与 Skill 问题

### D1. Agent 不记得我说过的话

**排查**:
1. 检查 `~/.fnix/memory/` 目录是否存在
2. 检查最近 7 天有没有 episodic 记录:`ls ~/.fnix/memory/episodic/`
3. 检查 embedding 索引:`sqlite3 ~/.fnix/memory/semantic/index.sqlite ".tables"`

**修复**:
```bash
fnix memory rebuild-index
```

### D2. Skill 不被识别

**排查**:
```bash
# 1. 看 skill 是否在路径
ls ~/.fnix/skills/

# 2. 检查 frontmatter 是否合法
fnix skill validate ~/.fnix/skills/my-skill/SKILL.md

# 3. 重载
fnix skill reload
```

### D3. 记忆里有敏感信息,想删除

```bash
# 删除单条
fnix memory delete --id mem_2026_08_15_001

# 删除某用户所有记忆
fnix memory purge --user "刘逸飞"

# 完全重置(谨慎)
fnix memory reset --confirm
```

---

## E. UI 问题

### E1. 字体显示异常

**Windows**:
```powershell
irm https://github.com/Liuyifeidashuaibi/FnixAgent/fonts/install.ps1 | iex
```

**macOS**:系统设置 → 字体 → 下载 `Sarasa Mono SC`、`PingFang SC`

### E2. 中文乱码

**Linux**:
```bash
sudo apt install -y fonts-noto-cjk fonts-noto-cjk-extra
fc-cache -fv
```

### E3. 主题色没切换

强制刷新:`Ctrl+Shift+R` (Windows / Linux) / `Cmd+Shift+R` (macOS)

### E4. WebView2 报错 "0x80072EE7"

**Win10 1809 以下**:安装 WebView2 Runtime
```powershell
winget install Microsoft.EdgeWebView2Runtime
```

---

## F. 网络 / 代理问题

### F1. 走公司代理

`config/agentd.yaml`:
```yaml
network:
  http_proxy: http://proxy.corp.example.com:8080
  https_proxy: http://proxy.corp.example.com:8080
  no_proxy: 127.0.0.1,localhost
```

### F2. Tauri 内部请求被代理拦截

Tauri Rust 侧不走系统代理,需要:

```rust
// src-tauri/src/lib.rs
tauri::Builder::default()
    .setup(|app| {
        let proxy = reqwest::Proxy::http("http://proxy:8080")?;
        // ...
    })
```

(详见 ADR-0001)

### F3. SSL 证书错误

开发期临时绕过(不推荐):
```yaml
network:
  insecure_skip_verify: true  # 仅 DEBUG 用
```

正确做法:把公司 CA 证书导入系统信任链。

---

## G. 性能问题

### G1. 内存占用 > 1 GB

```yaml
runtime:
  workers: 1                # 并发 worker 减少
  max_context_tokens: 4096  # 上下文减半
  gc_interval: 100          # GC 频率提高
```

### G2. CPU 占用 100%

可能 LLM 死循环。强制 kill:
```bash
fnix task cancel --all
```

### G3. 启动 > 30s

**检查**:
```bash
time fnixagent start
```

**优化**:
- 减少 skill 数量(> 50 个 skill 时启动会慢)
- 预编译 embedding 索引

---

## H. 升级 / 回滚

### H1. 升级到最新版本

```bash
fnixagent update
```

### H2. 回滚到上一版本

```bash
# 查看已装版本
fnixagent history

# 回滚
fnixagent rollback v1.2.3
```

### H3. 升级后报错

```bash
# 1. 看 changelog
cat CHANGELOG.md | head -100

# 2. 跑 migration
fnixagent migrate

# 3. 还不工作 → 回滚 + 提 Issue
fnixagent rollback
```

---

## I. 数据恢复

### I1. 记忆损坏 / 误删

记忆是 Git 仓库,直接 git:
```bash
cd ~/.fnix/memory
git log --oneline                  # 找健康版本
git checkout <commit-hash> -- .   # 回滚
```

### I2. 配置文件损坏

```bash
# 配置有备份
cp ~/.fnix/config.yaml.bak ~/.fnix/config.yaml
```

### I3. 完整数据迁移到新电脑

```bash
# 旧机器
fnix backup --output ~/fnix-backup-$(date +%Y%m%d).tar.gz

# 新机器
fnix restore --input fnix-backup-20260817.tar.gz
```

---

## J. 日志收集

### J1. 收集全部日志

```bash
fnix doctor --collect-logs --output ~/fnix-logs-$(date +%Y%m%d).zip
```

### J2. 日志位置

| 系统 | 路径 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\fnixagent\logs\` |
| macOS | `~/Library/Logs/FnixAgent/` |
| Linux | `~/.local/share/fnixagent/logs/` |

### J3. 日志级别

```bash
# 临时开启 debug
fnixagent start --log-level debug

# 持久改
config/agentd.yaml:
logging:
  level: debug
  sinks:
    - file
    - stderr
```

---

## K. 提交 Bug Report

在提 Issue 之前,**请先收集**:

```bash
fnix doctor --report
```

会自动生成包含:
- OS / 架构 / Python / Rust 版本
- 已安装 skill 列表
- agentd 配置(去除敏感信息)
- 最近 1000 行日志
- 配置文件 hash

的 zip 包,附在 Issue 里。

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.