class GatewayService:
    def register_gateway(self, gateway, resources):
        # Line 961: Original register_gateway logic
        for r in resources:
            # Original logic: getattr(r, "visibility", None) or visibility
            visibility = getattr(r, "visibility", None) or gateway.visibility
            # ... rest of registration logic

    def _update_or_create_resources(self, gateway, resources, update_visibility=True):
        # Line 4227: Update path - fixed to respect per-resource visibility
        for resource in resources:
            # Fixed: use getattr(resource, "visibility", None) or gateway.visibility
            # to match register_gateway() behavior
            visibility = getattr(resource, "visibility", None) or gateway.visibility
            
            # ... update logic using visibility
            
        # Line 4240: Create path - fixed to respect per-resource visibility
        for resource in resources:
            # Fixed: use getattr(resource, "visibility", None) or gateway.visibility
            # to match register_gateway() behavior
            visibility = getattr(resource, "visibility", None) or gateway.visibility
            
            # ... create logic using visibility