import asyncio
import logging
import signal
import sys
from typing import Any

# Import SSL context cache functions
from ssl_context_cache import clear_ssl_context_cache

logger = logging.getLogger(__name__)


def _sighup_reload() -> None:
    """Clear SSL context cache on SIGHUP for cert rotation."""
    try:
        clear_ssl_context_cache()
        logger.info("SIGHUP: SSL context cache cleared")
    except Exception as exc:
        logger.error(f"SIGHUP handler failed: {exc}")


def _sighup_handler(signum: int, frame: Any) -> None:
    """Schedule async cache reload (async-safe)."""
    logger.info("Received SIGHUP signal, scheduling SSL context cache refresh")
    try:
        event_loop = asyncio.get_running_loop()
        event_loop.create_task(_sighup_reload())
    except RuntimeError:
        logger.warning("SIGHUP received but event loop not running; skipping async reload")


def setup_sighup_handler():
    """Setup SIGHUP signal handler for certificate rotation."""
    if sys.platform != "win32":
        # Windows doesn't support SIGHUP
        signal.signal(signal.SIGHUP, _sighup_handler)

# Setup the handler when module is imported
setup_sighup_handler()
