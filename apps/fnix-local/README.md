# `fnix-local` — Rust 本地沙箱

> 本地工具执行的最后一道防线。所有系统调用、shell 命令、文件 IO
> 都经过这个 Rust 进程,能力受 Rust 类型系统 + ulimit 双重约束。

---

## 它是什么?

`fnix-local` 是一个 Rust 编写的 sidecar 进程,作为 Python `agentd` 的子进程运行。
它实现:

- 🔒 **Capability 白名单**(哪些命令可以执行)
- ⏱️ **超时熔断**(单次调用最长 30s)
- 📊 **资源限额**(CPU / 内存 / 文件描述符)
- 📝 **结构化审计日志**(每次调用都记录)
- 🔌 **stdio JSON-RPC 协议**(与 Python 通信)

---

## 进程模型

```
Python agentd
    │
    │ spawn subprocess
    ▼
fnix-local (Rust)
    │
    │ 进程内隔离
    ▼
ulimit + rlimit + seccomp (Linux) / sandbox (macOS)
```

---

## 支持的工具

| 工具 | 描述 | Safety |
| --- | --- | --- |
| `shell.run` | 执行 shell 命令 | dangerous |
| `fs.read` | 读文件 | safe |
| `fs.write` | 写文件 | moderate |
| `fs.list` | 列目录 | safe |
| `process.kill` | 杀进程 | dangerous |
| `net.fetch` | HTTP GET | moderate |
| `clipboard.read` | 读剪贴板 | moderate |
| `system.info` | 系统信息 | safe |

---

## JSON-RPC 协议

```json
// Request
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "shell.run",
  "params": {
    "command": "ls",
    "args": ["-la", "/Users/me/notes"],
    "timeout_ms": 5000,
    "cwd": "/Users/me/notes"
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "duration_ms": 42
  }
}
```

错误:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32001,
    "message": "Command not in allowlist",
    "data": { "command": "rm" }
  }
}
```

---

## 开发 / Develop

```bash
# 开发
cargo run

# 测试
cargo test

# 性能
cargo bench

# Release 构建
cargo build --release
# 产物: target/release/fnix-local (Linux/Mac) 或 fnix-local.exe (Win)
```

---

## 关键设计

### 1. 白名单 + 路径正则

```rust
// src/main.rs
pub struct AllowList {
    commands: HashSet<String>,
    path_patterns: Vec<regex::Regex>,
}

impl AllowList {
    pub fn check_shell(&self, cmd: &str) -> Result<(), Error> {
        if !self.commands.contains(cmd) {
            return Err(Error::CommandNotAllowed(cmd.into()));
        }
        Ok(())
    }

    pub fn check_path(&self, path: &Path) -> Result<(), Error> {
        for pattern in &self.path_patterns {
            if pattern.is_match(path.to_str().unwrap_or("")) {
                return Ok(());
            }
        }
        Err(Error::PathNotAllowed(path.into()))
    }
}
```

### 2. 资源限额

```rust
use nix::sys::resource::{setrlimit, Resource};

pub fn apply_limits(cfg: &LimitsConfig) -> Result<(), Error> {
    setrlimit(Resource::RLIMIT_CPU, cfg.cpu_secs, cfg.cpu_secs)?;
    setrlimit(Resource::RLIMIT_AS, cfg.memory_bytes, cfg.memory_bytes)?;
    setrlimit(Resource::RLIMIT_NOFILE, cfg.max_files, cfg.max_files)?;
    setrlimit(Resource::RLIMIT_NPROC, cfg.max_procs, cfg.max_procs)?;
    Ok(())
}
```

### 3. 超时

```rust
use tokio::time::{timeout, Duration};

pub async fn run_with_timeout<F, T>(fut: F, ms: u64) -> Result<T, Error>
where F: Future<Output = T> {
    match timeout(Duration::from_millis(ms), fut).await {
        Ok(v) => Ok(v),
        Err(_) => Err(Error::Timeout(ms)),
    }
}
```

### 4. 结构化日志

```rust
use tracing::{info, warn, error};

#[instrument(skip(args), fields(tool = %method, actor = %actor))]
pub async fn dispatch(&self, method: &str, args: Value, actor: &str) -> Result<Value, Error> {
    let start = Instant::now();
    let result = self.dispatch_inner(method, args.clone()).await;
    let duration = start.elapsed().as_millis() as u64;

    match &result {
        Ok(v) => info!(?v, "tool_call success"),
        Err(e) => error!(?e, "tool_call failed"),
    }
    audit_log(actor, method, &args, &result, duration);
    result
}
```

---

## 配置

`fnix-local.yaml`:

```yaml
allowlist:
  commands:
    - ls
    - cat
    - grep
    - find
    - head
    - tail
    - echo
    - pwd
    - git
    - cargo
    - python
    - node
    - pnpm

path_patterns:
  - "^/Users/[^/]+/(Documents|Projects|Notes)/.*"
  - "^/home/[^/]+/(Documents|Projects|Notes)/.*"
  - "^[A-Z]:\\\\Users\\\\[^\\\\]+\\\\Documents\\\\.*"

limits:
  cpu_secs: 60
  memory_mb: 512
  max_files: 1024
  max_procs: 32

timeouts:
  default_ms: 30000
  per_command:
    git: 120000
    cargo: 600000
    python: 120000
```

---

## 测试

### 单元测试

```bash
cargo test --lib
```

### 集成测试(沙箱验证)

```bash
cargo test --test sandbox
# 跑:
#   - 路径遍历攻击 (../etc/passwd)
#   - 危险命令 (rm -rf /)
#   - 资源耗尽 (fork 炸弹)
#   - 超时 (sleep 100)
```

### 渗透测试

```bash
./scripts/pen-test.sh
```

---

## 依赖 / Dependencies

```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
nix = "0.27"
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
thiserror = "1"
anyhow = "1"
regex = "1"
```

---

## 参考 / References

- [nix-rust/nix](https://github.com/nix-rust/nix)
- [tokio](https://tokio.rs/)
- [Rust Async Book](https://rust-lang.github.io/async-book/)
- [docs/adr/0001-tauri-desktop-runtime.md](../../docs/adr/0001-tauri-desktop-runtime.md)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.