use pyo3::prelude::*;
use pyo3::wrap_pyfunction;

// Re-export the engine
mod engine;
use engine::{URLReputationValidator, ValidationResult};

/// Python wrapper for URL reputation validation
#[pyfunction]
fn validate_url_py(url: &str) -> PyResult<PyObject> {
    Python::with_gil(|py| {
        let validator = URLReputationValidator::new();
        
        // Add some default malicious patterns
        validator.add_malicious_pattern(r"(?i)\b(phish|scam|fraud|malware|exploit|hack|crack|keygen|serial|cracked|free\s*software|pirate|warez|torrent|download\s*free|fake|counterfeit|imitation|replica|knockoff|bootleg|copycat|duplicate|clone|imitation|forged|fraudulent|deceptive|misleading|bogus|phony|sham|fake\s*id|fake\s*passport|fake\s*credit\s*card|fake\s*driver\s*license|fake\s*social\s*security|fake\s*ssn|fake\s*birth\s*certificate|fake\s*diploma|fake\s*degree|fake\s*certificate|fake\s*license|fake\s*permit|fake\s*registration|fake\s*insurance|fake\s*medical|fake\s*prescription|fake\s*pharmacy|fake\s*drug|fake\s*medication|fake\s*pill|fake\s*tablet|fake\s*capsule|fake\s*injection|fake\s*vaccine|fake\s*test|fake\s*result|fake\s*certificate|fake\s*report|fake\s*document|fake\s*paper|fake\s*record|fake\s*file|fake\s*data|fake\s*information|fake\s*content|fake\s*news|fake\s*article|fake\s*blog|fake\s*post|fake\s*review|fake\s*comment|fake\s*rating|fake\s*score|fake\s*statistic|fake\s*number|fake\s*count|fake\s*view|fake\s*like|fake\s*share|fake\s*follow|fake\s*subscriber|fake\s*fan|fake\s*customer|fake\s*user|fake\s*account|fake\s*profile|fake\s*identity|fake\s*persona|fake\s*character|fake\s*avatar|fake\s*image|fake\s*photo|fake\s*picture|fake\s*graphic|fake\s*logo|fake\s*brand|fake\s*company|fake\s*business|fake\s*organization|fake\s*institution|fake\s*agency|fake\s*department|fake\s*office|fake\s*building|fake\s*address|fake\s*location|fake\s*place|fake\s*city|fake\s*state|fake\s*country|fake\s*zip|fake\s*postal|fake\s*code|fake\s*phone|fake\s*number|fake\s*mobile|fake\s*cell|fake\s*landline|fake\s*fax|fake\s*email|fake\s*mail|fake\s*address|fake\s*domain|fake\s*url|fake\s*link|fake\s*hyperlink|fake\s*redirect|fake\s*proxy|fake\s*vpn|fake\s*tor|fake\s*onion|fake\s*darknet|fake\s*web|fake\s*site|fake\s*page|fake\s*portal|fake\s*gateway|fake\s*entry|fake\s*door|fake\s*exit|fake\s*window|fake\s*mirror|fake\s*reflection|fake\s*shadow|fake\s*ghost|fake\s*spirit|fake\s*apparition|fake\s*vision|fake\s*hallucination|fake\s*illusion|fake\s*deception|fake\s*trick|fake\s*trap|fake\s*bait|fake\s*lure|fake\s*hook|fake\s*net|fake\s*web|fake\s*snare|fake\s*trap|fake\s*mine|fake\s*bomb|fake\s*explosive|fake\s*weapon|fake\s*gun|fake\s*knife|fake\s*blade|fake\s*tool|fake\s*instrument|fake\s*device|fake\s*machine|fake\s*engine|fake\s*system|fake\s*software|fake\s*hardware|fake\s*firmware|fake\s*driver|fake\s*plugin|fake\s*extension|fake\s*addon|fake\s*module|fake\s*library|fake\s*framework|fake\s*platform|fake\s*service|fake\s*cloud|fake\s*server|fake\s*host|fake\s*network|fake\s*internet|fake\s*web|fake\s*world|fake\s*reality|fake\s*universe|fake\s*dimension|fake\s*space|fake\s*time|fake\s*date|fake\s*year|fake\s*month|fake\s*day|fake\s*hour|fake\s*minute|fake\s*second|fake\s*millisecond|fake\s*microsecond|fake\s*nanosecond|fake\s*picosecond|fake\s*femtosecond|fake\s*attosecond|fake\s*zeptosecond|fake\s*yoctosecond)\b");
        
        let result = validator.validate_url(url);
        
        // Convert to Python dict
        let py_dict = PyDict::new(py);
        py_dict.set_item("is_malicious", result.is_malicious)?;
        py_dict.set_item("confidence", result.confidence)?;
        
        let py_reasons = PyList::empty(py);
        for reason in result.reasons {
            py_reasons.append(reason)?;
        }
        py_dict.set_item("reasons", py_reasons)?;
        
        Ok(py_dict.into())
    })
}

/// Module definition
#[pymodule]
fn url_reputation_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(validate_url_py, m)?)?;
    Ok(())
}
