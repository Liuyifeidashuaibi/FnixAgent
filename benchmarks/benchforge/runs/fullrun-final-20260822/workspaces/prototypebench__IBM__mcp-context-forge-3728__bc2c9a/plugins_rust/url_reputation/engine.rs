use std::collections::HashSet;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use std::str::FromStr;

/// URL reputation validation result
#[derive(Debug, Clone, PartialEq)]
pub struct ValidationResult {
    pub is_malicious: bool,
    pub confidence: f64,
    pub reasons: Vec<String>,
}

impl ValidationResult {
    pub fn new(is_malicious: bool, confidence: f64, reasons: Vec<String>) -> Self {
        Self {
            is_malicious,
            confidence,
            reasons,
        }
    }
}

/// Main URL reputation validator
pub struct URLReputationValidator {
    // Domain whitelists and blacklists
    domain_whitelist: HashSet<String>,
    domain_blacklist: HashSet<String>,
    // TLD validation
    iana_tlds: HashSet<String>,
    // Pattern-based filters
    malicious_patterns: Vec<regex::Regex>,
    benign_patterns: Vec<regex::Regex>,
}

impl URLReputationValidator {
    pub fn new() -> Self {
        // Initialize with common TLDs (in a real implementation, this would be loaded from IANA)
        let mut iana_tlds = HashSet::new();
        iana_tlds.insert("com".to_string());
        iana_tlds.insert("org".to_string());
        iana_tlds.insert("net".to_string());
        iana_tlds.insert("edu".to_string());
        iana_tlds.insert("gov".to_string());
        iana_tlds.insert("mil".to_string());
        iana_tlds.insert("int".to_string());
        
        Self {
            domain_whitelist: HashSet::new(),
            domain_blacklist: HashSet::new(),
            iana_tlds,
            malicious_patterns: Vec::new(),
            benign_patterns: Vec::new(),
        }
    }
    
    /// Add a domain to whitelist
    pub fn add_to_whitelist(&mut self, domain: &str) {
        self.domain_whitelist.insert(domain.to_lowercase());
    }
    
    /// Add a domain to blacklist
    pub fn add_to_blacklist(&mut self, domain: &str) {
        self.domain_blacklist.insert(domain.to_lowercase());
    }
    
    /// Add malicious pattern regex
    pub fn add_malicious_pattern(&mut self, pattern: &str) {
        if let Ok(re) = regex::Regex::new(pattern) {
            self.malicious_patterns.push(re);
        }
    }
    
    /// Add benign pattern regex
    pub fn add_benign_pattern(&mut self, pattern: &str) {
        if let Ok(re) = regex::Regex::new(pattern) {
            self.benign_patterns.push(re);
        }
    }
    
    /// Calculate Shannon entropy for a string
    fn calculate_entropy(s: &str) -> f64 {
        if s.is_empty() {
            return 0.0;
        }
        
        let mut char_counts = std::collections::HashMap::new();
        for c in s.chars() {
            *char_counts.entry(c).or_insert(0) += 1;
        }
        
        let total_chars = s.chars().count() as f64;
        let mut entropy = 0.0;
        
        for &count in char_counts.values() {
            let probability = count as f64 / total_chars;
            entropy -= probability * probability.log2();
        }
        
        entropy
    }
    
    /// Check if domain is in IANA TLD list
    fn is_valid_tld(&self, tld: &str) -> bool {
        self.iana_tlds.contains(tld)
    }
    
    /// Detect homoglyphs (simplified version)
    fn has_homoglyphs(&self, domain: &str) -> bool {
        // Check for common homoglyph characters
        let homoglyph_chars = [
            'а', 'е', 'о', 'р', 'с', 'у', 'х', // Cyrillic lookalikes
            'α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η', // Greek lookalikes
        ];
        
        domain.chars().any(|c| homoglyph_chars.contains(&c))
    }
    
    /// Parse URL and extract components
    fn parse_url(&self, url: &str) -> Option<(String, String, String)> {
        // Simple URL parsing for demonstration
        let url = url.trim();
        
        // Remove protocol
        let url_no_proto = if url.starts_with("https://") {
            &url[8..]
        } else if url.starts_with("http://") {
            &url[7..]
        } else {
            url
        };
        
        // Extract domain and path
        let parts: Vec<&str> = url_no_proto.split('/').collect();
        if parts.is_empty() {
            return None;
        }
        
        let domain_part = parts[0];
        
        // Split domain into subdomain, domain, tld
        let domain_parts: Vec<&str> = domain_part.split('.').collect();
        if domain_parts.len() < 2 {
            return None;
        }
        
        let tld = domain_parts.last()?.to_lowercase();
        let domain = domain_parts.get(domain_parts.len() - 2)?.to_lowercase();
        let subdomain = if domain_parts.len() > 2 {
            domain_parts[0..domain_parts.len()-2].join(".")
        } else {
            String::new()
        };
        
        Some((subdomain, domain, tld))
    }
    
    /// Main validation method
    pub fn validate_url(&self, url: &str) -> ValidationResult {
        let mut reasons = Vec::new();
        let mut is_malicious = false;
        let mut confidence = 0.0;
        
        // Parse URL
        let parsed = self.parse_url(url);
        if parsed.is_none() {
            reasons.push("Invalid URL format".to_string());
            return ValidationResult::new(true, 0.9, reasons);
        }
        
        let (subdomain, domain, tld) = parsed.unwrap();
        
        // Check IANA TLD
        if !self.is_valid_tld(&tld) {
            reasons.push(format!("Invalid TLD: {}", tld));
            is_malicious = true;
            confidence = confidence.max(0.7);
        }
        
        // Check domain blacklist
        let full_domain = if subdomain.is_empty() {
            format!("{}.{}", domain, tld)
        } else {
            format!("{}.{}.{}", subdomain, domain, tld)
        };
        
        if self.domain_blacklist.contains(&full_domain.to_lowercase()) {
            reasons.push(format!("Domain in blacklist: {}", full_domain));
            is_malicious = true;
            confidence = confidence.max(0.95);
        }
        
        // Check domain whitelist
        if self.domain_whitelist.contains(&full_domain.to_lowercase()) {
            reasons.push(format!("Domain in whitelist: {}", full_domain));
            is_malicious = false;
            confidence = confidence.max(0.95);
        }
        
        // Check homoglyphs
        if self.has_homoglyphs(&domain) {
            reasons.push("Homoglyphs detected in domain".to_string());
            is_malicious = true;
            confidence = confidence.max(0.8);
        }
        
        // Check entropy (high entropy suggests random/garbage domain)
        let entropy = Self::calculate_entropy(&domain);
        if entropy > 4.0 {
            reasons.push(format!("High entropy domain: {:.2}", entropy));
            is_malicious = true;
            confidence = confidence.max(0.6);
        }
        
        // Check malicious patterns
        for pattern in &self.malicious_patterns {
            if pattern.is_match(url) {
                reasons.push(format!("Matches malicious pattern: {}", pattern.as_str()));
                is_malicious = true;
                confidence = confidence.max(0.85);
            }
        }
        
        // Check benign patterns
        for pattern in &self.benign_patterns {
            if pattern.is_match(url) {
                reasons.push(format!("Matches benign pattern: {}", pattern.as_str()));
                is_malicious = false;
                confidence = confidence.max(0.85);
            }
        }
        
        // Default confidence if no issues found
        if reasons.is_empty() {
            confidence = 0.1;
        }
        
        ValidationResult::new(is_malicious, confidence, reasons)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_basic_validation() {
        let validator = URLReputationValidator::new();
        
        // Test valid URL
        let result = validator.validate_url("https://google.com");
        assert_eq!(result.is_malicious, false);
        
        // Test invalid TLD
        let result = validator.validate_url("https://example.invalidtld");
        assert_eq!(result.is_malicious, true);
        
        // Test high entropy
        let result = validator.validate_url("https://a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6.q7r8s9t0u1v2w3x4y5z6.com");
        assert_eq!(result.is_malicious, true);
    }
    
    #[test]
    fn test_homoglyph_detection() {
        let validator = URLReputationValidator::new();
        
        // Test Cyrillic homoglyph
        let result = validator.validate_url("https://gооgle.com"); // Cyrillic 'о'
        assert_eq!(result.is_malicious, true);
    }
}
