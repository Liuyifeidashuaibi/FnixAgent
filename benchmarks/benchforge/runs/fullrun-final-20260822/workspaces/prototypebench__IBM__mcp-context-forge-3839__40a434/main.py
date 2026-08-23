import asyncio
import logging
import signal
import sys
from typing import Optional

import redis

from config import settings
from gateway.health_check import HealthCheckManager
from gateway.mcp_session import MCPSessionPool
from gateway.tool_discovery import ToolDiscoveryManager

logger = logging.getLogger(__name__)


class MCPGatewayApp:
    """
    Main application class for MCP Gateway with automatic tool discovery.
    """
    
    def __init__(self):
        self.health_check_manager = HealthCheckManager()
        self.session_pool = MCPSessionPool(
            idle_eviction_time=settings.MCP_SESSION_POOL_IDLE_EVICTION
        )
        
        # Initialize Redis client if enabled
        redis_client = None
        if settings.REDIS_ENABLED:
            try:
                redis_client = redis.from_url(settings.REDIS_URL)
                # Test connection
                redis_client.ping()
                logger.info("Redis connection established")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                redis_client = None
        
        self.tool_discovery = ToolDiscoveryManager(
            session_pool=self.session_pool,
            health_check_manager=self.health_check_manager,
            redis_client=redis_client
        )
        
        self._shutdown_event = asyncio.Event()
        
    async def startup(self):
        """
        Application startup logic.
        """
        logger.info("Starting MCP Gateway application...")
        
        # Start background polling if enabled
        if settings.AUTO_REFRESH_SERVERS:
            self._polling_task = asyncio.create_task(
                self.tool_discovery.start_background_polling()
            )
            logger.info("Background tool discovery polling started")
        else:
            logger.info("Automatic tool discovery disabled")
        
    async def shutdown(self):
        """
        Application shutdown logic.
        """
        logger.info("Shutting down MCP Gateway application...")
        
        # Cancel background tasks
        if hasattr(self, '_polling_task'):
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        
        # Close Redis connection
        if hasattr(self, 'redis_client') and self.redis_client:
            self.redis_client.close()
            
        logger.info("MCP Gateway application shutdown complete")
    
    def signal_handler(self, signum, frame):
        """
        Handle shutdown signals.
        """
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.shutdown())
        
    async def run(self):
        """
        Main application loop.
        """
        # Setup signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda s=sig: self.signal_handler(s, None)
            )
        
        try:
            await self.startup()
            
            # Keep the application running
            await self._shutdown_event.wait()
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down...")
            await self.shutdown()
        except Exception as e:
            logger.error(f"Application error: {e}")
            await self.shutdown()


async def main():
    """
    Entry point for the MCP Gateway application.
    """
    app = MCPGatewayApp()
    await app.run()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the application
    asyncio.run(main())
