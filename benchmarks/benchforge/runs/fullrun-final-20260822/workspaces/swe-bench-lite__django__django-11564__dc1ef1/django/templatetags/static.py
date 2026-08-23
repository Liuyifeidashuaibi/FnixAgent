from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.safestring import mark_safe

register = template.Library()

class StaticNode(template.Node):
    def __init__(self, varname=None, path=None):
        self.varname = varname
        self.path = path

    def url(self, context):
        path = self.path.resolve(context)
        
        # Get the static URL using the storage backend
        url = staticfiles_storage.url(path)
        
        # Add SCRIPT_NAME support - check for request in context
        request = context.get('request')
        if request and hasattr(request, 'META'):
            script_name = request.META.get('SCRIPT_NAME', '')
            if script_name and script_name != '/':
                # Prepend SCRIPT_NAME to the URL if not already present
                if not url.startswith(script_name):
                    if url.startswith('/'):
                        url = script_name + url
                    else:
                        url = script_name + '/' + url
        
        return url

    def render(self, context):
        url = self.url(context)
        if self.varname is None:
            return url
        context[self.varname] = url
        return ''

@register.tag
def static(parser, token):
    """
    A template tag that returns the URL to a file specified by the 'path' argument.
    It supports SCRIPT_NAME for sub-path deployments by automatically prepending
    the SCRIPT_NAME WSGI parameter when available in the request context.
    """
    bits = token.split_contents()
    if len(bits) < 2:
        raise template.TemplateSyntaxError(
            "%s takes at least one argument: the path to the file" % bits[0]
        )
    path = parser.compile_filter(bits[1])
    varname = None
    if len(bits) >= 4 and bits[2] == 'as':
        varname = bits[3]
    return StaticNode(varname, path)
