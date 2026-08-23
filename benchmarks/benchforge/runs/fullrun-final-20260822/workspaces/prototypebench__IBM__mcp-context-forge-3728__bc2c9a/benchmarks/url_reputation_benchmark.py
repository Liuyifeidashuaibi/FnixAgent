import time
import random
import string
from typing import List

# Try to import both implementations
try:
    import url_reputation_rust
    HAS_RUST = True
except ImportError:
    HAS_RUST = False

from plugins.url_reputation.url_reputation import url_reputation_plugin


def generate_test_urls(count: int = 1000) -> List[str]:
    """Generate test URLs for benchmarking."""
    urls = []
    
    # Generate various URL patterns
    domains = [
        "google.com", "github.com", "stackoverflow.com", "python.org",
        "malicious-phish-site.com", "scam-portal.net", "fraud-bank.org",
        "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6.q7r8s9t0u1v2w3x4y5z6.com",
        "gооgle.com", # Cyrillic homoglyph
        "example.invalidtld",
    ]
    
    protocols = ["http://", "https://"]
    
    for _ in range(count):
        protocol = random.choice(protocols)
        domain = random.choice(domains)
        path_length = random.randint(0, 5)
        path = "".join(random.choices(string.ascii_letters + string.digits + "/-", k=path_length))
        if path and not path.startswith("/"):
            path = "/" + path
        
        url = f"{protocol}{domain}{path}"
        urls.append(url)
    
    return urls


def benchmark_implementation(name: str, func, urls: List[str], iterations: int = 100):
    """Benchmark a URL validation implementation."""
    times = []
    
    for _ in range(iterations):
        start = time.perf_counter()
        for url in urls:
            try:
                result = func(url)
            except Exception as e:
                # Log error but continue
                pass
        end = time.perf_counter()
        times.append(end - start)
    
    avg_time = sum(times) / len(times)
    avg_per_url = avg_time / len(urls) * 1000000  # microseconds
    
    print(f"{name}: {avg_per_url:.2f} μs per URL (avg over {iterations} runs)")
    return avg_per_url


def main():
    print("URL Reputation Plugin Benchmark")
    print("=" * 40)
    
    # Generate test URLs
    test_urls = generate_test_urls(100)
    print(f"Generated {len(test_urls)} test URLs")
    
    # Benchmark Python implementation
    python_time = benchmark_implementation(
        "Python Implementation", 
        lambda url: url_reputation_plugin.validate_url(url), 
        test_urls
    )
    
    # Benchmark Rust implementation if available
    if HAS_RUST:
        rust_time = benchmark_implementation(
            "Rust Implementation", 
            url_reputation_rust.validate_url_py, 
            test_urls
        )
        
        # Calculate speedup
        if rust_time > 0:
            speedup = python_time / rust_time
            print(f"Speedup: {speedup:.2f}x")
    
    print("\nBenchmark complete!")

if __name__ == "__main__":
    main()
