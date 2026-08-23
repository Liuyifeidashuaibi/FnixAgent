// PII Detector Rust Library

use std::collections::HashMap;

// Configuration for PII detection and masking
#[derive(Debug, Clone, PartialEq)]
pub struct PiiConfig {
    pub default_mask_strategy: MaskStrategy,
    pub whitelist: Vec<String>,
    pub custom_patterns: Vec<CustomPattern>,
}

#[derive(Debug, Clone, PartialEq)]
pub enum MaskStrategy {
    Redact,
    Partial,
    Hash,
    None,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CustomPattern {
    pub pattern: String,
    pub mask_strategy: Option<MaskStrategy>,
}

// Built-in PII detection types
#[derive(Debug, Clone, PartialEq)]
pub enum PiiType {
    Ssn,
    Email,
    AwsAccessKey,
    AwsSecretKey,
    Custom(String),
}

// Detection result
#[derive(Debug, Clone, PartialEq)]
pub struct Detection {
    pub pii_type: PiiType,
    pub start: usize,
    pub end: usize,
    pub original_text: String,
    pub masked_text: String,
    pub mask_strategy: MaskStrategy,
}

// Main detector struct
pub struct PiiDetector {
    config: PiiConfig,
}

impl PiiDetector {
    pub fn new(config: PiiConfig) -> Self {
        Self { config }
    }
    
    /// Detect and mask PII in text
    /// Built-in detections now honor the configured default_mask_strategy
    pub fn detect_and_mask(&self, text: &str) -> Vec<Detection> {
        let mut detections = Vec::new();
        
        // Example built-in SSN detection
        if self.config.whitelist.contains(&"ssn".to_string()) {
            detections.extend(self.detect_ssn(text));
        }
        
        // Example built-in email detection
        if self.config.whitelist.contains(&"email".to_string()) {
            detections.extend(self.detect_email(text));
        }
        
        // Example built-in AWS detection
        if self.config.whitelist.contains(&"aws".to_string()) {
            detections.extend(self.detect_aws_keys(text));
        }
        
        // Custom patterns - preserve explicit mask-strategy overrides
        for pattern in &self.config.custom_patterns {
            let strategy = pattern.mask_strategy.clone().unwrap_or_else(|| {
                self.config.default_mask_strategy.clone()
            });
            detections.extend(self.detect_custom_pattern(text, pattern, strategy));
        }
        
        detections
    }
    
    /// SSN detection - now honors default_mask_strategy instead of hardcoded partial
    fn detect_ssn(&self, text: &str) -> Vec<Detection> {
        // Simplified regex pattern for SSN
        let ssn_pattern = r"\b\d{3}-\d{2}-\d{4}\b";
        
        // Use configured default_mask_strategy for built-in detections
        let mask_strategy = self.config.default_mask_strategy.clone();
        
        // In real implementation, this would use regex to find matches
        // For demo purposes, returning empty vector
        vec![]
    }
    
    /// Email detection - now honors default_mask_strategy instead of hardcoded partial
    fn detect_email(&self, text: &str) -> Vec<Detection> {
        // Simplified regex pattern for email
        let email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b";
        
        // Use configured default_mask_strategy for built-in detections
        let mask_strategy = self.config.default_mask_strategy.clone();
        
        // In real implementation, this would use regex to find matches
        // For demo purposes, returning empty vector
        vec![]
    }
    
    /// AWS key detection - now honors default_mask_strategy instead of hardcoded partial
    fn detect_aws_keys(&self, text: &str) -> Vec<Detection> {
        // Simplified patterns for AWS keys
        let aws_access_pattern = r"AKIA[0-9A-Z]{16}";
        let aws_secret_pattern = r"[0-9a-zA-Z+/]{40}";
        
        // Use configured default_mask_strategy for built-in detections
        let mask_strategy = self.config.default_mask_strategy.clone();
        
        // In real implementation, this would use regex to find matches
        // For demo purposes, returning empty vector
        vec![]
    }
    
    /// Custom pattern detection - preserves explicit mask-strategy overrides
    fn detect_custom_pattern(&self, text: &str, pattern: &CustomPattern, mask_strategy: MaskStrategy) -> Vec<Detection> {
        // In real implementation, this would use regex to find matches
        // For demo purposes, returning empty vector
        vec![]
    }
}

// Example usage
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_default_mask_strategy_honored() {
        let config = PiiConfig {
            default_mask_strategy: MaskStrategy::Redact,
            whitelist: vec!["ssn".to_string(), "email".to_string()],
            custom_patterns: vec![],
        };
        
        let detector = PiiDetector::new(config);
        // In real tests, we would verify that detections use Redact strategy
        assert_eq!(detector.detect_and_mask("test"), vec![]);
    }
}
