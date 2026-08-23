from django.utils.translation import gettext as _


class ValidationError(Exception):
    """An error while validating data."""
    def __init__(self, message, code=None, params=None):
        """
        ValidationError can be passed any object that can be printed (usually
        a string), or a dictionary or list of such objects.
        """
        if isinstance(message, dict):
            self.error_dict = message
        elif isinstance(message, list):
            self.error_list = message
        else:
            self.message = message
            self.code = code
            self.params = params
            self.error_list = [self]

    def __str__(self):
        if hasattr(self, 'error_dict'):
            return repr(self.error_dict)
        elif hasattr(self, 'error_list'):
            return repr(self.error_list)
        else:
            return str(self.message)

    def __repr__(self):
        return 'ValidationError(%s)' % self

    def __eq__(self, other):
        if not isinstance(other, ValidationError):
            return False
        
        # Compare error_list if both have it
        if hasattr(self, 'error_list') and hasattr(other, 'error_list'):
            # Sort both error lists for order independence
            self_errors = sorted(str(e) for e in self.error_list)
            other_errors = sorted(str(e) for e in other.error_list)
            return self_errors == other_errors
        
        # Compare error_dict if both have it
        if hasattr(self, 'error_dict') and hasattr(other, 'error_dict'):
            if set(self.error_dict.keys()) != set(other.error_dict.keys()):
                return False
            for key in self.error_dict:
                self_key_errors = sorted(str(e) for e in self.error_dict[key])
                other_key_errors = sorted(str(e) for e in other.error_dict[key])
                if self_key_errors != other_key_errors:
                    return False
            return True
        
        # Compare single message
        if hasattr(self, 'message') and hasattr(other, 'message'):
            return str(self.message) == str(other.message) and \
                   getattr(self, 'code', None) == getattr(other, 'code', None) and \
                   getattr(self, 'params', None) == getattr(other, 'params', None)
        
        return False
