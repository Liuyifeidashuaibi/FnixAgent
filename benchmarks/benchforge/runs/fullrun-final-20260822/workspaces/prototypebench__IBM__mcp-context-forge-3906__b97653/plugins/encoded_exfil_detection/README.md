# Encoded Exfiltration Detection Plugin

Version 0.2.0

## Overview

The Encoded Exfiltration Detection Plugin detects suspicious encoded payloads (base64, base64url, hex, percent-encoding, hex escapes) in prompt arguments, tool outputs, and resource content. It uses a multi-factor suspicion scoring system to identify potential data exfiltration attempts.

## Features

### Core Detection
- **Multi-encoding support**: Base64, Base64URL, Hex, Percent-encoding, Escaped hex
- **Multi-factor scoring**: Decodable, high entropy, printable payload, sensitive keywords, egress context, long segment
- **Configurable thresholds**: Global minimum suspicion score and per-encoding thresholds

### Production Hardening (New in 0.2.0)
- **Allowlisting**: Regex patterns to skip known-good encoded content (JWTs, image data URIs, git SHAs)
- **Resource post-fetch hook**: Scans resource responses for encoded exfiltration
- **Configurable keyword/egress lists**: Extend built-in sensitive keywords and egress hints
- **Nested encoding detection**: Detects multi-layer obfuscation (e.g., `base64(hex(secret))`)
- **JSON-within-strings parsing**: Recursively scans JSON structures embedded in strings
- **Recursion depth limiting**: Prevents unbounded recursion in deeply nested containers
- **Detection logging**: Warning logs for detected exfiltration attempts

### Performance
- **Rust acceleration**: 4.3x–12.1x speedup when `encoded_exfil_detection_rust` wheel is installed
- **Automatic fallback**: Pure Python implementation with identical behavior when Rust is unavailable
- **Pre-compilation**: Allowlist regexes, encoded keywords, and lowercased hints compiled once at config creation

## Configuration

### Basic Settings
- `min_suspicion_score`: Minimum score to flag as finding (default: 3)
- `min_encoded_length`: Minimum length of encoded candidate (default: 24)
- `min_entropy`: Minimum Shannon entropy for high entropy check (default: 3.3)
- `printable_ratio_threshold`: Minimum ratio of printable ASCII characters (default: 0.7)

### Allowlisting
- `allowlist_patterns`: List of regex patterns to skip detection (e.g., `^[A-Za-z0-9+/]+\\.[A-Za-z0-9+/]+\\.[A-Za-z0-9+/]+$` for JWTs)

### Per-Encoding Thresholds
- `per_encoding_score`: Dictionary mapping encoding types to minimum scores (e.g., `{"hex": 5, "base64": 2}`)

### Custom Keywords and Egress Hints
- `extra_sensitive_keywords`: Additional sensitive keywords to detect (e.g., `"watsonx_api", "ibm_cloud_key"`)
- `extra_egress_hints`: Additional egress hints to detect (e.g., `"ibmcloud", "watsonx"`)

### Advanced Settings
- `max_decode_depth`: Maximum depth for nested encoding detection (default: 2, range 1-5)
- `parse_json_strings`: Whether to parse JSON within strings (default: true)
- `max_recursion_depth`: Maximum recursion depth for container scanning (default: 32, range 1-1000)
- `log_detections`: Whether to log detections (default: true)
- `block_on_detection`: Whether to block on detection (default: true)
- `redact_enabled`: Whether to redact detected content (default: false)
- `min_findings_to_block`: Minimum number of findings to trigger blocking (default: 1)

## Hooks

The plugin implements three hooks:

- `prompt_pre_fetch`: Scans prompt arguments before processing
- `tool_post_invoke`: Scans tool output after execution
- `resource_post_fetch`: Scans resource content after fetching (new in 0.2.0)

## Architecture

The plugin uses optional Rust acceleration with automatic Python fallback:

- **Python**: Plugin lifecycle, hook integration, config validation, result construction
- **Rust**: Hot path - regex matching, decoding, scoring, allowlist checking, nested decoding, JSON parsing, redaction

Both implementations share identical logic and produce identical results (verified by parity tests).

## Installation

```bash
# Install Python plugin
pip install ./plugins/encoded_exfil_detection

# Install Rust acceleration (optional, for 4.3x-12.1x speedup)
pip install encoded_exfil_detection_rust
```

## Testing

The plugin includes 112 TDD tests covering all features and edge cases.

```bash
# Run Python tests
pytest plugins/encoded_exfil_detection/tests/

# Run Rust tests
cd plugins_rust/encoded_exfil_detection && cargo test

# Run performance comparison
python plugins_rust/encoded_exfil_detection/compare_performance.py
```

## Limitations

- **Cross-request correlation**: Not tracked (stateless design)
- **Custom encoding patterns**: Not supported (security concern - ReDoS risk)
- **JSON-within-strings overhead**: Every string gets a JSON parse attempt (~1-3 microseconds)
- **Nested detection overhead**: Candidates that decode successfully but score below threshold trigger re-scans
- **Allowlist pattern matching**: Matches encoded form, not decoded content
- **OpenShift validation**: Not tested on OpenShift cluster

## License

Apache-2.0
