from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class GatewayService:
    """
    Service for managing MCP Gateways and their associated tools, resources, and prompts.
    """
    
    def _update_or_create_tools(self, gateway, tools_data: List[Dict[str, Any]], created_via: str = "auto_refresh") -> None:
        """
        Update or create tools for the given gateway.
        
        Args:
            gateway: The gateway object
            tools_data: List of tool data dictionaries
            created_via: How the operation was triggered ('auto_refresh', 'health_check', 'rediscovery', 'update')
        """
        should_update_visibility = created_via == "update"
        
        for tool_data in tools_data:
            # Find existing tool or create new one
            existing_tool = self._find_existing_tool(gateway, tool_data)
            
            if existing_tool:
                # Update existing tool
                fields_to_update = []
                
                # Only update visibility if this is a manual update
                if should_update_visibility:
                    existing_tool.visibility = gateway.visibility
                    fields_to_update.append('visibility')
                
                # Always update other fields
                for field in ['name', 'description', 'parameters', 'capabilities']:
                    if field in tool_data and getattr(existing_tool, field, None) != tool_data[field]:
                        setattr(existing_tool, field, tool_data[field])
                        fields_to_update.append(field)
                
                if fields_to_update:
                    self._save_tool(existing_tool, fields_to_update)
            else:
                # Create new tool
                new_tool = self._create_tool(tool_data, gateway)
                # Set visibility for new tools based on gateway
                new_tool.visibility = gateway.visibility
                self._save_tool(new_tool)
    
    def _update_or_create_resources(self, gateway, resources_data: List[Dict[str, Any]], created_via: str = "auto_refresh") -> None:
        """
        Update or create resources for the given gateway.
        
        Args:
            gateway: The gateway object
            resources_data: List of resource data dictionaries
            created_via: How the operation was triggered ('auto_refresh', 'health_check', 'rediscovery', 'update')
        """
        should_update_visibility = created_via == "update"
        
        for resource_data in resources_data:
            # Find existing resource or create new one
            existing_resource = self._find_existing_resource(gateway, resource_data)
            
            if existing_resource:
                # Update existing resource
                fields_to_update = []
                
                # Only update visibility if this is a manual update
                if should_update_visibility:
                    existing_resource.visibility = gateway.visibility
                    fields_to_update.append('visibility')
                
                # Always update other fields
                for field in ['name', 'description', 'type', 'url']:
                    if field in resource_data and getattr(existing_resource, field, None) != resource_data[field]:
                        setattr(existing_resource, field, resource_data[field])
                        fields_to_update.append(field)
                
                if fields_to_update:
                    self._save_resource(existing_resource, fields_to_update)
            else:
                # Create new resource
                new_resource = self._create_resource(resource_data, gateway)
                # Set visibility for new resources based on gateway
                new_resource.visibility = gateway.visibility
                self._save_resource(new_resource)
    
    def _update_or_create_prompts(self, gateway, prompts_data: List[Dict[str, Any]], created_via: str = "auto_refresh") -> None:
        """
        Update or create prompts for the given gateway.
        
        Args:
            gateway: The gateway object
            prompts_data: List of prompt data dictionaries
            created_via: How the operation was triggered ('auto_refresh', 'health_check', 'rediscovery', 'update')
        """
        should_update_visibility = created_via == "update"
        
        for prompt_data in prompts_data:
            # Find existing prompt or create new one
            existing_prompt = self._find_existing_prompt(gateway, prompt_data)
            
            if existing_prompt:
                # Update existing prompt
                fields_to_update = []
                
                # Only update visibility if this is a manual update
                if should_update_visibility:
                    existing_prompt.visibility = gateway.visibility
                    fields_to_update.append('visibility')
                
                # Always update other fields
                for field in ['name', 'description', 'content', 'parameters']:
                    if field in prompt_data and getattr(existing_prompt, field, None) != prompt_data[field]:
                        setattr(existing_prompt, field, prompt_data[field])
                        fields_to_update.append(field)
                
                if fields_to_update:
                    self._save_prompt(existing_prompt, fields_to_update)
            else:
                # Create new prompt
                new_prompt = self._create_prompt(prompt_data, gateway)
                # Set visibility for new prompts based on gateway
                new_prompt.visibility = gateway.visibility
                self._save_prompt(new_prompt)
    
    # Helper methods (stubs for the actual implementation)
    def _find_existing_tool(self, gateway, tool_data):
        pass
    
    def _find_existing_resource(self, gateway, resource_data):
        pass
    
    def _find_existing_prompt(self, gateway, prompt_data):
        pass
    
    def _create_tool(self, tool_data, gateway):
        pass
    
    def _create_resource(self, resource_data, gateway):
        pass
    
    def _create_prompt(self, prompt_data, gateway):
        pass
    
    def _save_tool(self, tool, fields_to_update=None):
        pass
    
    def _save_resource(self, resource, fields_to_update=None):
        pass
    
    def _save_prompt(self, prompt, fields_to_update=None):
        pass