import time
from typing import Any, Optional

class MCPClient:
    def __init__(self, config: MCPClientConfig):
        self.config = config
        # Other initialization...

    def _cleanup_session(self):
        # Reset session state
        # This is a placeholder for actual cleanup logic
        pass

    def _reconnect_session(self) -> bool:
        attempts = 0
        while attempts < self.config.reconnect_attempts:
            try:
                # Attempt to reconnect
                # This is a placeholder for actual reconnection logic
                print(f"Reconnecting... Attempt {attempts + 1}")
                time.sleep(self.config.reconnect_delay * (attempts + 1))
                return True
            except Exception as e:
                attempts += 1
                if attempts >= self.config.reconnect_attempts:
                    raise e
        return False

    def invoke_hook(self, hook_name: str, payload: Any) -> Any:
        try:
            # Existing invocation logic...
            response = self._send_request(hook_name, payload)
            return response
        except (McpError, PluginError) as e:
            if "session terminated" in str(e):
                self._cleanup_session()
                if self._reconnect_session():
                    # Retry the original request
                    return self.invoke_hook(hook_name, payload)
            raise e