//! Managed local runtime for the single Workbench desktop shell.
//!
//! Development can use an external agentd/fnix-local via environment variables.
//! Packaged builds resolve bundled resources and expose the selected dynamic ports
//! to the renderer through `runtime_get_config`.

use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, State};

const MAX_RESTARTS: u32 = 3;

#[derive(Default)]
pub struct RuntimeState {
    api_base: Mutex<String>,
    sidecar_url: Mutex<String>,
    capability_token: Mutex<String>,
    packaged: Mutex<bool>,
    starting: Mutex<bool>,
    /// True when FNIXAGENT_BACKEND_URL / VITE_API_BASE points at an external agentd.
    /// Doctor must not spawn a competing process on that port.
    external_api: Mutex<bool>,
    /// True when FNIX_LOCAL_URL points at an external sidecar.
    external_sidecar: Mutex<bool>,
    sidecar_child: Mutex<Option<Child>>,
    agentd_child: Mutex<Option<Child>>,
    agentd_restarts: Mutex<u32>,
    sidecar_restarts: Mutex<u32>,
}

struct RuntimePaths {
    work_dir: PathBuf,
    python_path: PathBuf,
    sidecar_dir: PathBuf,
    agentd_dir: PathBuf,
    log_dir: PathBuf,
    packaged: bool,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeConfig {
    pub api_base: String,
    pub sidecar_url: String,
    pub capability_token: String,
    pub packaged: bool,
}

#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeDoctorReport {
    pub ok: bool,
    pub api_base: String,
    pub sidecar_url: String,
    pub packaged: bool,
    pub capability_configured: bool,
    pub agentd_binary: bool,
    pub sidecar_binary: bool,
    pub python_fallback: bool,
    pub agentd_healthy: bool,
    pub sidecar_healthy: bool,
    pub keychain_ok: bool,
    pub agentd_restarts: u32,
    pub sidecar_restarts: u32,
    pub arch: String,
    pub os: String,
    pub notes: Vec<String>,
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn env_api_base() -> Option<String> {
    [
        "FNIXAGENT_BACKEND_URL",
        "fnixagent_BACKEND_URL",
        "VITE_API_BASE",
    ]
    .into_iter()
    .find_map(|key| std::env::var(key).ok().filter(|value| !value.trim().is_empty()))
}

fn resolve_paths(app: &AppHandle) -> RuntimePaths {
    let log_dir = app
        .path()
        .app_log_dir()
        .unwrap_or_else(|_| std::env::temp_dir().join("fnix"));
    let _ = fs::create_dir_all(&log_dir);

    if let Ok(resources) = app.path().resource_dir() {
        let python_path = resources.join("fnixagent-py/src");
        let agentd_dir = resources.join("agentd");
        if python_path.exists() || bundled_agentd_binary(&agentd_dir).is_some() {
            return RuntimePaths {
                work_dir: resources.clone(),
                python_path,
                sidecar_dir: resources.join("fnix-local"),
                agentd_dir,
                log_dir,
                packaged: true,
            };
        }
    }

    let root = repo_root();
    let workbench_resources = root.join("apps/workbench/src-tauri/resources");
    let legacy_resources = root.join("apps/desktop-tauri/resources");
    let resources = if workbench_resources.join("fnixagent-py/src").exists()
        || workbench_resources.join("agentd").exists()
    {
        workbench_resources
    } else {
        legacy_resources
    };
    let bundled_python = resources.join("fnixagent-py/src");
    let python_path = if bundled_python.exists() {
        bundled_python
    } else {
        root.join("src")
    };

    RuntimePaths {
        work_dir: root,
        python_path,
        sidecar_dir: resources.join("fnix-local"),
        agentd_dir: resources.join("agentd"),
        log_dir,
        packaged: false,
    }
}

fn bundled_sidecar_binary(sidecar_dir: &Path) -> Option<PathBuf> {
    let names: &[&str] = if cfg!(target_os = "windows") {
        &["fnix-local.exe", "fnix-local-windows-x64.exe"]
    } else if cfg!(target_os = "macos") {
        &["fnix-local", "fnix-local-macos-universal"]
    } else {
        &["fnix-local", "fnix-local-linux-x64"]
    };
    names
        .iter()
        .map(|name| sidecar_dir.join(name))
        .find(|path| path.is_file())
}

fn bundled_agentd_binary(agentd_dir: &Path) -> Option<PathBuf> {
    let names: &[&str] = if cfg!(target_os = "windows") {
        &["fnix-agentd.exe", "agentd.exe"]
    } else {
        &["fnix-agentd", "agentd"]
    };
    names
        .iter()
        .map(|name| agentd_dir.join(name))
        .find(|path| path.is_file())
}

fn python_command() -> &'static str {
    if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    }
}

fn find_free_port(start: u16, end: u16) -> Result<u16, String> {
    (start..=end)
        .find(|port| TcpListener::bind(("127.0.0.1", *port)).is_ok())
        .ok_or_else(|| format!("no free port in range {start}-{end}"))
}

fn log_stdio(log_dir: &Path, name: &str) -> Result<(Stdio, Stdio), String> {
    let stdout = open_log(log_dir, &format!("{name}.stdout.log"))?;
    let stderr = open_log(log_dir, &format!("{name}.stderr.log"))?;
    Ok((Stdio::from(stdout), Stdio::from(stderr)))
}

fn open_log(log_dir: &Path, name: &str) -> Result<File, String> {
    fs::create_dir_all(log_dir).map_err(|error| error.to_string())?;
    OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join(name))
        .map_err(|error| error.to_string())
}

async fn wait_for_health(url: &str, timeout_ms: u64) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
        .map_err(|error| error.to_string())?;
    let health_url = format!("{}/health", url.trim_end_matches('/'));
    let started = Instant::now();
    while started.elapsed().as_millis() < timeout_ms as u128 {
        if let Ok(response) = client.get(&health_url).send().await {
            if response.status().is_success() {
                return Ok(());
            }
        }
        tokio::time::sleep(Duration::from_millis(400)).await;
    }
    Err(format!("runtime health check timed out: {health_url}"))
}

fn spawn_sidecar(
    paths: &RuntimePaths,
    host: &str,
    port: u16,
    capability_token: &str,
) -> Result<Child, String> {
    let (stdout, stderr) = log_stdio(&paths.log_dir, "fnix-local")?;
    if let Some(binary) = bundled_sidecar_binary(&paths.sidecar_dir) {
        return Command::new(binary)
            .args(["--host", host, "--port", &port.to_string()])
            .env("FNIX_LOCAL_HOST", host)
            .env("FNIX_LOCAL_PORT", port.to_string())
            .env("FNIX_CAPABILITY_TOKEN", capability_token)
            .stdout(stdout)
            .stderr(stderr)
            .spawn()
            .map_err(|error| error.to_string());
    }

    Command::new(python_command())
        .args(["-m", "fnixagent.local"])
        .current_dir(&paths.work_dir)
        .env("PYTHONPATH", &paths.python_path)
        .env("FNIX_LOCAL_HOST", host)
        .env("FNIX_LOCAL_PORT", port.to_string())
        .env("FNIX_CAPABILITY_TOKEN", capability_token)
        .stdout(stdout)
        .stderr(stderr)
        .spawn()
        .map_err(|error| format!("failed to start fnix-local: {error}"))
}

fn spawn_agentd(
    paths: &RuntimePaths,
    host: &str,
    port: u16,
    sidecar_url: &str,
    capability_token: &str,
) -> Result<Child, String> {
    let (stdout, stderr) = log_stdio(&paths.log_dir, "agentd")?;
    let profile =
        std::env::var("FNIXAGENT_PROFILE").unwrap_or_else(|_| "standalone".into());
    let backend = format!("http://{host}:{port}");
    let port_arg = port.to_string();
    // Production guardrail (fnixagent.main lifespan): SERVICE_ENV=production 时
    // 弱/空 JWT_SECRET_KEY 会拒绝启动。桌面壳每次启动生成强随机密钥注入,
    // 打包发布版(agentd 以 production 运行)方可正常拉起。
    let jwt_secret = uuid::Uuid::new_v4().to_string();

    // Packaged builds use PyInstaller binary. Dev uses live Python so gateway
    // fixes apply without rebuilding (set FNIX_AGENTD_BUNDLE=1 to force binary).
    let force_bundle = std::env::var("FNIX_AGENTD_BUNDLE")
        .map(|v| matches!(v.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes"))
        .unwrap_or(false);
    let use_bundle = force_bundle || paths.packaged;
    if use_bundle {
        if let Some(binary) = bundled_agentd_binary(&paths.agentd_dir) {
            return Command::new(binary)
                .args([
                    "serve",
                    "--no-reload",
                    "--host",
                    host,
                    "--port",
                    &port_arg,
                ])
                .current_dir(&paths.agentd_dir)
                .env("FNIXAGENT_PROFILE", &profile)
                // P1: SERVICE_ENV/SERVICE_DEBUG 跟随编译 profile, 不再强制 dev 模式
                // 打包发布版用 production, dev 模式才开 debug, 让 main.py 的 production guardrail 生效
                .env("SERVICE_ENV", if cfg!(debug_assertions) { "development" } else { "production" })
                .env("SERVICE_DEBUG", if cfg!(debug_assertions) { "true" } else { "false" })
                .env("FNIX_LOCAL_URL", sidecar_url)
                .env("FNIX_LOCAL_MANAGED", "false")
                .env("FNIX_CAPABILITY_TOKEN", capability_token)
                .env("JWT_SECRET_KEY", &jwt_secret)
                .env("FNIXAGENT_BACKEND_URL", &backend)
                .stdout(stdout)
                .stderr(stderr)
                .spawn()
                .map_err(|error| format!("failed to start bundled agentd: {error}"));
        }
    }

    Command::new(python_command())
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
        .env("FNIXAGENT_PROFILE", profile)
        .env("SERVICE_ENV", "development")
        .env("SERVICE_DEBUG", "true")
        .env("FNIX_LOCAL_URL", sidecar_url)
        .env("FNIX_LOCAL_MANAGED", "false")
        .env("FNIX_CAPABILITY_TOKEN", capability_token)
        .env("JWT_SECRET_KEY", jwt_secret)
        .env("FNIXAGENT_BACKEND_URL", backend)
        .stdout(stdout)
        .stderr(stderr)
        .spawn()
        .map_err(|error| format!("failed to start agentd: {error}"))
}

pub fn read_config(state: &RuntimeState) -> RuntimeConfig {
    let api_base = state
        .api_base
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let sidecar_url = state
        .sidecar_url
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let capability_token = state
        .capability_token
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let packaged = state.packaged.lock().map(|value| *value).unwrap_or(false);
    RuntimeConfig {
        api_base: if api_base.is_empty() {
            env_api_base().unwrap_or_else(|| "http://127.0.0.1:8003".to_string())
        } else {
            api_base
        },
        sidecar_url: if sidecar_url.is_empty() {
            std::env::var("FNIX_LOCAL_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:8710".to_string())
        } else {
            sidecar_url
        },
        capability_token: if capability_token.is_empty() {
            std::env::var("FNIX_CAPABILITY_TOKEN").unwrap_or_default()
        } else {
            capability_token
        },
        packaged,
    }
}

pub async fn bootstrap(app: &AppHandle) -> Result<RuntimeConfig, String> {
    let state = app.state::<RuntimeState>();
    {
        let mut starting = state
            .starting
            .lock()
            .map_err(|_| "runtime state lock poisoned".to_string())?;
        if *starting || state.agentd_child.lock().map(|child| child.is_some()).unwrap_or(false) {
            return Ok(read_config(&state));
        }
        *starting = true;
    }

    let result = bootstrap_inner(app, &state).await;
    if let Ok(mut starting) = state.starting.lock() {
        *starting = false;
    }
    match result {
        Ok(()) => Ok(read_config(&state)),
        Err(error) => {
            shutdown(&state);
            Err(error)
        }
    }
}

async fn bootstrap_inner(app: &AppHandle, state: &RuntimeState) -> Result<(), String> {
    let paths = resolve_paths(app);
    if let Ok(mut packaged) = state.packaged.lock() {
        *packaged = paths.packaged;
    }

    let external_api = env_api_base();
    let external_sidecar = std::env::var("FNIX_LOCAL_URL")
        .ok()
        .filter(|value| !value.trim().is_empty());
    let use_external_api = external_api.is_some();
    let use_external_sidecar = external_sidecar.is_some();
    if let Ok(mut value) = state.external_api.lock() {
        *value = use_external_api;
    }
    if let Ok(mut value) = state.external_sidecar.lock() {
        *value = use_external_sidecar;
    }

    // Only mint a capability token when we manage agentd ourselves (or env forces one).
    // External agentd is usually started without FNIX_CAPABILITY_TOKEN for local UI.
    let capability_token = if use_external_api {
        std::env::var("FNIX_CAPABILITY_TOKEN")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_default()
    } else {
        std::env::var("FNIX_CAPABILITY_TOKEN")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| uuid::Uuid::new_v4().to_string())
    };
    if let Ok(mut value) = state.capability_token.lock() {
        *value = capability_token.clone();
    }

    if let Some(api_base) = external_api.as_ref() {
        if let Ok(mut value) = state.api_base.lock() {
            *value = api_base.clone();
        }
    }
    if let Some(sidecar_url) = external_sidecar.as_ref() {
        if let Ok(mut value) = state.sidecar_url.lock() {
            *value = sidecar_url.clone();
        }
    }

    let host = "127.0.0.1";
    let mut sidecar_url = external_sidecar.unwrap_or_default();
    if sidecar_url.is_empty() {
        let port = find_free_port(8710, 8720)?;
        sidecar_url = format!("http://{host}:{port}");
        let child = spawn_sidecar(&paths, host, port, &capability_token)?;
        if let Ok(mut value) = state.sidecar_child.lock() {
            *value = Some(child);
        }
        if let Ok(mut value) = state.sidecar_url.lock() {
            *value = sidecar_url.clone();
        }
        wait_for_health(&sidecar_url, 20_000).await?;
    }

    if !use_external_api {
        // Prefer canonical local port; fall back within range if busy.
        let port = find_free_port(8003, 8020).or_else(|_| find_free_port(8000, 8020))?;
        let api_base = format!("http://{host}:{port}");
        let child = spawn_agentd(&paths, host, port, &sidecar_url, &capability_token)?;
        if let Ok(mut value) = state.agentd_child.lock() {
            *value = Some(child);
        }
        if let Ok(mut value) = state.api_base.lock() {
            *value = api_base.clone();
        }
        wait_for_health(&api_base, 90_000).await?;
    } else if let Some(api_base) = external_api.as_ref() {
        // Soft probe only — never replace an externally managed agentd.
        if !probe_health(api_base).await {
            return Err(format!(
                "external agentd unhealthy at {api_base} (set FNIXAGENT_BACKEND_URL only when already running)"
            ));
        }
    }
    Ok(())
}

fn kill_child(slot: &Mutex<Option<Child>>) {
    if let Ok(mut child) = slot.lock() {
        if let Some(mut process) = child.take() {
            let _ = process.kill();
            let _ = process.wait();
        }
    }
}

pub fn shutdown(state: &RuntimeState) {
    kill_child(&state.agentd_child);
    kill_child(&state.sidecar_child);
}

async fn probe_health(url: &str) -> bool {
    if url.trim().is_empty() {
        return false;
    }
    wait_for_health(url, 2_500).await.is_ok()
}

async fn ensure_children_alive(app: &AppHandle, state: &RuntimeState) -> Result<(), String> {
    let config = read_config(state);
    let paths = resolve_paths(app);
    let token = state
        .capability_token
        .lock()
        .map(|value| value.clone())
        .unwrap_or_default();
    let external_api = state.external_api.lock().map(|v| *v).unwrap_or(false);
    let external_sidecar = state.external_sidecar.lock().map(|v| *v).unwrap_or(false);
    let host = "127.0.0.1";

    if !config.sidecar_url.is_empty() && !probe_health(&config.sidecar_url).await {
        if external_sidecar {
            return Err(format!(
                "external fnix-local unhealthy (will not respawn): {}",
                config.sidecar_url
            ));
        }
        let restarts = state.sidecar_restarts.lock().map(|v| *v).unwrap_or(0);
        if restarts >= MAX_RESTARTS {
            return Err(format!(
                "fnix-local unhealthy after {MAX_RESTARTS} restarts: {}",
                config.sidecar_url
            ));
        }
        kill_child(&state.sidecar_child);
        let port = config
            .sidecar_url
            .rsplit(':')
            .next()
            .and_then(|p| p.parse().ok())
            .unwrap_or(8710);
        let child = spawn_sidecar(&paths, host, port, &token)?;
        if let Ok(mut value) = state.sidecar_child.lock() {
            *value = Some(child);
        }
        if let Ok(mut value) = state.sidecar_restarts.lock() {
            *value += 1;
        }
        wait_for_health(&config.sidecar_url, 20_000).await?;
    }

    if !config.api_base.is_empty() && !probe_health(&config.api_base).await {
        if external_api {
            return Err(format!(
                "external agentd unhealthy (will not respawn): {}",
                config.api_base
            ));
        }
        let restarts = state.agentd_restarts.lock().map(|v| *v).unwrap_or(0);
        if restarts >= MAX_RESTARTS {
            return Err(format!(
                "agentd unhealthy after {MAX_RESTARTS} restarts: {}",
                config.api_base
            ));
        }
        kill_child(&state.agentd_child);
        let port = config
            .api_base
            .rsplit(':')
            .next()
            .and_then(|p| p.parse().ok())
            .unwrap_or(8003);
        let child = spawn_agentd(&paths, host, port, &config.sidecar_url, &token)?;
        if let Ok(mut value) = state.agentd_child.lock() {
            *value = Some(child);
        }
        if let Ok(mut value) = state.agentd_restarts.lock() {
            *value += 1;
        }
        wait_for_health(&config.api_base, 90_000).await?;
    }
    Ok(())
}

fn keychain_probe() -> bool {
    match keyring::Entry::new("com.fnix.agent", "doctor.probe") {
        Ok(entry) => match entry.set_password("ok") {
            Ok(()) => {
                let _ = entry.delete_credential();
                true
            }
            Err(_) => false,
        },
        Err(_) => false,
    }
}

pub async fn doctor(app: &AppHandle, state: &RuntimeState) -> RuntimeDoctorReport {
    let config = read_config(state);
    let paths = resolve_paths(app);
    let agentd_binary = bundled_agentd_binary(&paths.agentd_dir).is_some();
    let sidecar_binary = bundled_sidecar_binary(&paths.sidecar_dir).is_some();
    let python_fallback = !agentd_binary;
    let agentd_healthy = probe_health(&config.api_base).await;
    let sidecar_healthy = probe_health(&config.sidecar_url).await;
    let capability_configured = !config.capability_token.is_empty();
    let keychain_ok = keychain_probe();
    let agentd_restarts = state.agentd_restarts.lock().map(|v| *v).unwrap_or(0);
    let sidecar_restarts = state.sidecar_restarts.lock().map(|v| *v).unwrap_or(0);

    let mut notes = Vec::new();
    if python_fallback {
        notes.push("agentd using system Python fallback — run pnpm bundle:agentd".into());
    }
    let external_api = state.external_api.lock().map(|v| *v).unwrap_or(false);
    let external_sidecar = state.external_sidecar.lock().map(|v| *v).unwrap_or(false);
    if external_api {
        notes.push("using external agentd (FNIXAGENT_BACKEND_URL / VITE_API_BASE) — no auto-respawn".into());
    }
    if external_sidecar {
        notes.push("using external fnix-local (FNIX_LOCAL_URL) — no auto-respawn".into());
    }
    if !capability_configured && !external_api {
        notes.push("capability token empty — managed desktop bootstrap not active".into());
    }
    if !agentd_healthy {
        notes.push("agentd /health failed".into());
    }
    if !sidecar_healthy {
        notes.push("fnix-local /health failed".into());
    }
    if !keychain_ok {
        notes.push("OS Keychain unavailable — BYOK may fall back to memory only".into());
    }

    let ok = agentd_healthy
        && (config.sidecar_url.is_empty() || sidecar_healthy)
        && (!paths.packaged || agentd_binary);

    RuntimeDoctorReport {
        ok,
        api_base: config.api_base,
        sidecar_url: config.sidecar_url,
        packaged: config.packaged,
        capability_configured,
        agentd_binary,
        sidecar_binary,
        python_fallback,
        agentd_healthy,
        sidecar_healthy,
        keychain_ok,
        agentd_restarts,
        sidecar_restarts,
        arch: std::env::consts::ARCH.to_string(),
        os: std::env::consts::OS.to_string(),
        notes,
    }
}

#[tauri::command]
pub fn runtime_get_config(state: State<'_, RuntimeState>) -> RuntimeConfig {
    read_config(&state)
}

#[tauri::command]
pub async fn runtime_bootstrap(app: AppHandle) -> Result<RuntimeConfig, String> {
    bootstrap(&app).await
}

#[tauri::command]
pub async fn runtime_doctor(app: AppHandle) -> RuntimeDoctorReport {
    let state = app.state::<RuntimeState>();
    let _ = ensure_children_alive(&app, &state).await;
    doctor(&app, &state).await
}
