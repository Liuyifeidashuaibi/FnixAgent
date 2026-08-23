//! OS Keychain 安全存储 — 对接 @fnixagent/sdk ElectronTokenStorage
use keyring::Entry;

const SERVICE: &str = "com.fnix.agent";

fn entry(key: &str) -> Result<Entry, String> {
    Entry::new(SERVICE, key).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn secure_set(key: String, value: String) -> Result<String, String> {
    entry(&key)?
        .set_password(&value)
        .map_err(|e| e.to_string())?;
    Ok(value)
}

#[tauri::command]
pub fn secure_get(key: String) -> Result<String, String> {
    match entry(&key)?.get_password() {
        Ok(v) => Ok(v),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
pub fn secure_delete(key: String) -> Result<(), String> {
    match entry(&key)?.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
