//! 子进程生命周期 — fnix-local + agentd（Standalone 自动拉起）
use serde::Serialize;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, State};

#[derive(Default)]
pub struct RuntimeState {
    pub api_base: Mutex<String>,
    pub sidecar_url: Mutex<String>,
    pub managed: Mutex<bool>,
    pub packaged: Mutex<bool>,
    sidecar_child: Mutex<Option<Child>>,
    agentd_child: Mutex<Option<Child>>,
}

struct RuntimePaths {
    work_dir: PathBuf,
    python_path: PathBuf,
    sidecar_dir: PathBuf,
    packaged: bool,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeConfig {
    pub api_base: String,
    pub sidecar_url: String,
    pub packaged: bool,
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn resolve_paths(app: &AppHandle) -> RuntimePaths {
    if let Ok(res) = app.path().resource_dir() {
        let py = res.join("fnixagent-py/src");
        if py.exists() {
            return RuntimePaths {
                work_dir: res.clone(),
                python_path: py,
                sidecar_dir: res.join("fnix-local"),
                packaged: true,
            };
        }
    }

    let root = repo_root();
    let dev_res = root.join("apps/desktop-tauri/resources");
    let py = dev_res.join("fnixagent-py/src");
    if py.exists() {
        return RuntimePaths {
            work_dir: root.clone(),
            python_path: py,
            sidecar_dir: dev_res.join("fnix-local"),
            packaged: false,
        };
    }

    RuntimePaths {
        work_dir: root.clone(),
        python_path: root.join("src"),
        sidecar_dir: dev_res.join("fnix-local"),
        packaged: false,
    }
}

fn bundled_sidecar_binary(sidecar_dir: &PathBuf) -> Option<PathBuf> {
    let names = if cfg!(target_os = "windows") {
        ["fnix-local.exe", "fnix-local-windows-x64.exe"]
    } else if cfg!(target_os = "macos") {
        ["fnix-local", "fnix-local-macos-universal"]
    } else {
        ["fnix-local", "fnix-local-linux-x64"]
    };
    for name in names {
        let full = sidecar_dir.join(name);
        if full.exists() {
            return Some(full);
        }
    }
    None
}

fn python_cmd() -> &'static str {
    if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    }
}

fn find_free_port(start: u16, max: u16) -> Result<u16, String> {
    for port in start..=max {
        if TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return Ok(port);
        }
    }
    Err(format!("no free port in range {start}-{max}"))
}

async fn wait_health(url: &str, max_ms: u64) -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(c) => c,
        Err(_) => return false,
    };
    let endpoint = format!("{}/health", url.trim_end_matches('/'));
    let start = Instant::now();
    while start.elapsed().as_millis() < max_ms as u128 {
        if let Ok(resp) = client.get(&endpoint).send().await {
            if resp.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(400)).await;
    }
    false
}

/// 子进程日志目标：打包模式写入临时日志目录（避免崩溃无诊断），开发模式继承父进程。
fn child_stdio(log_name: &str, packaged: bool) -> (Stdio, Stdio) {
    if !packaged {
        // 开发模式：直接继承父进程 stdout/stderr，便于实时调试
        return (Stdio::inherit(), Stdio::inherit());
    }
    // 打包模式：追加到临时日志文件（%TEMP%/fnixagent/*.log），崩溃时可查诊断
    let base = std::env::temp_dir().join("fnixagent").join("logs");
    let _ = std::fs::create_dir_all(&base);
    let path = base.join(format!("{log_name}.log"));
    if let Ok(f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        match f.try_clone() {
            Ok(err_f) => return (Stdio::from(f), Stdio::from(err_f)),
            // 极端情况：clone 失败则 stderr 落空，stdout 仍写入日志
            Err(_) => return (Stdio::from(f), Stdio::null()),
        }
    }
    (Stdio::null(), Stdio::null())
}

fn spawn_sidecar(paths: &RuntimePaths, host: &str, port: u16) -> Result<Child, String> {
    let (out, err) = child_stdio("fnix-local", paths.packaged);
    if let Some(bin) = bundled_sidecar_binary(&paths.sidecar_dir) {
        Command::new(bin)
            .args(["--host", host, "--port", &port.to_string()])
            .env("FNIX_LOCAL_HOST", host)
            .env("FNIX_LOCAL_PORT", port.to_string())
            .stdout(out)
            .stderr(err)
            .spawn()
            .map_err(|e| e.to_string())
    } else {
        Command::new(python_cmd())
            .args(["-m", "fnixagent.local"])
            .current_dir(&paths.work_dir)
            .env("PYTHONPATH", &paths.python_path)
            .env("FNIX_LOCAL_HOST", host)
            .env("FNIX_LOCAL_PORT", port.to_string())
            .stdout(out)
            .stderr(err)
            .spawn()
            .map_err(|e| e.to_string())
    }
}

fn spawn_agentd(paths: &RuntimePaths, host: &str, port: u16, sidecar_url: &str) -> Result<Child, String> {
    let (out, err) = child_stdio("agentd", paths.packaged);
    Command::new(python_cmd())
        .args([
            "-m",
            "fnixagent.main",
            "serve",
            "--no-reload",
            "--host",
            host,
            "--port",
            &port.to_string(),
        ])
        .current_dir(&paths.work_dir)
        .env("PYTHONPATH", &paths.python_path)
        .env(
            "FNIXAGENT_PROFILE",
            std::env::var("FNIXAGENT_PROFILE").unwrap_or_else(|_| "standalone".into()),
        )
        // C7 修复：不再写死 development/true。优先读取显式环境变量，
        // 未设置时按打包状态推导：打包发布默认 production / false，
        // 开发模式（未打包）才回退到 development / true，避免发布后仍跑调试模式。
        .env(
            "SERVICE_ENV",
            std::env::var("SERVICE_ENV").unwrap_or_else(|_| {
                if paths.packaged {
                    "production".to_string()
                } else {
                    "development".to_string()
                }
            }),
        )
        .env(
            "SERVICE_DEBUG",
            std::env::var("SERVICE_DEBUG")
                .unwrap_or_else(|_| if paths.packaged { "false" } else { "true" }.to_string()),
        )
        .env("FNIX_LOCAL_URL", sidecar_url)
        .env("FNIX_LOCAL_MANAGED", "false")
        .env("fnixagent_BACKEND_URL", format!("http://{host}:{port}"))
        .stdout(out)
        .stderr(err)
        .spawn()
        .map_err(|e| e.to_string())
}

pub fn read_config(state: &RuntimeState) -> RuntimeConfig {
    let api = state.api_base.lock().map(|g| g.clone()).unwrap_or_default();
    let sidecar = state
        .sidecar_url
        .lock()
        .map(|g| g.clone())
        .unwrap_or_default();
    let packaged = state.packaged.lock().map(|g| *g).unwrap_or(false);
    RuntimeConfig {
        api_base: if api.is_empty() {
            std::env::var("fnixagent_BACKEND_URL")
                .or_else(|_| std::env::var("VITE_API_BASE"))
                .unwrap_or_else(|_| "http://127.0.0.1:8000".to_string())
        } else {
            api
        },
        sidecar_url: if sidecar.is_empty() {
            std::env::var("FNIX_LOCAL_URL").unwrap_or_else(|_| "http://127.0.0.1:8710".to_string())
        } else {
            sidecar
        },
        packaged,
    }
}

pub async fn bootstrap(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<RuntimeState>();
    let paths = resolve_paths(app);

    if let Ok(mut g) = state.packaged.lock() {
        *g = paths.packaged;
    }

    let external_api = std::env::var("fnixagent_BACKEND_URL")
        .or_else(|_| std::env::var("VITE_API_BASE"))
        .ok();
    let external_sidecar = std::env::var("FNIX_LOCAL_URL").ok();
    let sidecar_managed = std::env::var("FNIX_LOCAL_MANAGED").unwrap_or_default() != "false";

    if let Some(url) = external_api.clone() {
        if let Ok(mut g) = state.api_base.lock() {
            *g = url;
        }
    }
    if let Some(url) = external_sidecar.clone() {
        if let Ok(mut g) = state.sidecar_url.lock() {
            *g = url;
        }
    }

    let need_sidecar = external_sidecar.is_none() && sidecar_managed;
    let need_agentd = external_api.is_none();

    if !need_sidecar && !need_agentd {
        if let Ok(mut g) = state.managed.lock() {
            *g = false;
        }
        return Ok(());
    }

    if let Ok(mut g) = state.managed.lock() {
        *g = true;
    }

    let host = "127.0.0.1";
    let mut sidecar = external_sidecar.unwrap_or_default();

    if need_sidecar {
        let port = find_free_port(8710, 8720)?;
        sidecar = format!("http://{host}:{port}");
        let child = spawn_sidecar(&paths, host, port)?;
        if let Ok(mut g) = state.sidecar_child.lock() {
            *g = Some(child);
        }
        if let Ok(mut g) = state.sidecar_url.lock() {
            *g = sidecar.clone();
        }
        let _ = wait_health(&sidecar, 20_000).await;
    }

    if need_agentd {
        let port = find_free_port(8000, 8020)?;
        let api = format!("http://{host}:{port}");
        let child = spawn_agentd(&paths, host, port, &sidecar)?;
        if let Ok(mut g) = state.agentd_child.lock() {
            *g = Some(child);
        }
        if let Ok(mut g) = state.api_base.lock() {
            *g = api.clone();
        }
        let _ = wait_health(&api, 90_000).await;
    }

    Ok(())
}

pub fn shutdown(state: &RuntimeState) {
    if let Ok(mut g) = state.agentd_child.lock() {
        if let Some(mut child) = g.take() {
            let _ = child.kill();
        }
    }
    if let Ok(mut g) = state.sidecar_child.lock() {
        if let Some(mut child) = g.take() {
            let _ = child.kill();
        }
    }
}

#[tauri::command]
pub fn runtime_get_config(state: State<'_, RuntimeState>) -> RuntimeConfig {
    read_config(&state)
}

#[tauri::command]
pub async fn runtime_bootstrap(app: AppHandle) -> Result<RuntimeConfig, String> {
    bootstrap(&app).await?;
    let state = app.state::<RuntimeState>();
    Ok(read_config(&state))
}
