import json

class GatewayService:
    def _update_or_create_tools(self, tool, auth_value):
        # Ensure auth_value is a string before writing to VARCHAR column
        if isinstance(auth_value, dict):
            auth_value = json.dumps(auth_value)
        
        # Simulate updating or creating the tool with the auth_value
        print(f"Updating or creating tool with auth_value: {auth_value}")

# Example usage
if __name__ == "__main__":
    service = GatewayService()
    tool = {'name': 'example_tool'}
    auth_value = {'key': 'value'}
    service._update_or_create_tools(tool, auth_value)
