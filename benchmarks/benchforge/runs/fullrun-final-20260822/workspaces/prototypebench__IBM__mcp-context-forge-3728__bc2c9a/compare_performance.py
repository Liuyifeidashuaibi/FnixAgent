#!/usr/bin/env python3
"""
Performance comparison script for URL reputation implementations.
"""

import time
import sys
from typing import Dict, Any

# Try to import both implementations
try:
    import url_reputation_rust
    HAS_RUST = True
except ImportError:
    HAS_RUST = False
    print("Warning: Rust extension not available")

from plugins.url_reputation.url_reputation import url_reputation_plugin


def time_function(func, *args, **kwargs) -> float:
    """Time a function call and return execution time in microseconds."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    end = time.perf_counter()
    return (end - start) * 1000000, result  # Convert to microseconds


def run_comparison():
    """Run performance comparison between Python and Rust implementations."""
    
    # Test URLs
    test_urls = [
        "https://google.com",
        "https://malicious-phish-site.com/login",
        "https://a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6.q7r8s9t0u1v2w3x4y5z6.com",
        "https://gооgle.com",  # Cyrillic homoglyph
        "https://example.invalidtld",
        "https://github.com/IBM/mcp-context-forge",
        "http://scam-portal.net/verify-account",
        "https://python.org/docs/3.11/",
    ]
    
    print("URL Reputation Performance Comparison")
    print("=" * 50)
    print(f"Testing with {len(test_urls)} URLs")
    print()
    
    # Test Python implementation
    print("Python Implementation:")
    python_times = []
    for url in test_urls:
        elapsed, _ = time_function(url_reputation_plugin.validate_url, url)
        python_times.append(elapsed)
        print(f"  {url[:40]}...: {elapsed:.2f} μs")
    
    python_avg = sum(python_times) / len(python_times)
    print(f"  Average: {python_avg:.2f} μs")
    print()
    
    # Test Rust implementation if available
    if HAS_RUST:
        print("Rust Implementation:")
        rust_times = []
        for url in test_urls:
            try:
                elapsed, _ = time_function(url_reputation_rust.validate_url_py, url)
                rust_times.append(elapsed)
                print(f"  {url[:40]}...: {elapsed:.2f} μs")
            except Exception as e:
                print(f"  {url[:40]}...: ERROR - {e}")
        
        if rust_times:
            rust_avg = sum(rust_times) / len(rust_times)
            print(f"  Average: {rust_avg:.2f} μs")
            
            # Calculate speedup
            if rust_avg > 0:
                speedup = python_avg / rust_avg
                print(f"  Speedup: {speedup:.2f}x")
                
                # Check if it meets the <7 microseconds requirement
                if rust_avg < 7.0:
                    print(f"  ✓ Meets <7μs requirement ({rust_avg:.2f}μs)")
                else:
                    print(f"  ✗ Does not meet <7μs requirement ({rust_avg:.2f}μs)")
        print()
    
    # Summary
    print("Summary:")
    print(f"- Python average: {python_avg:.2f} μs")
    if HAS_RUST and rust_times:
        print(f"- Rust average: {rust_avg:.2f} μs")
        print(f"- Speedup: {speedup:.2f}x")
    
    return python_avg, rust_avg if HAS_RUST and rust_times else None


def main():
    """Main entry point."""
    try:
        python_avg, rust_avg = run_comparison()
        
        # Exit code based on performance
        if rust_avg and rust_avg < 7.0:
            print("\n✅ Rust implementation meets the <7 microseconds requirement!")
            sys.exit(0)
        else:
            print("\n❌ Rust implementation does not meet the <7 microseconds requirement.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nError during benchmark: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
