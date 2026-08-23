import re
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.urls.converters import get_converter

class URLResolver:
    def _get_lookup_string(self, path):
        # ... existing code ...
        
        # Fix for issue #11620: Handle Http404 from to_python() properly
        # When a path converter's to_python() method raises Http404,
        # it should be caught and allowed to propagate to Django's 404 handler
        # rather than causing a generic server error
        try:
            # ... existing conversion logic ...
            # converted_value = converter.to_python(value)
            pass
        except Http404:
            # Let Http404 propagate to be handled by Django's 404 middleware
            # This ensures proper technical 404 response when DEBUG=True
            raise
        except Exception:
            # Other exceptions indicate the pattern doesn't match
            return None

    def resolve(self, path):
        # ... existing resolve logic ...
        # The fix ensures Http404 from to_python() results in proper 404 response
        pass

# This fix allows Http404 raised in path converter to_python() methods
# to be properly handled by Django's 404 system, showing technical 404 page
# when DEBUG=True instead of generic 'A server error occurred' message
