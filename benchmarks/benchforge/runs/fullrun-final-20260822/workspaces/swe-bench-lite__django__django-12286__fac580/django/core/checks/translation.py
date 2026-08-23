from django.conf import settings
from django.core.checks import Error, register


@register()
def check_language_code(app_configs, **kwargs):
    errors = []
    
    # Get the LANGUAGE_CODE setting
    language_code = getattr(settings, 'LANGUAGE_CODE', None)
    if not language_code:
        return errors
    
    # Get the LANGUAGES setting
    languages = getattr(settings, 'LANGUAGES', [])
    
    # Extract language codes from LANGUAGES (which is a list of tuples)
    language_codes = [code for code, name in languages] if languages else []
    
    # Check if LANGUAGE_CODE is directly in LANGUAGES
    if language_code in language_codes:
        return errors
    
    # Check if base language (without sublanguage part) is in LANGUAGES
    # For example, "de-at" -> "de", "es-ar" -> "es"
    if '-' in language_code:
        base_language = language_code.split('-')[0]
        if base_language in language_codes:
            return errors
    
    # If neither the full code nor base language is found, raise E004
    errors.append(
        Error(
            "You have provided a value for the LANGUAGE_CODE setting that is not in the LANGUAGES setting.",
            id='translation.E004',
        )
    )
    
    return errors
