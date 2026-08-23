import re

# Patch to fix option:: directive validation for Sphinx 3.2+
# Relax the validation to accept any non-empty string instead of restrictive patterns
# Original validation was too strict and broke backward compatibility

def validate_option_syntax(option_text):
    """
    Validate option syntax - relaxed version that accepts any non-empty string
    """
    if not option_text or not option_text.strip():
        return False
    return True

# The original strict validation would be replaced with this permissive one
# This allows patterns like [enable=]PATTERN that were valid in earlier Sphinx versions
