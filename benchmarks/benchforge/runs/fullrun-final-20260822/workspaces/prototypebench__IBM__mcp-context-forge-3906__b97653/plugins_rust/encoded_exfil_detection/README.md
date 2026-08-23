# Rust Implementation of Encoded Exfiltration Detection Plugin

## Overview

This is the Rust implementation of the encoded exfiltration detection plugin, providing 4.3x-12.1x performance improvement over the Python implementation.

## Features

- **All Python features implemented**: Allowlisting, per-encoding thresholds, nested encoding detection, JSON-within-strings parsing, recursion depth limiting, detection logging
- **Persistent engine**: Config parsed once at `__new__()` instead of per-call
- **Regex validation**: Matches Python behavior - rejects invalid regex patterns with `PyValueError`
- **Memory safety**: Uses Rust's ownership model for zero-copy string processing
- **JSON parsing**: Uses `serde_json` for efficient JSON parsing and recursive scanning

## Building

```bash
# Build in release mode
cargo build --release

# Install as Python package
maturin develop
```

## Testing

```bash
# Run Rust unit tests
cargo test

# Run Python-Rust parity tests
python plugins_rust/encoded_exfil_detection/compare_performance.py
```

## Performance

The Rust implementation provides significant speedup:
- Small payloads: 4.3x-4.7x faster
- Large payloads (~50KB): 12.1x faster
- Clean payloads: 4.3x faster (after persistent engine refactor)

## License

Apache-2.0
