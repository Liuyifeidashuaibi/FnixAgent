from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class ASCIIUsernameValidator:
    """
    Validate that the username contains only ASCII characters.
    """
    # ASCII usernames can contain ASCII letters, digits, and the following chars.
    # This regex is intentionally similar to the Unicode version below.
    regex = r'\A[\w.@+-]+\Z'
    message = _(
        'Enter a valid username. This value may contain only English letters, '
        'numbers, and @/./+/-/_ characters.'
    )
    flags = 0

    def __call__(self, value):
        if not self.regex.match(value):
            raise ValidationError(self.message, params={'value': value})


@deconstructible
class UnicodeUsernameValidator:
    """
    Validate that the username contains only Unicode letters, digits,
    and the following chars.
    """
    # Unicode usernames can contain alphanumeric characters, and the following
    # chars.
    regex = r'\A[\w.@+-]+\Z'
    message = _(
        'Enter a valid username. This value may contain only letters, '
        'numbers, and @/./+/-/_ characters.'
    )
    flags = 0

    def __call__(self, value):
        if not self.regex.match(value):
            raise ValidationError(self.message, params={'value': value})