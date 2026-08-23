import re
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler


class EncodedExfilConfig(BaseModel):
    """
    Configuration for Encoded Exfiltration Detection Plugin
    
    All new features from gap analysis are implemented:
    - Allowlisting (Gap 1)
    - Per-encoding thresholds (Gap 2)
    - Resource post-fetch hook (Gap 3)
    - Configurable keyword/egress lists (Gap 4)
    - Nested encoding detection (Gap 5)
    - JSON-within-strings parsing (Gap 6)
    - Container recursion depth limit (Gap 7)
    - Detection logging (Gap 8)
    """
    
    # Core detection settings
    min_suspicion_score: int = Field(3, ge=0, le=10)
    min_encoded_length: int = Field(24, ge=1, le=1000)
    min_entropy: float = Field(3.3, ge=0.0, le=8.0)
    printable_ratio_threshold: float = Field(0.7, ge=0.0, le=1.0)
    
    # Allowlisting (Gap 1)
    allowlist_patterns: List[str] = Field(default_factory=list)
    
    # Per-encoding thresholds (Gap 2)
    per_encoding_score: Dict[str, int] = Field(default_factory=dict)
    
    # Configurable keywords and egress hints (Gap 4)
    extra_sensitive_keywords: List[str] = Field(default_factory=list)
    extra_egress_hints: List[str] = Field(default_factory=list)
    
    # Nested encoding detection (Gap 5)
    max_decode_depth: int = Field(2, ge=1, le=5)
    
    # JSON-within-strings parsing (Gap 6)
    parse_json_strings: bool = True
    
    # Container recursion depth limit (Gap 7)
    max_recursion_depth: int = Field(32, ge=1, le=1000)
    
    # Detection logging (Gap 8)
    log_detections: bool = True
    
    # Blocking and redaction settings
    block_on_detection: bool = True
    redact_enabled: bool = False
    min_findings_to_block: int = Field(1, ge=1)
    
    # Internal pre-compiled fields (set during model_post_init)
    _allowlist_regexes: Optional[List[re.Pattern]] = None
    _sensitive_keywords: Optional[List[bytes]] = None
    _egress_hints: Optional[List[str]] = None
    
    @field_validator('allowlist_patterns')
    @classmethod
    def validate_allowlist_patterns(cls, v):
        """Validate allowlist patterns are valid regex"""
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
        return v
    
    @field_validator('per_encoding_score')
    @classmethod
    def validate_per_encoding_score(cls, v):
        """Validate per-encoding score values"""
        for encoding, score in v.items():
            if not isinstance(score, int) or score < 0 or score > 10:
                raise ValueError(f"Invalid score {score} for encoding {encoding}: must be 0-10")
        return v
    
    @field_validator('min_findings_to_block')
    @classmethod
    def validate_min_findings_to_block(cls, v):
        if v < 1:
            raise ValueError("min_findings_to_block must be at least 1")
        return v
    
    def model_post_init(self, __context):
        """Pre-compile allowlist regexes, encode keywords, lowercase egress hints"""
        # Compile allowlist regexes
        self._allowlist_regexes = []
        for pattern in self.allowlist_patterns:
            try:
                compiled = re.compile(pattern)
                self._allowlist_regexes.append(compiled)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
        
        # Pre-encode sensitive keywords to bytes for efficient matching
        built_in_keywords = [
            "password", "passwd", "pwd", "secret", "token", "api_key", 
            "api_secret", "access_key", "secret_key", "private_key", 
            "ssh_key", "jwt", "bearer", "auth"
        ]
        all_keywords = built_in_keywords + self.extra_sensitive_keywords
        self._sensitive_keywords = [keyword.encode('utf-8') for keyword in all_keywords]
        
        # Lowercase egress hints
        built_in_egress = [
            "curl", "wget", "fetch", "http", "https", "webhook", 
            "upload", "post", "put", "send", "exfil", "leak"
        ]
        all_egress = built_in_egress + self.extra_egress_hints
        self._egress_hints = [hint.lower() for hint in all_egress]
    
    class Config:
        # Pydantic v2 compatibility
        ignored_types = (re.Pattern,)
