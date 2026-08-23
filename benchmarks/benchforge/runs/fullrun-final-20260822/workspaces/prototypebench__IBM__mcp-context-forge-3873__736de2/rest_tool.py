import json
import orjson
import logging
from typing import Dict, Any, Optional, Union

# Configure logging
logger = logging.getLogger(__name__)

# Configurable setting for response truncation
REST_RESPONSE_TEXT_MAX_LENGTH = 5000  # default: 5000 chars, range: 1000-100000


def _handle_json_parse_error(response_content: bytes, encoding: str = 'utf-8') -> Dict[str, Any]:
    """
    Helper function for graceful fallback when JSON parsing fails.
    Handles multiple exception types: json.JSONDecodeError, orjson.JSONDecodeError, 
    UnicodeDecodeError, AttributeError
    """
    try:
        # Try standard json first
        return json.loads(response_content.decode(encoding))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        pass
    
    try:
        # Try orjson if available
        return orjson.loads(response_content)
    except (orjson.JSONDecodeError, AttributeError) as e:
        pass
    
    # Fallback: return raw text with truncation
    try:
        text_content = response_content.decode(encoding)
        original_length = len(text_content)
        
        # Apply truncation
        if original_length > REST_RESPONSE_TEXT_MAX_LENGTH:
            truncated_content = text_content[:REST_RESPONSE_TEXT_MAX_LENGTH]
            logger.warning(
                f"Response text truncated: {original_length} -> {len(truncated_content)} chars. "
                f"Original content: {text_content[:200]}..."
            )
            text_content = truncated_content
        
        return {"response_text": text_content}
    except UnicodeDecodeError:
        # Handle binary content
        logger.warning("Unable to decode response content, returning hex representation")
        return {"response_text": response_content[:REST_RESPONSE_TEXT_MAX_LENGTH].hex()}


def validate_jq_filter(jq_filter: str) -> bool:
    """
    Validates jq filter to detect simple email addresses mistakenly used as jq filters.
    Uses regex pattern ^[^.\[\]|]+@[^.\[\]|]+\.[^.\[\]|]+$ to catch basic email patterns
    """
    import re
    
    # Email pattern: basic email validation without false positives
    email_pattern = r'^[^.\[\]|]+@[^.\[\]|]+\.[^.\[\]|]+$'
    
    if re.match(email_pattern, jq_filter):
        logger.warning(f"Invalid jq filter detected (appears to be an email address): {jq_filter}")
        return False
    
    return True


def process_query_params(method: str, url: str, input_params: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """
    Process query parameters based on HTTP method:
    - GET requests: URL query params merged with input arguments (URL params take precedence)
    - POST/PUT/PATCH/DELETE: Query params preserved in URL to support signed URLs
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    
    parsed_url = urlparse(url)
    url_params = parse_qs(parsed_url.query)
    
    # Convert list values to single values (take first)
    url_params = {k: v[0] if isinstance(v, list) and v else v for k, v in url_params.items()}
    
    if method.upper() == 'GET':
        # Merge URL params with input params, URL params take precedence
        merged_params = {**input_params, **url_params}
        
        # Check for conflicts and log warnings
        conflicts = set(input_params.keys()) & set(url_params.keys())
        if conflicts:
            logger.warning(f"Query parameter conflicts detected for GET request: {conflicts}. "
                         f"URL parameters take precedence.")
        
        # Build new URL with merged params
        new_query = urlencode(merged_params)
        new_parsed = parsed_url._replace(query=new_query)
        new_url = urlunparse(new_parsed)
        
        return new_url, merged_params
    else:
        # For POST/PUT/PATCH/DELETE: preserve URL query params as-is
        # Return original url and input_params unchanged
        return url, input_params


def make_rest_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    data: Optional[Union[str, bytes, Dict]] = None,
    params: Optional[Dict[str, Any]] = None,
    jq_filter: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Enhanced REST request function with improved error handling and validation.
    """
    import requests
    
    # Validate jq filter
    if jq_filter and not validate_jq_filter(jq_filter):
        jq_filter = None  # Treat invalid filters as empty
    
    # Process query parameters based on method
    if params:
        url, params = process_query_params(method, url, params)
    
    try:
        # Make the HTTP request
        response = requests.request(
            method=method,
            url=url,
            headers=headers or {},
            data=data,
            params=params,
            timeout=timeout
        )
        
        # Handle response
        if response.status_code >= 400:
            # Handle error responses
            try:
                # Try to parse as JSON first
                error_data = response.json()
                return {
                    "status_code": response.status_code,
                    "error": "HTTP error",
                    "response": error_data
                }
            except (json.JSONDecodeError, ValueError):
                # Fall back to text handling
                error_data = _handle_json_parse_error(response.content)
                return {
                    "status_code": response.status_code,
                    "error": "HTTP error",
                    "response": error_data
                }
        
        # Handle success responses
        if 'application/json' in response.headers.get('content-type', ''):
            try:
                json_data = response.json()
                if jq_filter and jq_filter.strip():
                    # Apply jq filter if available (simplified for this example)
                    # In real implementation, would use jq library
                    pass
                return {
                    "status_code": response.status_code,
                    "response": json_data
                }
            except (json.JSONDecodeError, ValueError):
                # Fall back to text handling for non-JSON responses
                text_data = _handle_json_parse_error(response.content)
                return {
                    "status_code": response.status_code,
                    "response": text_data
                }
        else:
            # Non-JSON response
            text_data = _handle_json_parse_error(response.content)
            return {
                "status_code": response.status_code,
                "response": text_data
            }
            
    except requests.exceptions.RequestException as e:
        return {
            "error": "Request failed",
            "exception": str(e)
        }
    except Exception as e:
        logger.error(f"Unexpected error in REST request: {e}")
        return {
            "error": "Unexpected error",
            "exception": str(e)
        }
