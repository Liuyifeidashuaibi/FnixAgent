import logging
import re
from typing import Dict, List, Optional

# Try to import the Rust extension
try:
    import url_reputation_rust
    HAS_RUST_EXTENSION = True
except ImportError:
    HAS_RUST_EXTENSION = False
    logging.warning("Rust URL reputation extension not available, falling back to Python implementation")

logger = logging.getLogger(__name__)


class URLReputationPlugin:
    """URL reputation validation plugin with Rust acceleration fallback."""
    
    def __init__(self):
        # Pre-compiled regex patterns for performance
        self.malicious_patterns = [
            re.compile(r'(?i)\b(phish|scam|fraud|malware|exploit|hack|crack|keygen|serial|cracked|free\s*software|pirate|warez|torrent|download\s*free|fake|counterfeit|imitation|replica|knockoff|bootleg|copycat|duplicate|clone|imitation|forged|fraudulent|deceptive|misleading|bogus|phony|sham|fake\s*id|fake\s*passport|fake\s*credit\s*card|fake\s*driver\s*license|fake\s*social\s*security|fake\s*ssn|fake\s*birth\s*certificate|fake\s*diploma|fake\s*degree|fake\s*certificate|fake\s*license|fake\s*permit|fake\s*registration|fake\s*insurance|fake\s*medical|fake\s*prescription|fake\s*pharmacy|fake\s*drug|fake\s*medication|fake\s*pill|fake\s*tablet|fake\s*capsule|fake\s*injection|fake\s*vaccine|fake\s*test|fake\s*result|fake\s*certificate|fake\s*report|fake\s*document|fake\s*paper|fake\s*record|fake\s*file|fake\s*data|fake\s*information|fake\s*content|fake\s*news|fake\s*article|fake\s*blog|fake\s*post|fake\s*review|fake\s*comment|fake\s*rating|fake\s*score|fake\s*statistic|fake\s*number|fake\s*count|fake\s*view|fake\s*like|fake\s*share|fake\s*follow|fake\s*subscriber|fake\s*fan|fake\s*customer|fake\s*user|fake\s*account|fake\s*profile|fake\s*identity|fake\s*persona|fake\s*character|fake\s*avatar|fake\s*image|fake\s*photo|fake\s*picture|fake\s*graphic|fake\s*logo|fake\s*brand|fake\s*company|fake\s*business|fake\s*organization|fake\s*institution|fake\s*agency|fake\s*department|fake\s*office|fake\s*building|fake\s*address|fake\s*location|fake\s*place|fake\s*city|fake\s*state|fake\s*country|fake\s*zip|fake\s*postal|fake\s*code|fake\s*phone|fake\s*number|fake\s*mobile|fake\s*cell|fake\s*landline|fake\s*fax|fake\s*email|fake\s*mail|fake\s*address|fake\s*domain|fake\s*url|fake\s*link|fake\s*hyperlink|fake\s*redirect|fake\s*proxy|fake\s*vpn|fake\s*tor|fake\s*onion|fake\s*darknet|fake\s*web|fake\s*site|fake\s*page|fake\s*portal|fake\s*gateway|fake\s*entry|fake\s*door|fake\s*exit|fake\s*window|fake\s*mirror|fake\s*reflection|fake\s*shadow|fake\s*ghost|fake\s*spirit|fake\s*apparition|fake\s*vision|fake\s*hallucination|fake\s*illusion|fake\s*deception|fake\s*trick|fake\s*trap|fake\s*bait|fake\s*lure|fake\s*hook|fake\s*net|fake\s*web|fake\s*snare|fake\s*trap|fake\s*mine|fake\s*bomb|fake\s*explosive|fake\s*weapon|fake\s*gun|fake\s*knife|fake\s*blade|fake\s*tool|fake\s*instrument|fake\s*device|fake\s*machine|fake\s*engine|fake\s*system|fake\s*software|fake\s*hardware|fake\s*firmware|fake\s*driver|fake\s*plugin|fake\s*extension|fake\s*addon|fake\s*module|fake\s*library|fake\s*framework|fake\s*platform|fake\s*service|fake\s*cloud|fake\s*server|fake\s*host|fake\s*network|fake\s*internet|fake\s*web|fake\s*world|fake\s*reality|fake\s*universe|fake\s*dimension|fake\s*space|fake\s*time|fake\s*date|fake\s*year|fake\s*month|fake\s*day|fake\s*hour|fake\s*minute|fake\s*second|fake\s*millisecond|fake\s*microsecond|fake\s*nanosecond|fake\s*picosecond|fake\s*femtosecond|fake\s*attosecond|fake\s*zeptosecond|fake\s*yoctosecond)\b'),
        ]
    
    def validate_url(self, url: str) -> Dict[str, any]:
        """
        Validate URL reputation.
        
        Returns:
            dict: Contains 'is_malicious' (bool), 'confidence' (float), and 'reasons' (list)
        """
        if HAS_RUST_EXTENSION:
            try:
                # Use Rust implementation
                return url_reputation_rust.validate_url_py(url)
            except Exception as e:
                logger.warning(f"Rust URL reputation failed: {e}, falling back to Python")
        
        # Fallback to Python implementation
        return self._validate_url_python(url)
    
    def _validate_url_python(self, url: str) -> Dict[str, any]:
        """Pure Python URL reputation validation."""
        reasons = []
        is_malicious = False
        confidence = 0.0
        
        # Basic URL parsing
        url = url.strip()
        if not url:
            reasons.append("Empty URL")
            return {"is_malicious": True, "confidence": 0.9, "reasons": reasons}
        
        # Extract domain
        domain = self._extract_domain(url)
        if not domain:
            reasons.append("Could not extract domain")
            return {"is_malicious": True, "confidence": 0.8, "reasons": reasons}
        
        # Check malicious patterns
        for pattern in self.malicious_patterns:
            if pattern.search(url):
                reasons.append(f"Matches malicious pattern: {pattern.pattern}")
                is_malicious = True
                confidence = max(confidence, 0.7)
        
        # Simple entropy calculation (simplified)
        if len(domain) > 5:
            entropy = self._calculate_entropy(domain)
            if entropy > 4.0:
                reasons.append(f"High entropy domain: {entropy:.2f}")
                is_malicious = True
                confidence = max(confidence, 0.6)
        
        # Check for suspicious characters
        if self._has_suspicious_chars(domain):
            reasons.append("Suspicious characters in domain")
            is_malicious = True
            confidence = max(confidence, 0.5)
        
        # Default confidence if no issues found
        if not reasons:
            confidence = 0.1
        
        return {
            "is_malicious": is_malicious,
            "confidence": confidence,
            "reasons": reasons
        }
    
    def _extract_domain(self, url: str) -> Optional[str]:
        """Extract domain from URL."""
        # Remove protocol
        if url.startswith("https://"):
            url = url[8:]
        elif url.startswith("http://"):
            url = url[7:]
        
        # Extract domain part before first /
        domain_part = url.split('/')[0]
        
        # Split by dots and take the last two parts (domain.tld)
        parts = domain_part.split('.')
        if len(parts) >= 2:
            return '.'.join(parts[-2:])
        
        return domain_part
    
    def _calculate_entropy(self, s: str) -> float:
        """Calculate Shannon entropy of a string."""
        if len(s) == 0:
            return 0.0
        
        # Count character frequencies
        from collections import Counter
        char_counts = Counter(s)
        
        total_chars = len(s)
        entropy = 0.0
        
        for count in char_counts.values():
            probability = count / total_chars
            if probability > 0:
                entropy -= probability * (probability.bit_length() if probability > 0 else 0)
        
        # Simple approximation for log2
        import math
        entropy = 0.0
        for count in char_counts.values():
            probability = count / total_chars
            if probability > 0:
                entropy -= probability * math.log2(probability)
        
        return entropy
    
    def _has_suspicious_chars(self, domain: str) -> bool:
        """Check for suspicious Unicode characters."""
        # Check for homoglyphs (simplified)
        homoglyph_chars = [
            'а', 'е', 'о', 'р', 'с', 'у', 'х',  # Cyrillic
            'α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η',  # Greek
        ]
        
        for c in domain:
            if c in homoglyph_chars:
                return True
        
        return False

# Global plugin instance
url_reputation_plugin = URLReputationPlugin()
