# Configuration file for REST tool settings

# Configurable setting for response truncation
# Default: 5000 chars, range: 1000-100000
REST_RESPONSE_TEXT_MAX_LENGTH = 5000

# Other potential configuration options
REST_DEFAULT_TIMEOUT = 30
REST_MAX_RETRIES = 3
REST_RETRY_BACKOFF_FACTOR = 1

# Security settings
REST_ALLOW_UNSAFE_REDIRECTS = False
REST_VERIFY_SSL = True

# Logging settings
REST_LOG_LEVEL = 'INFO'
REST_LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
