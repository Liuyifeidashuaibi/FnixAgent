# PII Context Forge - PII Filter

This module provides PII (Personally Identifiable Information) detection and masking capabilities for the MCP Context Forge system.

## 📚 Documentation

### Configuration

The PII filter supports various configuration options:

- `default_mask_strategy`: Controls how detected PII is masked (options: `redact`, `partial`, `hash`, `none`)
- `whitelist`: List of PII types to enable (e.g., `ssn`, `email`, `aws`)
- `custom_patterns`: Custom regex patterns with optional mask strategies

### Testing

Run unit tests with:

```bash
# Rust tests
cargo test

# Python plugin tests
pytest tests/unit/mcpgateway/plugins/plugins/pii_filter/test_pii_filter.py -q
```

### Local Development

Start the service locally using Docker Compose:

```bash
# Start services
docker-compose up -d

# Verify PII filter is running on port 8080
curl http://localhost:8080/health
```

### Manual Verification

Test the PII filter with sample prompts:

```bash
# Test with curl
curl -X POST http://localhost:8080/v1/pii/detect-and-mask \
  -H "Content-Type: application/json" \
  -d '{"text": "My SSN is 123-45-6789 and email is user@example.com"}'
```

## 🧪 Verification Matrix

| Check | Command | Status |
|-------|---------|--------|
| Lint suite | `make --no-print-directory pre-commit` | ✅ |
| Unit tests | `cargo test` and `pytest tests/unit/mcpgateway/plugins/plugins/pii_filter/test_pii_filter.py -q` | ✅ |
| Coverage ≥ 80% | Not run | N/A |

## 🛠️ Implementation Details

### Plugin Layer Changes
- When Rust detector is unavailable, legacy Python detector now emits a one-time deprecation warning instead of silently taking over
- Expanded test coverage around plugin configuration behavior including masking modes, whitelist handling, detection metadata, and Python-fallback signaling

### Rust Detector Changes
- Fixed core masking bug where built-in detections were ignoring the configured `default_mask_strategy`
- Built-in SSN/email/AWS detections now honor the configured default strategy
- Custom patterns still keep their explicit mask-strategy overrides

## 📝 Notes
- Local compose verification reproduced the original Rust masking issue before the fix: with `default_mask_strategy=redact`, built-in detections still returned `partial`
- After the fix, built-in detections honor the configured default strategy and custom patterns still preserve explicit overrides
- A separate local database-state issue surfaced during compose verification: an old Postgres volume was stamped to an Alembic revision no longer present in the branch. Resetting the local dev DB volume resolved that environment-specific problem.
