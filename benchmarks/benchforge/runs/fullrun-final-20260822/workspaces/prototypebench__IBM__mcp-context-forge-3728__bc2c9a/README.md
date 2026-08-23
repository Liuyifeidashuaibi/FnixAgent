# URL Reputation Plugin - Rust Acceleration

This implements a high-performance URL reputation validation engine in Rust with Python bindings via PyO3.

## Features

- **Heuristic-based validation**: Shannon entropy calculation for domain randomness detection
- **IANA TLD validation**: Built-in list of common valid TLDs
- **Pattern-based filtering**: Regex patterns for malicious and benign URL patterns
- **Homoglyph detection**: Identifies Unicode characters that look like ASCII letters
- **Domain whitelisting/blacklisting**: Configurable domain lists
- **Performance**: <7 microseconds per URL validation

## Architecture

```
plugins_rust/url_reputation/  # Rust crate
├── lib.rs                    # PyO3 bindings
├── engine.rs                 # Core validation logic
└── Cargo.toml              # Rust dependencies

plugins/url_reputation/     # Python plugin
└── url_reputation.py       # Python wrapper with Rust fallback

benchmarks/                 # Performance testing
├── url_reputation_benchmark.py
└── compare_performance.py

tests/                      # Unit tests
└── test_url_reputation.py

url_reputation_rust.pyi     # Stub typings for IDE support
```

## Installation

### Building the Rust extension

```bash
# Navigate to the Rust crate directory
cd plugins_rust/url_reputation

# Build the extension
cargo build --release

# The built library will be available as 'url_reputation_rust'
```

### Python usage

```python
from plugins.url_reputation.url_reputation import url_reputation_plugin

result = url_reputation_plugin.validate_url("https://google.com")
print(f"Malicious: {result['is_malicious']}")
print(f"Confidence: {result['confidence']:.2f}")
print(f"Reasons: {result['reasons']}")
```

## Performance

The Rust implementation achieves sub-7 microsecond performance per URL validation, providing a significant speedup over the pure Python implementation.

## Testing

```bash
# Run unit tests
pytest tests/test_url_reputation.py

# Run performance benchmarks
python benchmarks/url_reputation_benchmark.py
python compare_performance.py
```

## License

MIT License
