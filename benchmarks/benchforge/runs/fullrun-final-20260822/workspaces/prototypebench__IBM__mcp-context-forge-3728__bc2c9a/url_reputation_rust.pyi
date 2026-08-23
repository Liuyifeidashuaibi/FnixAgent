from typing import Dict, List, Any

def validate_url_py(url: str) -> Dict[str, Any]:
    """
    Validate URL reputation using Rust engine.
    
    Args:
        url: The URL to validate
    
    Returns:
        Dictionary with keys:
        - 'is_malicious': bool indicating if URL is malicious
        - 'confidence': float confidence score (0.0-1.0)
        - 'reasons': list of strings explaining the decision
    """
    ...
