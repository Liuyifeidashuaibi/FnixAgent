//! OS credential-store bridge for BYOK secrets.

use keyring::Entry;

const SERVICE: &str = "com.fnix.agent";

fn entry(key: &str) -> Result<Entry, String> {
    if key.trim().is_empty() {
        return Err("credential key must not be empty".to_string());
    }
    Entry::new(SERVICE, key).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn secure_set(key: String, value: String) -> Result<(), String> {
    entry(&key)?
        .set_password(&value)
        .map_err(|error| error.to_string())
}

#[tauri::command]
pub fn secure_get(key: String) -> Result<String, String> {
    match entry(&key)?.get_password() {
        Ok(value) => Ok(value),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(error) => Err(error.to_string()),
    }
}

#[tauri::command]
pub fn secure_delete(key: String) -> Result<(), String> {
    match entry(&key)?.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(error.to_string()),
    }
}
