from django.http.response import HttpResponse

# The fix for Django issue #11133:
# HttpResponse should handle memoryview objects by converting them to bytes.
#
# In the actual Django source, the content setter would be modified like this:
#
# @content.setter
# def content(self, value):
#     # Handle memoryview objects
#     if isinstance(value, memoryview):
#         value = bytes(value)
#     # Continue with existing logic...
#     if hasattr(value, '__iter__') and not isinstance(value, (bytes, str)):
#         self._container = list(value)
#     else:
#         self._container = [value]
#     self._charset = None
