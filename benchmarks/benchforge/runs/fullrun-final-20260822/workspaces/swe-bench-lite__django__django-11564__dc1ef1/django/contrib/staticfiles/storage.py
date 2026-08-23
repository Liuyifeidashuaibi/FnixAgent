import os
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.core.files.storage import FileSystemStorage
from django.conf import settings


class ScriptNameStaticFilesStorage(StaticFilesStorage):
    """
    StaticFilesStorage that supports SCRIPT_NAME for sub-path deployments.
    """
    def url(self, name, parameters=None):
        url = super().url(name, parameters)
        
        # Check for SCRIPT_NAME in context if available
        # This is a simplified version - in real Django, this would be handled
        # through the request context in template tags
        if hasattr(self, '_request') and self._request:
            script_name = getattr(self._request.META, 'SCRIPT_NAME', '')
            if script_name and not url.startswith(script_name):
                if url.startswith('/'):
                    url = script_name + url
                else:
                    url = script_name + '/' + url
        
        return url


class ScriptNameFileSystemStorage(FileSystemStorage):
    """
    FileSystemStorage that supports SCRIPT_NAME for sub-path deployments.
    """
    def url(self, name):
        url = super().url(name)
        
        # Check for SCRIPT_NAME in context if available
        if hasattr(self, '_request') and self._request:
            script_name = getattr(self._request.META, 'SCRIPT_NAME', '')
            if script_name and not url.startswith(script_name):
                if url.startswith('/'):
                    url = script_name + url
                else:
                    url = script_name + '/' + url
        
        return url
