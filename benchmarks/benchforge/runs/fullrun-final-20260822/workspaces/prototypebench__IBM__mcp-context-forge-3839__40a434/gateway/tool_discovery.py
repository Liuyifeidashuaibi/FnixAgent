import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import redis

from .config import settings
from .health_check import HealthCheckManager
from .mcp_session import MCPSessionPool
from .models import MCPGateway, ToolDefinition

logger = logging.getLogger(__name__)


class ToolDiscoveryManager:
    """
    Manages automatic tool discovery for upstream MCP servers via
    usage-aware adaptive polling.
    
    Implements hot/cold server classification where:
    - Hot servers (top 20% by usage) are polled at 1x base interval (300s default)
    - Cold servers (remaining 80%) are polled at 3x base interval (900s default)
    """
    
    def __init__(
        self,
        session_pool: MCPSessionPool,
        health_check_manager: HealthCheckManager,
        redis_client: Optional[redis.Redis] = None
    ):
        self.session_pool = session_pool
        self.health_check_manager = health_check_manager
        self.redis_client = redis_client
        self._server_classification = {}  # server_id -> 'hot' | 'cold'
        self._last_classification_time = 0.0
        
    def _get_server_usage_metrics(self) -> Dict[str, Dict]:
        """
        Extract per-server metrics from pooled sessions:
        - server_last_used
        - active_session_count
        - total_use_count
        """
        metrics = {}
        
        # Get all servers from the pool
        for server_id, session_info in self.session_pool.get_all_servers().items():
            if not session_info:
                continue
                
            # Extract metrics from session info
            metrics[server_id] = {
                'server_last_used': session_info.get('last_used', 0),
                'active_session_count': session_info.get('active_count', 0),
                'total_use_count': session_info.get('total_count', 0),
                'server_id': server_id
            }
            
        return metrics
    
    def _classify_servers(self) -> Dict[str, str]:
        """
        Classify servers into hot/cold tiers based on usage patterns.
        
        Algorithm:
        1. Extract per-server metrics
        2. Filter to servers with valid pooled sessions
        3. Sort by recency (most recently used first)
        4. Top 20% -> hot, remainder -> cold
        """
        if not settings.HOT_COLD_CLASSIFICATION_ENABLED:
            # If classification is disabled, treat all as hot
            return {}
            
        metrics = self._get_server_usage_metrics()
        if not metrics:
            return {}
            
        # Sort by recency (most recent first)
        sorted_servers = sorted(
            metrics.items(),
            key=lambda x: x[1].get('server_last_used', 0),
            reverse=True
        )
        
        # Calculate top 20%
        n = len(sorted_servers)
        hot_count = max(1, int(0.20 * n))
        
        classification = {}
        for i, (server_id, _) in enumerate(sorted_servers):
            classification[server_id] = 'hot' if i < hot_count else 'cold'
            
        return classification
    
    def _get_poll_interval(self, server_id: str) -> int:
        """
        Get appropriate poll interval for a server based on its classification.
        """
        if not settings.HOT_COLD_CLASSIFICATION_ENABLED:
            return settings.GATEWAY_AUTO_REFRESH_INTERVAL
            
        classification = self._get_server_classification()
        if classification.get(server_id) == 'hot':
            return settings.GATEWAY_AUTO_REFRESH_INTERVAL
        else:
            return settings.GATEWAY_AUTO_REFRESH_INTERVAL * 3
    
    def _get_server_classification(self) -> Dict[str, str]:
        """
        Get server classification, using Redis cache if available.
        """
        if self.redis_client and settings.REDIS_ENABLED:
            try:
                # Try to get from Redis cache
                cached = self.redis_client.get('tool_discovery:classification')
                if cached:
                    import json
                    return json.loads(cached.decode('utf-8'))
            except Exception as e:
                logger.warning(f"Failed to get classification from Redis: {e}")
                
        # Fall back to local calculation
        return self._classify_servers()
    
    async def _perform_tool_discovery(self, gateway: MCPGateway) -> bool:
        """
        Perform tool discovery for a single gateway.
        """
        try:
            # Use the gateway's session to call tools/list
            session = await self.session_pool.get_session(gateway.id)
            if not session:
                logger.warning(f"No session available for gateway {gateway.id}")
                return False
                
            # Call tools/list endpoint
            tools_response = await session.tools_list()
            
            if not tools_response:
                logger.warning(f"No tools response from gateway {gateway.id}")
                return False
                
            # Reconcile tools with local registry
            await self._reconcile_tools(gateway.id, tools_response)
            return True
            
        except Exception as e:
            logger.error(f"Error during tool discovery for {gateway.id}: {e}")
            return False
    
    async def _reconcile_tools(self, gateway_id: str, tools: List[ToolDefinition]):
        """
        Reconcile discovered tools against local registry.
        Handle additions, updates, and removals.
        """
        # This would integrate with the local tool registry
        # For now, just log the discovery
        logger.info(f"Discovered {len(tools)} tools for gateway {gateway_id}")
        
        # In real implementation, this would:
        # - Add new tools
        # - Update existing tools
        # - Remove tools that no longer exist
        
    async def _poll_server(self, gateway: MCPGateway) -> bool:
        """
        Poll a single server for tool updates.
        """
        if not settings.AUTO_REFRESH_SERVERS:
            return False
            
        # Check if it's time to poll this server
        now = time.time()
        last_refresh = getattr(gateway, 'last_refresh_at', 0)
        elapsed = now - last_refresh
        
        poll_interval = self._get_poll_interval(gateway.id)
        
        if elapsed < poll_interval:
            return False
            
        # Perform tool discovery
        success = await self._perform_tool_discovery(gateway)
        
        if success:
            # Update last refresh time
            gateway.last_refresh_at = now
            
        return success
    
    async def poll_all_servers(self) -> Dict[str, bool]:
        """
        Poll all registered servers for tool updates.
        Returns dict of {server_id: success_bool}.
        """
        results = {}
        
        # Get all gateways
        gateways = await self.health_check_manager.get_all_gateways()
        
        for gateway in gateways:
            try:
                result = await self._poll_server(gateway)
                results[gateway.id] = result
            except Exception as e:
                logger.error(f"Error polling gateway {gateway.id}: {e}")
                results[gateway.id] = False
                
        return results
    
    async def start_background_polling(self):
        """
        Start the background polling loop.
        """
        if not settings.AUTO_REFRESH_SERVERS:
            logger.info("Automatic tool discovery disabled")
            return
            
        logger.info(
            f"Starting background tool discovery polling "
            f"(hot: {settings.GATEWAY_AUTO_REFRESH_INTERVAL}s, "
            f"cold: {settings.GATEWAY_AUTO_REFRESH_INTERVAL * 3}s)"
        )
        
        while True:
            try:
                # Poll all servers
                results = await self.poll_all_servers()
                
                # Log summary
                successful = sum(1 for r in results.values() if r)
                total = len(results)
                logger.info(f"Tool discovery completed: {successful}/{total} servers")
                
                # Wait for next interval (use base interval as minimum)
                await asyncio.sleep(settings.GATEWAY_AUTO_REFRESH_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("Background polling cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background polling loop: {e}")
                await asyncio.sleep(60)  # Fallback sleep on error
