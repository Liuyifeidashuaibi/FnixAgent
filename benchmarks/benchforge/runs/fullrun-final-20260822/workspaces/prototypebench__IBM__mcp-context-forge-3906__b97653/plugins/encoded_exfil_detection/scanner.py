import json
import re
import base64
import binascii
from typing import Any, Dict, List, Optional, Tuple, Union, cast
import logging

from .config import EncodedExfilConfig

logger = logging.getLogger(__name__)

# Built-in encoding patterns
_BASE64_PATTERN = r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"
_BASE64URL_PATTERN = r"(?:[A-Za-z0-9_-]{4})*(?:[A-Za-z0-9_-]{2}==|[A-Za-z0-9_-]{3}=)?"
_HEX_PATTERN = r"[0-9a-fA-F]{4,}"
_PERCENT_ENCODING_PATTERN = r"%[0-9a-fA-F]{2}(?:%[0-9a-fA-F]{2})*"
_ESCAPED_HEX_PATTERN = r"\\x[0-9a-fA-F]{2}(?:\\x[0-9a-fA-F]{2})*"

# Pre-compiled regex patterns
_BASE64_REGEX = re.compile(_BASE64_PATTERN)
_BASE64URL_REGEX = re.compile(_BASE64URL_PATTERN)
_HEX_REGEX = re.compile(_HEX_PATTERN)
_PERCENT_ENCODING_REGEX = re.compile(_PERCENT_ENCODING_PATTERN)
_ESCAPED_HEX_REGEX = re.compile(_ESCAPED_HEX_PATTERN)


# Helper functions for entropy calculation
def _shannon_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of bytes"""
    if not data:
        return 0.0
    
    # Count frequency of each byte
    freq = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    
    # Calculate entropy
    entropy = 0.0
    length = len(data)
    for count in freq.values():
        probability = count / length
        entropy -= probability * (probability.bit_length() - 1 if probability > 0 else 0)
    
    return entropy


def _is_printable_ascii(data: bytes) -> bool:
    """Check if bytes are mostly printable ASCII"""
    if not data:
        return True
    
    printable_count = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
    return (printable_count / len(data)) >= 0.7


def _decode_base64(candidate: str) -> Optional[bytes]:
    """Safely decode base64"""
    try:
        # Try standard base64
        return base64.b64decode(candidate, validate=True)
    except Exception:
        try:
            # Try base64url
            return base64.urlsafe_b64decode(candidate)
        except Exception:
            return None


def _decode_hex(candidate: str) -> Optional[bytes]:
    """Safely decode hex"""
    try:
        return bytes.fromhex(candidate)
    except Exception:
        return None


def _decode_percent_encoding(candidate: str) -> Optional[bytes]:
    """Safely decode percent encoding"""
    try:
        decoded = unquote(candidate)
        return decoded.encode('utf-8')
    except Exception:
        return None


def _decode_escaped_hex(candidate: str) -> Optional[bytes]:
    """Safely decode escaped hex"""
    try:
        # Replace \xXX with %XX for unquote, or handle directly
        # Simple approach: replace \x with % and use unquote
        if candidate.startswith('\\x') or '\\x' in candidate:
            # Convert \xXX to %XX format
            import re
            converted = re.sub(r'\\x([0-9a-fA-F]{2})', r'%\1', candidate)
            return _decode_percent_encoding(converted)
        return None
    except Exception:
        return None


def _scan_text(text: str, config: EncodedExfilConfig, decode_depth: int = 1) -> Tuple[str, List[Dict[str, Any]], bool]:
    """Scan text for encoded exfiltration candidates"""
    if not isinstance(text, str):
        return text, [], False
    
    findings = []
    redacted = False
    
    # Check allowlist first
    for pattern in config._allowlist_regexes or []:
        if pattern.search(text):
            return text, [], False
    
    # Scan for each encoding type
    encoding_patterns = [
        (_BASE64_REGEX, "base64", _decode_base64),
        (_BASE64URL_REGEX, "base64url", _decode_base64),
        (_HEX_REGEX, "hex", _decode_hex),
        (_PERCENT_ENCODING_REGEX, "percent_encoding", _decode_percent_encoding),
        (_ESCAPED_HEX_REGEX, "escaped_hex", _decode_escaped_hex),
    ]
    
    for regex, encoding_type, decoder in encoding_patterns:
        matches = list(regex.finditer(text))
        for match in matches:
            candidate = match.group()
            
            # Skip if too short
            if len(candidate) < config.min_encoded_length:
                continue
            
            # Decode candidate
            decoded_bytes = decoder(candidate)
            if decoded_bytes is None:
                continue
            
            # Score the candidate
            score = 0
            
            # +1 decodable
            score += 1
            
            # +1 high entropy
            entropy = _shannon_entropy(decoded_bytes)
            if entropy >= config.min_entropy:
                score += 1
            
            # +1 printable payload
            if _is_printable_ascii(decoded_bytes):
                score += 1
            
            # +2 sensitive keywords
            decoded_text = decoded_bytes.decode('utf-8', errors='ignore')
            for keyword in config._sensitive_keywords:
                if keyword.lower() in decoded_text.lower().encode('utf-8'):
                    score += 2
                    break
            
            # +1 egress context
            for hint in config._egress_hints:
                if hint in text.lower() or hint in decoded_text.lower():
                    score += 1
                    break
            
            # +1 long segment
            if len(candidate) >= 2 * config.min_encoded_length:
                score += 1
            
            # Check threshold
            threshold = config.per_encoding_score.get(encoding_type, config.min_suspicion_score)
            if score >= threshold:
                finding = {
                    "encoding": encoding_type,
                    "score": score,
                    "start": match.start(),
                    "end": match.end(),
                    "candidate": candidate,
                    "decoded_length": len(decoded_bytes),
                    "entropy": round(entropy, 2),
                }
                findings.append(finding)
                
                # Redact if enabled
                if config.redact_enabled:
                    text = text[:match.start()] + "[REDACTED]" + text[match.end():]
                    redacted = True
            
            # Nested detection (Gap 5)
            if score < threshold and decode_depth < config.max_decode_depth:
                try:
                    nested_decoded = decoded_bytes.decode('utf-8')
                    # Recursively scan decoded text
                    nested_text, nested_findings, nested_redacted = _scan_text(
                        nested_decoded, config, decode_depth + 1
                    )
                    
                    # If nested findings have higher score, replace current finding
                    if nested_findings:
                        best_nested = max(nested_findings, key=lambda x: x.get('score', 0))
                        if best_nested.get('score', 0) > score:
                            # Replace with nested finding
                            nested_finding = {
                                **best_nested,
                                "nested_in": encoding_type,
                                "nested_candidate": candidate,
                            }
                            findings[-1] = nested_finding
                            
                            if config.redact_enabled:
                                text = text[:match.start()] + "[REDACTED]" + text[match.end():]
                                redacted = True
                except Exception:
                    pass
    
    # JSON-within-strings parsing (Gap 6)
    if config.parse_json_strings:
        try:
            # Try to parse as JSON
            json_obj = json.loads(text)
            if isinstance(json_obj, (dict, list)):
                # Recursively scan the parsed JSON
                scanned_json, json_findings, json_redacted = _scan_container(
                    json_obj, config, depth=1
                )
                
                # Merge findings
                findings.extend(json_findings)
                
                if config.redact_enabled and json_redacted:
                    # Convert back to string for redaction
                    try:
                        text = json.dumps(scanned_json)
                        redacted = True
                    except Exception:
                        pass
        except json.JSONDecodeError:
            pass
    
    return text, findings, redacted


def _scan_container(container: Any, config: EncodedExfilConfig, depth: int = 0) -> Tuple[Any, List[Dict[str, Any]], bool]:
    """Recursively scan container (dict, list, str) for encoded exfiltration"""
    if depth >= config.max_recursion_depth:
        return container, [], False
    
    findings = []
    redacted = False
    
    if isinstance(container, str):
        # Scan string
        result_text, string_findings, string_redacted = _scan_text(container, config)
        findings.extend(string_findings)
        if string_redacted:
            redacted = True
        return result_text, findings, redacted
    
    elif isinstance(container, dict):
        # Scan dictionary
        new_dict = {}
        for key, value in container.items():
            if isinstance(key, str):
                # Scan key
                key_text, key_findings, key_redacted = _scan_text(key, config)
                new_key = key_text
                findings.extend(key_findings)
                if key_redacted:
                    redacted = True
            else:
                new_key = key
            
            # Scan value
            new_value, value_findings, value_redacted = _scan_container(value, config, depth + 1)
            findings.extend(value_findings)
            if value_redacted:
                redacted = True
            
            new_dict[new_key] = new_value
        
        return new_dict, findings, redacted
    
    elif isinstance(container, list):
        # Scan list
        new_list = []
        for item in container:
            new_item, item_findings, item_redacted = _scan_container(item, config, depth + 1)
            findings.extend(item_findings)
            if item_redacted:
                redacted = True
            new_list.append(new_item)
        
        return new_list, findings, redacted
    
    else:
        # Non-container types
        return container, [], False


def scan_container(container: Any, config: EncodedExfilConfig) -> Dict[str, Any]:
    """Main entry point for scanning a container"""
    try:
        scanned_container, findings, redacted = _scan_container(container, config)
        
        return {
            "count": len(findings),
            "findings": findings,
            "redacted": redacted,
            "scanned_container": scanned_container if redacted else None,
        }
    
    except Exception as e:
        logger.error(f"Error scanning container: {e}")
        return {
            "count": 0,
            "findings": [],
            "redacted": False,
        }
