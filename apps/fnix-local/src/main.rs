//! fnix-local — Rust sidecar implementing packages/protocol/openapi/fnix-local-v1.yaml

use axum::{
    extract::{Query, Request, State},
    http::StatusCode,
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    net::SocketAddr,
    path::{Path, PathBuf},
    process::Stdio,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tokio::{fs, process::Command, time::timeout};
use tower_http::cors::{AllowOrigin, CorsLayer};
use walkdir::WalkDir;

const VERSION: &str = "0.1.0-rust";

#[derive(Clone)]
struct AppState {
    sessions: Arc<Mutex<HashMap<String, IndexSession>>>,
    workspace_map: Arc<Mutex<HashMap<String, String>>>,
}

#[derive(Clone, Serialize, Deserialize)]
struct IndexSession {
    session_id: String,
    workspace: String,
    indexed_at: String,
    stats: serde_json::Value,
    pdg_digest: String,
    symbols: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
struct IndexRequest {
    workspace: String,
    #[serde(default)]
    force: bool,
    session_id: Option<String>,
}

#[derive(Deserialize)]
struct RunRequest {
    workspace: String,
    command: String,
    cwd: Option<String>,
    #[serde(default = "default_timeout")]
    timeout: u64,
}

fn default_timeout() -> u64 {
    60
}

#[derive(Deserialize)]
struct ReadQuery {
    workspace: String,
    path: String,
    #[serde(default)]
    offset: usize,
    limit: Option<usize>,
}

#[derive(Deserialize)]
struct ContextQuery {
    workspace: Option<String>,
    session_id: Option<String>,
    query: Option<String>,
    #[serde(default = "default_top_k")]
    top_k: usize,
}

fn default_top_k() -> usize {
    8
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "fnix_local=info,tower_http=warn".into()),
        )
        .init();

    let host = std::env::var("FNIX_LOCAL_HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port: u16 = std::env::var("FNIX_LOCAL_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8710);

    let state = AppState {
        sessions: Arc::new(Mutex::new(HashMap::new())),
        workspace_map: Arc::new(Mutex::new(HashMap::new())),
    };

    let cors = CorsLayer::new()
        .allow_origin(AllowOrigin::list([
            "http://127.0.0.1:5175".parse().unwrap(),
            "http://localhost:5175".parse().unwrap(),
            "http://127.0.0.1:1420".parse().unwrap(),
            "http://localhost:1420".parse().unwrap(),
            "tauri://localhost".parse().unwrap(),
            "https://tauri.localhost".parse().unwrap(),
        ]))
        .allow_methods(tower_http::cors::Any)
        .allow_headers(tower_http::cors::Any);

    let app = Router::new()
        .route("/health", get(health))
        .route("/v1/index", post(index_workspace))
        .route("/v1/context", get(get_context))
        .route("/v1/run", post(run_command))
        .route("/v1/read", get(read_file))
        .layer(middleware::from_fn(capability_gate))
        .layer(cors)
        .with_state(state);

    let addr: SocketAddr = format!("{host}:{port}").parse().expect("bind addr");
    tracing::info!("fnix-local listening on http://{addr}");
    let listener = tokio::net::TcpListener::bind(addr).await.expect("bind");
    axum::serve(listener, app).await.expect("serve");
}

async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "ok": true,
        "service": "fnix-local",
        "version": VERSION,
        "runtime": "rust",
    }))
}

async fn capability_gate(req: Request, next: Next) -> Response {
    let expected = std::env::var("FNIX_CAPABILITY_TOKEN")
        .unwrap_or_default()
        .trim()
        .to_string();
    if expected.is_empty() || req.uri().path() == "/health" {
        return next.run(req).await;
    }
    let presented = req
        .headers()
        .get("x-fnix-capability")
        .and_then(|value| value.to_str().ok())
        .map(str::trim)
        .unwrap_or("");
    if presented == expected {
        return next.run(req).await;
    }
    (
        StatusCode::UNAUTHORIZED,
        Json(serde_json::json!({"detail":"Missing or invalid capability token"})),
    )
        .into_response()
}

fn norm_workspace(path: &str) -> Result<PathBuf, (StatusCode, String)> {
    let p = PathBuf::from(path);
    let abs = if p.is_absolute() {
        p
    } else {
        std::env::current_dir()
            .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?
            .join(p)
    };
    let canonical = abs
        .canonicalize()
        .map_err(|e| (StatusCode::BAD_REQUEST, format!("invalid workspace: {e}")))?;
    if !canonical.is_dir() {
        return Err((StatusCode::BAD_REQUEST, "workspace is not a directory".into()));
    }
    Ok(canonical)
}

fn index_dir(workspace: &Path) -> PathBuf {
    workspace.join(".fnix").join("index")
}

fn persist_summary(session: &IndexSession) -> std::io::Result<()> {
    let dir = index_dir(Path::new(&session.workspace));
    std::fs::create_dir_all(&dir)?;
    let path = dir.join("pdg_summary.json");
    let tmp = dir.join("pdg_summary.json.tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(session)?)?;
    std::fs::rename(tmp, path)
}

fn load_summary(workspace: &Path) -> Option<IndexSession> {
    let path = index_dir(workspace).join("pdg_summary.json");
    let raw = std::fs::read_to_string(path).ok()?;
    serde_json::from_str(&raw).ok()
}

async fn index_workspace(
    State(state): State<AppState>,
    Json(body): Json<IndexRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let root = norm_workspace(&body.workspace)?;
    let norm_key = root.to_string_lossy().to_lowercase();

    if !body.force {
        if let Some(sid) = state.workspace_map.lock().unwrap().get(&norm_key).cloned() {
            if let Some(session) = state.sessions.lock().unwrap().get(&sid).cloned() {
                return Ok(Json(serde_json::json!({
                    "ok": true,
                    "session_id": session.session_id,
                    "workspace": session.workspace,
                    "stats": session.stats,
                })));
            }
        }
    }

    let started = Instant::now();
    let mut total_files = 0u64;
    let mut indexed_files = 0u64;
    let mut digest_lines: Vec<String> = Vec::new();
    let mut symbols: Vec<serde_json::Value> = Vec::new();

    let walker = WalkDir::new(&root)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| !should_skip(e.path()));

    for entry in walker.filter_map(|e| e.ok()) {
        total_files += 1;
        if !entry.file_type().is_file() {
            continue;
        }
        let path = entry.path();
        if should_skip(path) {
            continue;
        }
        if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            if is_code_ext(ext) {
                indexed_files += 1;
                if let Ok(rel) = path.strip_prefix(&root) {
                    digest_lines.push(format!("- {}", rel.display()));
                    if symbols.len() < 150 {
                        if let Ok(content) = std::fs::read_to_string(path) {
                            for line in content.lines().take(200) {
                                let trimmed = line.trim();
                                if trimmed.starts_with("fn ")
                                    || trimmed.starts_with("pub fn ")
                                    || trimmed.starts_with("class ")
                                    || trimmed.starts_with("def ")
                                    || trimmed.starts_with("export function ")
                                    || trimmed.starts_with("export async function ")
                                {
                                    symbols.push(serde_json::json!({
                                        "name": trimmed.chars().take(80).collect::<String>(),
                                        "kind": "symbol",
                                        "file": rel.display().to_string(),
                                        "line": 0,
                                    }));
                                    break;
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    let session_id = body
        .session_id
        .unwrap_or_else(|| uuid::Uuid::new_v4().simple().to_string()[..16].to_string());

    let stats = serde_json::json!({
        "total_files": total_files,
        "indexed_files": indexed_files,
        "skipped_files": total_files.saturating_sub(indexed_files),
        "total_symbols": symbols.len(),
        "total_slices": 0,
        "duration_sec": started.elapsed().as_secs_f64(),
        "errors": [],
    });

    let session = IndexSession {
        session_id: session_id.clone(),
        workspace: root.to_string_lossy().to_string(),
        indexed_at: chrono_now(),
        stats: stats.clone(),
        pdg_digest: digest_lines.join("\n"),
        symbols,
    };

    persist_summary(&session).map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    {
        let mut sessions = state.sessions.lock().unwrap();
        sessions.insert(session_id.clone(), session.clone());
    }
    state
        .workspace_map
        .lock()
        .unwrap()
        .insert(norm_key, session_id.clone());

    Ok(Json(serde_json::json!({
        "ok": true,
        "session_id": session_id,
        "workspace": session.workspace,
        "stats": stats,
    })))
}

async fn get_context(
    State(state): State<AppState>,
    Query(q): Query<ContextQuery>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    if q.workspace.is_none() && q.session_id.is_none() {
        return Err((StatusCode::BAD_REQUEST, "workspace or session_id required".into()));
    }

    let session = if let Some(sid) = &q.session_id {
        state.sessions.lock().unwrap().get(sid).cloned()
    } else if let Some(ws) = &q.workspace {
        let root = norm_workspace(ws)?;
        load_summary(&root).or_else(|| {
            let norm_key = root.to_string_lossy().to_lowercase();
            state
                .workspace_map
                .lock()
                .unwrap()
                .get(&norm_key)
                .and_then(|sid| state.sessions.lock().unwrap().get(sid).cloned())
        })
    } else {
        None
    };

    let Some(session) = session else {
        return Ok(Json(serde_json::json!({
            "ok": false,
            "session_id": "",
            "symbols": [],
            "pdg_digest": "",
            "vector_hits": [],
            "message": "no index session",
        })));
    };

    let mut vector_hits = Vec::new();
    if let Some(query) = &q.query {
        let q_lower = query.to_lowercase();
        for sym in session.symbols.iter().take(q.top_k * 3) {
            let name = sym.get("name").and_then(|v| v.as_str()).unwrap_or("");
            if name.to_lowercase().contains(&q_lower) {
                vector_hits.push(serde_json::json!({
                    "file": sym.get("file").cloned().unwrap_or_default(),
                    "lines": sym.get("line").cloned().unwrap_or(serde_json::json!(0)),
                    "symbol": name,
                    "preview": name,
                }));
                if vector_hits.len() >= q.top_k {
                    break;
                }
            }
        }
    }

    Ok(Json(serde_json::json!({
        "ok": true,
        "session_id": session.session_id,
        "workspace": session.workspace,
        "pdg_digest": session.pdg_digest,
        "symbols": session.symbols,
        "vector_hits": vector_hits,
        "stats": session.stats,
    })))
}

async fn run_command(Json(body): Json<RunRequest>) -> Json<serde_json::Value> {
    let workspace = match norm_workspace(&body.workspace) {
        Ok(p) => p,
        Err((_, msg)) => {
            return Json(serde_json::json!({
                "ok": false,
                "stdout": "",
                "stderr": msg,
                "exit_code": 1,
            }))
        }
    };

    let cwd = if let Some(rel) = body.cwd.as_ref() {
        match safe_join(&workspace, rel) {
            Ok(path) => path,
            Err((_, msg)) => {
                return Json(serde_json::json!({
                    "ok": false,
                    "stdout": "",
                    "stderr": msg,
                    "exit_code": 1,
                }))
            }
        }
    } else {
        workspace.clone()
    };

    // Reject path-escape and common destructive patterns before spawning a shell.
    let command = body.command.trim();
    if command.is_empty() {
        return Json(serde_json::json!({
            "ok": false,
            "stdout": "",
            "stderr": "empty command",
            "exit_code": 1,
        }));
    }
    let lower = command.to_ascii_lowercase();
    let blocked = [
        "rm -rf /",
        "rm -rf \\",
        "del /f",
        "format ",
        "mkfs",
        "shutdown",
        "reboot",
        "..\\",
        "../",
    ];
    if blocked.iter().any(|needle| lower.contains(needle)) {
        return Json(serde_json::json!({
            "ok": false,
            "stdout": "",
            "stderr": "command blocked by fnix-local policy",
            "exit_code": 1,
        }));
    }

    let shell = if cfg!(target_os = "windows") {
        ("cmd", "/C")
    } else {
        ("sh", "-c")
    };

    let mut cmd = Command::new(shell.0);
    cmd.arg(shell.1)
        .arg(command)
        .current_dir(cwd)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let dur = Duration::from_secs(body.timeout.min(600));
    match timeout(dur, cmd.output()).await {
        Ok(Ok(output)) => Json(serde_json::json!({
            "ok": output.status.success(),
            "stdout": String::from_utf8_lossy(&output.stdout).to_string(),
            "stderr": String::from_utf8_lossy(&output.stderr).to_string(),
            "exit_code": output.status.code().unwrap_or(1),
        })),
        Ok(Err(e)) => Json(serde_json::json!({
            "ok": false,
            "stdout": "",
            "stderr": e.to_string(),
            "exit_code": 1,
        })),
        Err(_) => Json(serde_json::json!({
            "ok": false,
            "stdout": "",
            "stderr": "command timed out",
            "exit_code": 124,
        })),
    }
}

async fn read_file(Query(q): Query<ReadQuery>) -> Result<impl IntoResponse, (StatusCode, String)> {
    let workspace = norm_workspace(&q.workspace)?;
    let target = safe_join(&workspace, &q.path)?;

    let content = fs::read_to_string(&target)
        .await
        .map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))?;

    let sliced = if q.offset > 0 || q.limit.is_some() {
        let lines: Vec<&str> = content.lines().collect();
        let start = q.offset.min(lines.len());
        let end = q
            .limit
            .map(|l| (start + l).min(lines.len()))
            .unwrap_or(lines.len());
        lines[start..end].join("\n")
    } else {
        content
    };

    Ok(Json(serde_json::json!({
        "ok": true,
        "content": sliced,
        "metadata": { "path": q.path, "offset": q.offset, "limit": q.limit },
    })))
}

fn safe_join(workspace: &Path, rel: &str) -> Result<PathBuf, (StatusCode, String)> {
    let root = workspace
        .canonicalize()
        .map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))?;
    let candidate = if Path::new(rel).is_absolute() {
        PathBuf::from(rel)
    } else {
        root.join(rel)
    };
    let canonical = candidate
        .canonicalize()
        .map_err(|e| (StatusCode::BAD_REQUEST, e.to_string()))?;
    if canonical.strip_prefix(&root).is_err() {
        return Err((StatusCode::BAD_REQUEST, "path escapes workspace".into()));
    }
    Ok(canonical)
}

fn should_skip(path: &Path) -> bool {
    let s = path.to_string_lossy();
    s.contains("/.git/")
        || s.contains("\\.git\\")
        || s.contains("/node_modules/")
        || s.contains("\\node_modules\\")
        || s.contains("/target/")
        || s.contains("\\target\\")
        || s.contains("/dist/")
        || s.contains("\\dist\\")
        || s.ends_with(".git")
}

fn is_code_ext(ext: &str) -> bool {
    matches!(
        ext,
        "rs" | "py" | "ts" | "tsx" | "js" | "jsx" | "go" | "java" | "c" | "cpp" | "h" | "cs" | "md" | "json" | "yaml" | "yml" | "toml"
    )
}

fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    format!("{secs}")
}
