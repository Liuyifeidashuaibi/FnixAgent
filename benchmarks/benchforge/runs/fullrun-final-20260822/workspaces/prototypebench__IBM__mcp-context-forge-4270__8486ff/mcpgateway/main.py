class MCPPathRewriteMiddleware:
    def __init__(self, app, root_path=""):
        self.app = app
        self.root_path = root_path

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Store original path
            original_path = scope.get("path", "")
            scope["modified_path"] = original_path
            
            # Compute app-relative path by stripping root_path prefix
            if self.root_path and original_path.startswith(self.root_path):
                app_path = original_path[len(self.root_path):]
                if not app_path.startswith("/"):
                    app_path = "/" + app_path
                # Fix: Update modified_path to use app_path (line 3028-3030)
                scope["modified_path"] = app_path
            
        await self.app(scope, receive, send)
