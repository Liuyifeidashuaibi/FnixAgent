from django.utils.functional import allow_lazy
from django.utils.safestring import mark_safe


def slugify(value, allow_unicode=False):
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces to hyphens.
    Remove characters that aren't alphanumerics, underscores, or hyphens.
    Convert to lowercase. Also strip leading and trailing whitespace and
    dashes and underscores.
    """
    import re
    
    if allow_unicode:
        value = re.sub(r'[^一-鿿\w\s-]', '', value)
        value = re.sub(r'[-\s]+', '-', value).strip('-_')
    else:
        from django.utils.encoding import force_str
        value = force_str(value)
        import unicodedata
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        value = re.sub(r'[^\w\s-]', '', value)
        value = re.sub(r'[-\s]+', '-', value).strip('-_')
    
    return value.strip('-_')

slugify = allow_lazy(slugify, str)
