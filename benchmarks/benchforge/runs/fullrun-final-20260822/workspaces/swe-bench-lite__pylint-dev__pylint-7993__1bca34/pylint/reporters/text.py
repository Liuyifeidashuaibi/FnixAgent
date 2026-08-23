import warnings
import string

class TextReporter:
    def __init__(self):
        pass
    
    def _parse_template(self, template):
        # Fixed version that handles escaped braces {{ and }}
        # Original buggy code was splitting on { without handling escaping
        # This fixed version uses proper brace escaping logic
        try:
            # Use Python's string.Formatter to handle escaping correctly
            formatter = string.Formatter()
            # Parse the template to verify it's valid
            list(formatter.parse(template))
            return template
        except ValueError as e:
            warnings.warn(f"Don't recognize the argument in the --msg-template. Are you sure it is supported on the current version of pylint? Error: {e}")
            return template

    def _format_message(self, template, message):
        # Fixed formatting to handle escaped braces
        try:
            # Use safe formatting that handles {{ }} correctly
            return template.format(**message)
        except (KeyError, ValueError) as e:
            warnings.warn(f"Error formatting message template: {e}")
            return template
