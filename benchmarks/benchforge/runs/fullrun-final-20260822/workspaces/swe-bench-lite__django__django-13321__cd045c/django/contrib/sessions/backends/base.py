import base64
import binascii
import json
from django.core import signing
from django.utils import timezone


class SessionBase:
    """
    Base class for all Session classes.
    """
    def _legacy_decode(self, session_data):
        try:
            # Python 2 ascii encoding raises ValueError on decode failure.
            # Python 3 ascii encoding raises UnicodeDecodeError.
            try:
                encoded_data = base64.b64decode(session_data.encode('ascii'))
            except binascii.Error:
                return {}
        except (ValueError, UnicodeDecodeError):
            return {}
        try:
            return json.loads(encoded_data.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return {}
