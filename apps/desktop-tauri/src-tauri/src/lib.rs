use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::time::Duration;
use tauri::{AppHandle, Manager, RunEvent, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

mod pty;
mod runtime;
mod secure;

use runtime::RuntimeState;

#[derive(Debug, Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
struct FileTreeNode {
    name: String,
    path: String,
    #[serde(rename = "type")]
    node_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    size: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    children: Option<Vec<FileTreeNode>>,
}

fn should_skip(name: &str) -> bool {
    name.starts_with('.') || name == "node_modules"
}

fn read_directory_tree(dir_path: &Path, max_depth: usize, depth: usize) -> Vec<FileTreeNode> {
    if depth >= max_depth {
        return vec![];
    }
    let entries = match fs::read_dir(dir_path) {
        Ok(e) => e,
        Err(_) => return vec![],
    };

    let mut nodes = Vec::new();
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if should_skip(&name) {
            continue;
        }
        let full_path = entry.path();
        let path_str = full_path.to_string_lossy().to_string();
        if full_path.is_dir() {
            nodes.push(FileTreeNode {
                name,
                path: path_str,
                node_type: "directory".to_string(),
                size: None,
                children: Some(read_directory_tree(&full_path, max_depth, depth + 1)),
            });
        } else {
            let size = fs::metadata(&full_path).ok().map(|m| m.len());
            nodes.push(FileTreeNode {
                name,
                path: path_str,
                node_type: "file".to_string(),
                size,
                children: None,
            });
        }
    }

    nodes.sort_by(|a, b| {
        if a.node_type != b.node_type {
            return if a.node_type == "directory" {
                std::cmp::Ordering::Less
            } else {
                std::cmp::Ordering::Greater
            };
        }
        a.name.to_lowercase().cmp(&b.name.to_lowercase())
    });
    nodes
}

fn read_directory_shallow(dir_path: &Path) -> Vec<FileTreeNode> {
    let entries = match fs::read_dir(dir_path) {
        Ok(e) => e,
        Err(_) => return vec![],
    };
    let mut nodes = Vec::new();
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        if should_skip(&name) {
            continue;
        }
        let full_path = entry.path();
        let path_str = full_path.to_string_lossy().to_string();
        if full_path.is_dir() {
            nodes.push(FileTreeNode {
                name,
                path: path_str,
                node_type: "directory".to_string(),
                size: None,
                children: None,
            });
        } else {
            let size = fs::metadata(&full_path).ok().map(|m| m.len());
            nodes.push(FileTreeNode {
                name,
                path: path_str,
                node_type: "file".to_string(),
                size,
                children: None,
            });
        }
    }
    nodes.sort_by(|a, b| {
        if a.node_type != b.node_type {
            return if a.node_type == "directory" {
                std::cmp::Ordering::Less
            } else {
                std::cmp::Ordering::Greater
            };
        }
        a.name.to_lowercase().cmp(&b.name.to_lowercase())
    });
    nodes
}

fn api_base_from_state(state: &RuntimeState) -> String {
    runtime::read_config(state).api_base
}

#[tauri::command]
async fn backend_health(state: State<'_, RuntimeState>) -> Result<Value, String> {
    let url = format!("{}/health", api_base_from_state(&state).trim_end_matches('/'));
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(8))
        .build()
        .map_err(|e| e.to_string())?;
    match client.get(&url).send().await {
        Ok(resp) if resp.status().is_success() => {
            let data = resp.json::<Value>().await.unwrap_or(json!({}));
            Ok(json!({ "ok": true, "data": data }))
        }
        Ok(resp) => Ok(json!({
            "ok": false,
            "status": resp.status().as_u16(),
            "error": resp.status().canonical_reason().unwrap_or("HTTP error")
        })),
        Err(err) => Ok(json!({
            "ok": false,
            "status": 0,
            "error": err.to_string()
        })),
    }
}

#[tauri::command]
fn fs_open_folder(app: AppHandle) -> Result<Option<String>, String> {
    let picked = app
        .dialog()
        .file()
        .set_title("选择工作区文件夹")
        .blocking_pick_folder();
    Ok(picked.map(|p| p.to_string()))
}

#[tauri::command]
fn fs_open_files(app: AppHandle) -> Result<Vec<String>, String> {
    let picked = app
        .dialog()
        .file()
        .set_title("选择任务附件")
        .blocking_pick_files();
    Ok(picked
        .unwrap_or_default()
        .into_iter()
        .map(|p| p.to_string())
        .collect())
}

#[tauri::command]
fn fs_read_tree(dir_path: String) -> Result<Vec<FileTreeNode>, String> {
    let path = Path::new(&dir_path);
    if !path.is_dir() {
        return Ok(vec![]);
    }
    Ok(read_directory_tree(path, 5, 0))
}

#[tauri::command]
fn fs_read_dir(dir_path: String) -> Result<Vec<FileTreeNode>, String> {
    let path = Path::new(&dir_path);
    if !path.is_dir() {
        return Ok(vec![]);
    }
    Ok(read_directory_shallow(path))
}

// 安全说明：以下危险命令（fs_read_file / fs_write_file / fs_create_file /
// fs_create_dir / fs_delete / fs_rename）此前对任意绝对路径执行读写、递归删除，
// 且无路径校验（fs_delete 使用 remove_dir_all 可删除任意目录），构成严重攻击面。
// 经全仓库核查，前端（workbench/dist）实际通过 apps/workbench/src-tauri 的
// read_directory 命令（带 ProjectRoot 路径校验）读写文件，从未 invoke 上述命令，
// 因此此处直接移除该攻击面。如需文件读写，请走带路径白名单的工作区命令。

#[tauri::command]
fn shell_open_external(app: AppHandle, url: String) -> Result<bool, String> {
    app.opener()
        .open_url(&url, None::<&str>)
        .map(|_| true)
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn shell_open_path(app: AppHandle, target_path: String) -> Value {
    match app.opener().open_path(&target_path, None::<&str>) {
        Ok(()) => json!({ "ok": true }),
        Err(err) => json!({ "ok": false, "error": err.to_string() }),
    }
}

// 安全说明：shell_exec 此前将任意命令字符串直接传给 `cmd /C` 或 `sh -lc`，
// 且无白名单/沙箱，`_timeout_ms` 参数声明但未使用（无超时保护）。这属于任意
// 命令执行（RCE）风险。经全仓库核查，前端从未 invoke 该命令（终端功能由 pty::*
// 命令与 Rust 内部 sidecar 提供），因此直接移除该攻击面。
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(RuntimeState::default())
        .manage(pty::PtyState::default())
        .invoke_handler(tauri::generate_handler![
            backend_health,
            runtime::runtime_get_config,
            runtime::runtime_bootstrap,
            secure::secure_set,
            secure::secure_get,
            secure::secure_delete,
            fs_open_folder,
            fs_open_files,
            fs_read_tree,
            fs_read_dir,
            shell_open_external,
            shell_open_path,
            pty::pty_spawn,
            pty::pty_write,
            pty::pty_resize,
            pty::pty_kill,
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            tauri::async_runtime::block_on(async move {
                let _ = runtime::bootstrap(&handle).await;
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                runtime::shutdown(app.state::<RuntimeState>().inner());
            }
        });
}
