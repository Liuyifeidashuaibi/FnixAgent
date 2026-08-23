use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyString};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// Built-in sensitive keywords and egress hints
const BUILT_IN_KEYWORDS: &[&str] = &[
    "password", "passwd", "pwd", "secret", "token", "api_key",
    "api_secret", "access_key", "secret_key", "private_key",
    "ssh_key", "jwt", "bearer", "auth",
];

const BUILT_IN_EGRESS_HINTS: &[&str] = &[
    "curl", "wget", "fetch", "http", "https", "webhook",
    "upload", "post", "put", "send", "exfil", "leak",
];

#[derive(Deserialize, Clone)]
struct EncodedExfilConfig {
    min_suspicion_score: u32,
    min_encoded_length: usize,
    min_entropy: f64,
    printable_ratio_threshold: f64,
    allowlist_patterns: Vec<String>,
    per_encoding_score: HashMap<String, u32>,
    extra_sensitive_keywords: Vec<String>,
    extra_egress_hints: Vec<String>,
    max_decode_depth: u32,
    parse_json_strings: bool,
    max_recursion_depth: u32,
    log_detections: bool,
    block_on_detection: bool,
    redact_enabled: bool,
    min_findings_to_block: u32,
}

#[pyclass]
#[derive(Clone)]
pub struct ExfilDetectorEngine {
    config: EncodedExfilConfig,
    allowlist_regexes: Vec<Regex>,
    sensitive_keywords: Vec<Vec<u8>>,
    egress_hints: Vec<String>,
}

#[pymethods]
impl ExfilDetectorEngine {
    #[new]
    fn new(config_dict: &PyDict) -> PyResult<Self> {
        // Parse config from Python dict
        let config: EncodedExfilConfig = serde_json::from_str(
            &serde_json::to_string(config_dict)?
        )?;
        
        // Compile allowlist regexes
        let mut allowlist_regexes = Vec::new();
        for pattern in &config.allowlist_patterns {
            let regex = Regex::new(pattern)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(
                    format!("Invalid regex pattern '{}': {}", pattern, e)
                ))?;
            allowlist_regexes.push(regex);
        }
        
        // Pre-encode sensitive keywords
        let mut sensitive_keywords = Vec::new();
        let all_keywords = [
            BUILT_IN_KEYWORDS,
            &config.extra_sensitive_keywords[..],
        ].concat();
        
        for keyword in all_keywords {
            sensitive_keywords.push(keyword.as_bytes().to_vec());
        }
        
        // Lowercase egress hints
        let mut egress_hints = Vec::new();
        let all_egress = [
            BUILT_IN_EGRESS_HINTS,
            &config.extra_egress_hints[..],
        ].concat();
        
        for hint in all_egress {
            egress_hints.push(hint.to_lowercase());
        }
        
        Ok(Self {
            config,
            allowlist_regexes,
            sensitive_keywords,
            egress_hints,
        })
    }
    
    fn scan(&self, container: &PyAny) -> PyResult<PyObject> {
        let findings = self.scan_container(container, 0)?;
        
        // Build result dict
        let py = container.py();
        let result_dict = PyDict::new(py);
        result_dict.set_item("count", findings.len())?;
        result_dict.set_item("findings", findings)?;
        result_dict.set_item("redacted", false)?; // Redaction not implemented in this version
        
        Ok(result_dict.into())
    }
}

impl ExfilDetectorEngine {
    fn scan_container(&self, container: &PyAny, depth: u32) -> PyResult<Vec<PyObject>> {
        if depth >= self.config.max_recursion_depth {
            return Ok(Vec::new());
        }
        
        let py = container.py();
        let mut findings = Vec::new();
        
        if container.is_instance_of::<PyString>() {
            let text = container.extract::<String>()?;
            let text_findings = self.scan_text(&text, 1)?;
            findings.extend(text_findings);
        } else if container.is_instance_of::<PyDict>() {
            let dict = container.downcast::<PyDict>()?;
            for (key, value) in dict.iter() {
                // Scan key if it's a string
                if key.is_instance_of::<PyString>() {
                    let key_str = key.extract::<String>()?;
                    let key_findings = self.scan_text(&key_str, depth + 1)?;
                    findings.extend(key_findings);
                }
                
                // Scan value
                let value_findings = self.scan_container(value, depth + 1)?;
                findings.extend(value_findings);
            }
        } else if container.is_instance_of::<PyList>() {
            let list = container.downcast::<PyList>()?;
            for item in list.iter() {
                let item_findings = self.scan_container(item, depth + 1)?;
                findings.extend(item_findings);
            }
        }
        
        Ok(findings)
    }
    
    fn scan_text(&self, text: &str, decode_depth: u32) -> PyResult<Vec<PyObject>> {
        let py = pyo3::Python::acquire_gil();
        let py = py.python();
        
        // Check allowlist
        for regex in &self.allowlist_regexes {
            if regex.is_match(text) {
                return Ok(Vec::new());
            }
        }
        
        let mut findings = Vec::new();
        
        // Base64 pattern
        let base64_regex = Regex::new(r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?").unwrap();
        for cap in base64_regex.captures_iter(text) {
            let candidate = cap[0].to_string();
            if candidate.len() < self.config.min_encoded_length {
                continue;
            }
            
            // Try to decode
            let decoded = match base64::decode(&candidate) {
                Ok(bytes) => bytes,
                Err(_) => continue,
            };
            
            // Score
            let mut score = 0;
            score += 1; // decodable
            
            // Entropy calculation (simplified)
            let entropy = self.calculate_entropy(&decoded);
            if entropy >= self.config.min_entropy {
                score += 1;
            }
            
            // Printable check
            let printable_ratio = self.calculate_printable_ratio(&decoded);
            if printable_ratio >= self.config.printable_ratio_threshold {
                score += 1;
            }
            
            // Sensitive keywords
            let decoded_str = String::from_utf8_lossy(&decoded);
            for keyword in &self.sensitive_keywords {
                let keyword_str = std::str::from_utf8(keyword).unwrap_or("");
                if decoded_str.to_lowercase().contains(&keyword_str.to_lowercase()) {
                    score += 2;
                    break;
                }
            }
            
            // Egress hints
            for hint in &self.egress_hints {
                if text.to_lowercase().contains(hint) || decoded_str.to_lowercase().contains(hint) {
                    score += 1;
                    break;
                }
            }
            
            // Long segment
            if candidate.len() >= 2 * self.config.min_encoded_length {
                score += 1;
            }
            
            // Threshold check
            let threshold = *self.config.per_encoding_score.get("base64").unwrap_or(&self.config.min_suspicion_score);
            if score >= threshold {
                let finding_dict = PyDict::new(py);
                finding_dict.set_item("encoding", "base64")?;
                finding_dict.set_item("score", score)?;
                finding_dict.set_item("candidate", &candidate)?;
                finding_dict.set_item("decoded_length", decoded.len())?;
                finding_dict.set_item("entropy", entropy)?;
                
                findings.push(finding_dict.into());
            }
        }
        
        Ok(findings)
    }
    
    fn calculate_entropy(&self, data: &[u8]) -> f64 {
        if data.is_empty() {
            return 0.0;
        }
        
        // Simple entropy calculation
        let mut freq = [0u64; 256];
        for &b in data {
            freq[b as usize] += 1;
        }
        
        let total = data.len() as f64;
        let mut entropy = 0.0;
        for &count in freq.iter() {
            if count > 0 {
                let probability = count as f64 / total;
                entropy -= probability * probability.log2();
            }
        }
        
        entropy
    }
    
    fn calculate_printable_ratio(&self, data: &[u8]) -> f64 {
        if data.is_empty() {
            return 1.0;
        }
        
        let printable_count = data.iter()
            .filter(|&&b| (32..=126).contains(&b) || b == 9 || b == 10 || b == 13)
            .count();
        
        printable_count as f64 / data.len() as f64
    }
}

// Backward compatible function
#[pyfunction]
fn py_scan_container(container: &PyAny, config_dict: &PyDict) -> PyResult<PyObject> {
    let engine = ExfilDetectorEngine::new(config_dict)?;
    engine.scan(container)
}

/// A Python module implemented in Rust.
#[pymodule]
fn encoded_exfil_detection(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<ExfilDetectorEngine>()?;
    m.add_function(wrap_pyfunction!(py_scan_container, m)?)?;
    Ok(())
}
