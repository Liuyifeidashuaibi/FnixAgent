import ssl
from typing import Optional, Dict, Any

# Import the SSL context cache
from ssl_context_cache import get_cached_ssl_context, clear_ssl_context_cache


def resolve_mtls_certificates(
    gateway_payload: Optional[Dict[str, Any]] = None,
    gateway: Optional[Any] = None,
    has_gateway: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve client certificate and key from payload or runtime gateway.
    
    Returns:
        Tuple of (client_cert, client_key)
    """
    client_cert_from_payload = None
    client_key_from_payload = None
    
    if gateway_payload and has_gateway:
        client_cert_from_payload = gateway_payload.get("client_cert")
        client_key_from_payload = gateway_payload.get("client_key")
    
    gateway_client_cert = client_cert_from_payload
    gateway_client_key = client_key_from_payload
    
    if has_gateway and gateway is not None:
        runtime_gateway_client_cert = getattr(gateway, "client_cert", None)
        runtime_gateway_client_key = getattr(gateway, "client_key", None)
        if runtime_gateway_client_cert:
            gateway_client_cert = runtime_gateway_client_cert
        if runtime_gateway_client_key:
            gateway_client_key = runtime_gateway_client_key
    
    return gateway_client_cert, gateway_client_key


def get_ssl_context_for_gateway(
    gateway_url: Optional[str] = None,
    gateway_ca_cert: Optional[str] = None,
    gateway_payload: Optional[Dict[str, Any]] = None,
    gateway: Optional[Any] = None,
    has_gateway: bool = False,
) -> Optional[ssl.SSLContext]:
    """
    Get SSL context for gateway with HTTP bypass and mTLS support.
    
    Returns:
        SSLContext object or None for HTTP URLs
    """
    # Skip SSL entirely for http:// URLs
    if gateway_url and gateway_url.lower().startswith("http://"):
        return None  # Use default httpx verification
    
    # Resolve mTLS certificates
    client_cert_value, client_key_value = resolve_mtls_certificates(
        gateway_payload, gateway, has_gateway
    )
    
    # Create SSL context only for HTTPS with valid CA cert
    if gateway_url and gateway_url.lower().startswith("https://") and gateway_ca_cert:
        try:
            ctx = get_cached_ssl_context(
                ca_certificate=gateway_ca_cert,
                client_cert=client_cert_value,
                client_key=client_key_value,
            )
            return ctx
        except Exception as e:
            # Log error but continue with default verification
            pass
    
    return None


def create_ssl_context(
    ca_certificate: str,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
) -> ssl.SSLContext:
    """Create SSL context with mTLS support."""
    return get_cached_ssl_context(ca_certificate, client_cert, client_key)
