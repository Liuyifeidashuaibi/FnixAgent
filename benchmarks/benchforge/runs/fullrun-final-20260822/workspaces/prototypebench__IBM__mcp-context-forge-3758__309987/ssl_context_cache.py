import hashlib
import ssl
import time
from typing import Dict, Optional, Tuple, Any

# Global cache storage
_ssl_context_cache: Dict[str, Tuple[ssl.SSLContext, float]] = {}
_ssl_context_cache_max_size: int = 100
_ssl_context_cache_ttl: Optional[float] = None


def _get_cache_key(
    ca_certificate: str,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
) -> str:
    """Generate collision-safe cache key with labeled prefixes."""
    key_hash = hashlib.sha256()
    
    # Convert to bytes for hashing
    ca_cert_bytes = ca_certificate.encode() if isinstance(ca_certificate, str) else ca_certificate
    
    key_hash.update(b"ca_cert:")
    key_hash.update(ca_cert_bytes)
    
    client_cert_value = client_cert or ""
    client_key_value = client_key or ""
    
    key_hash.update(b"|client_cert:")
    key_hash.update(client_cert_value.encode())
    
    key_hash.update(b"|client_key:")
    key_hash.update(client_key_value.encode())
    
    return key_hash.hexdigest()


def _is_expired(timestamp: float) -> bool:
    """Check if cache entry has expired based on TTL."""
    if _ssl_context_cache_ttl is None:
        return False
    return time.time() - timestamp > _ssl_context_cache_ttl


def get_cached_ssl_context(
    ca_certificate: str,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
) -> ssl.SSLContext:
    """
    Get cached SSL context with mTLS support.
    
    Args:
        ca_certificate: CA certificate string
        client_cert: Client certificate string for mTLS (optional)
        client_key: Client key string for mTLS (optional)
        
    Returns:
        SSLContext object
    """
    cache_key = _get_cache_key(ca_certificate, client_cert, client_key)
    
    # Check cache
    if cache_key in _ssl_context_cache:
        ctx, timestamp = _ssl_context_cache[cache_key]
        if not _is_expired(timestamp):
            return ctx
        else:
            # Remove expired entry
            del _ssl_context_cache[cache_key]
    
    # Create new SSL context
    ctx = ssl.create_default_context()
    
    # Load CA certificate
    if ca_certificate:
        ctx.load_verify_locations(cadata=ca_certificate)
    
    # Load client certificate chain for mTLS
    if client_cert and client_key:
        try:
            ctx.load_cert_chain(certfile=client_cert, keyfile=client_key)
        except Exception as e:
            raise ValueError(f"Failed to load client certificate chain: {e}")
    
    # Store in cache
    _ssl_context_cache[cache_key] = (ctx, time.time())
    
    # Enforce max size limit
    if len(_ssl_context_cache) > _ssl_context_cache_max_size:
        # Remove oldest entries
        sorted_items = sorted(_ssl_context_cache.items(), key=lambda x: x[1][1])
        for key, _ in sorted_items[:-_ssl_context_cache_max_size]:
            del _ssl_context_cache[key]
    
    return ctx


def clear_ssl_context_cache() -> None:
    """Clear the entire SSL context cache."""
    _ssl_context_cache.clear()


def set_cache_config(max_size: int = 100, ttl: Optional[float] = None) -> None:
    """Configure cache settings."""
    global _ssl_context_cache_max_size, _ssl_context_cache_ttl
    _ssl_context_cache_max_size = max_size
    _ssl_context_cache_ttl = ttl


def get_cache_size() -> int:
    """Get current cache size."""
    return len(_ssl_context_cache)
