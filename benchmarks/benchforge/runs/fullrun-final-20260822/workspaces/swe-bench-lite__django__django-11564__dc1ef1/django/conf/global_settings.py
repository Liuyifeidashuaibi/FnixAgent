# Django global settings with SCRIPT_NAME support

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/stable/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = None

# Media files (user-uploaded files)
# https://docs.djangoproject.com/en/stable/topics/files/

MEDIA_URL = '/media/'
MEDIA_ROOT = None

# Storage backends
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# SCRIPT_NAME support configuration
# When running under WSGI with SCRIPT_NAME, these settings will be automatically
# enhanced by the template tags and storage classes
SCRIPT_NAME_SUPPORT = True
