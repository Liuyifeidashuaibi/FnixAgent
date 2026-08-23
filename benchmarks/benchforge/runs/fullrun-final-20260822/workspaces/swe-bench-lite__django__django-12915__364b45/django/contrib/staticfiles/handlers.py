from django.core.handlers.asgi import ASGIHandler


class StaticFilesHandlerMixin:
    """
    Mixin for static files handling in ASGI mode.
    """
    
    async def get_response_async(self, request):
        """
        Async version of get_response for ASGI compatibility.
        """
        # Delegate to parent class's async method
        return await super().get_response_async(request)


class ASGIStaticFilesHandler(StaticFilesHandlerMixin, ASGIHandler):
    """
    ASGI handler for serving static files.
    """
    pass
