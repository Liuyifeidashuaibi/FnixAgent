//! 本地 PTY 终端 — portable-pty + Tauri 事件流
use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, State};

static PTY_SEQ: AtomicU64 = AtomicU64::new(1);

pub(crate) struct PtyHandle {
    master: Arc<Mutex<Box<dyn MasterPty + Send>>>,
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
}

#[derive(Default)]
pub struct PtyState {
    pub sessions: Mutex<HashMap<String, PtyHandle>>,
}

#[derive(Clone, Serialize)]
struct PtyOutputEvent {
    id: String,
    data: String,
}

fn shell_command() -> CommandBuilder {
    if cfg!(target_os = "windows") {
        let mut cmd = CommandBuilder::new("powershell.exe");
        cmd.args(["-NoLogo", "-NoExit"]);
        cmd
    } else {
        CommandBuilder::new("bash")
    }
}

#[tauri::command]
pub async fn pty_spawn(
    app: AppHandle,
    state: State<'_, PtyState>,
    cwd: Option<String>,
    cols: Option<u16>,
    rows: Option<u16>,
) -> Result<String, String> {
    let pty_system = native_pty_system();
    let size = PtySize {
        rows: rows.unwrap_or(24),
        cols: cols.unwrap_or(80),
        pixel_width: 0,
        pixel_height: 0,
    };
    let pair = pty_system.openpty(size).map_err(|e| e.to_string())?;

    let mut cmd = shell_command();
    if let Some(dir) = cwd.filter(|d| !d.is_empty()) {
        cmd.cwd(dir);
    }

    let _child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;
    drop(pair.slave);

    let mut reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;

    let id = format!("pty-{}", PTY_SEQ.fetch_add(1, Ordering::Relaxed));
    let master = Arc::new(Mutex::new(pair.master));
    let writer_arc = Arc::new(Mutex::new(writer));

    {
        let mut map = state.sessions.lock().map_err(|e| e.to_string())?;
        map.insert(
            id.clone(),
            PtyHandle {
                master: master.clone(),
                writer: writer_arc.clone(),
            },
        );
    }

    let app_bg = app.clone();
    let id_bg = id.clone();
    tauri::async_runtime::spawn(async move {
        let mut buf = [0u8; 8192];
        loop {
            match reader.read(&mut buf) {
                Ok(0) => break,
                Ok(n) => {
                    let chunk = String::from_utf8_lossy(&buf[..n]).to_string();
                    let _ = app_bg.emit(
                        "pty-output",
                        PtyOutputEvent {
                            id: id_bg.clone(),
                            data: chunk,
                        },
                    );
                }
                Err(_) => break,
            }
        }
        let _ = app_bg.emit("pty-exit", serde_json::json!({ "id": id_bg }));
    });

    Ok(id)
}

#[tauri::command]
pub fn pty_write(state: State<'_, PtyState>, id: String, data: String) -> Result<(), String> {
    let map = state.sessions.lock().map_err(|e| e.to_string())?;
    let handle = map.get(&id).ok_or_else(|| "pty session not found".to_string())?;
    let mut writer = handle.writer.lock().map_err(|e| e.to_string())?;
    writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
    writer.flush().map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn pty_resize(
    state: State<'_, PtyState>,
    id: String,
    cols: u16,
    rows: u16,
) -> Result<(), String> {
    let map = state.sessions.lock().map_err(|e| e.to_string())?;
    let handle = map.get(&id).ok_or_else(|| "pty session not found".to_string())?;
    let master = handle.master.lock().map_err(|e| e.to_string())?;
    master
        .resize(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn pty_kill(state: State<'_, PtyState>, id: String) -> Result<(), String> {
    let mut map = state.sessions.lock().map_err(|e| e.to_string())?;
    map.remove(&id);
    Ok(())
}
