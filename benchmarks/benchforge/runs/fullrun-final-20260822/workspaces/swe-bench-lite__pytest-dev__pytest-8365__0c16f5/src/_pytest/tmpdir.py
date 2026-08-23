import getpass
import re
import os
from pathlib import Path

# Sanitize username for filesystem compatibility
# Replace illegal characters with underscore
ILLEGAL_CHARS = r'[\\/:*?"<>|]'

def _sanitize_username(username):
    """Sanitize username to be safe for filesystem use."""
    return re.sub(ILLEGAL_CHARS, '_', username)

# Original get_user function with sanitization
def get_user():
    try:
        user = getpass.getuser()
        return _sanitize_username(user)
    except Exception:
        # Fallback if getpass fails
        return 'unknown'

# Function to get sanitized username for basetemp construction
def get_sanitized_username():
    """Get username sanitized for use in filesystem paths."""
    return _sanitize_username(getpass.getuser())

# The rest of the tmpdir module would follow...
