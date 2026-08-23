from typing import Dict, Any
from mcpgateway.schemas import A2AAgentAggregateMetrics

class A2AAgentService:
    @staticmethod
    def aggregate_metrics() -> Dict[str, Any]:
        # Get cached metrics
        from mcpgateway.cache import metrics_cache
        cached = metrics_cache.metrics_cache.get()
        
        # Defensive check: ensure cached is a dict before unpacking
        if not isinstance(cached, dict):
            # Return empty dict or handle invalid cache gracefully
            return {}
        
        # Create and return the aggregate metrics object
        return A2AAgentAggregateMetrics(**cached)
