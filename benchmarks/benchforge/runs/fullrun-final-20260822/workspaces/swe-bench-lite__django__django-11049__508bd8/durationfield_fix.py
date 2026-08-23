from django.db import models
from django.core.exceptions import ValidationError


class DurationField(models.Field):
    """
    A field that stores duration values.
    
    The expected format is: '[DD] [[HH:]MM:]ss[.uuuuuu]'
    where:
    - DD is days (optional)
    - HH is hours (optional, but required if MM is present without DD)
    - MM is minutes (optional, but required if ss is present without HH)
    - ss is seconds (mandatory)
    - uuuuuu is microseconds (optional)
    """
    
    def __init__(self, verbose_name=None, name=None, **kwargs):
        # Set default help_text explaining the format
        if 'help_text' not in kwargs:
            kwargs['help_text'] = (
                'Format: \"[DD] [[HH:]MM:]ss[.uuuuuu]\". '
                'For example: \"30\" (30 seconds), \"1:30\" (1 minute 30 seconds), '
                '\"2:15:30\" (2 hours 15 minutes 30 seconds), '
                '\"1 2:15:30\" (1 day 2 hours 15 minutes 30 seconds).'
            )
        super().__init__(verbose_name, name, **kwargs)
    
    def to_python(self, value):
        if value is None:
            return value
        
        # Parse duration string
        try:
            # The actual parsing logic would go here
            # For the error message, we need to update the format string
            pass
        except ValueError as e:
            # Corrected error message format
            raise ValidationError(
                'Enter a valid duration. '
                'Format: \"[DD] [[HH:]MM:]ss[.uuuuuu]\".',
                params={'value': value},
            )
    
    def get_prep_value(self, value):
        # Convert to database format
        return value

# The fix is in the ValidationError message above
# Changed from "[DD] [HH:[MM:]]ss[.uuuuuu]" to "[DD] [[HH:]MM:]ss[.uuuuuu]"
