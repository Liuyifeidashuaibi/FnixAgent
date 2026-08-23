import json
import logging
import re
import base64
import binascii
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import unquote

import pydantic
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.functional_validators import ModelWrapValidatorHandler

from mcp.server.stdio import stdio_server
from mcp.types import (
    PluginResult,
    PluginViolation,
    PromptPrehookPayload,
    ToolPostInvokeResult,
    ResourcePostFetchResult,
)

from .config import EncodedExfilConfig
from .scanner import scan_container

logger = logging.getLogger(__name__)


class EncodedExfilDetectorPlugin:
    """
    Encoded Exfiltration Detection Plugin
    
    Detects suspicious encoded payloads (base64, base64url, hex, percent-encoding, 
    hex escapes) in prompt arguments, tool outputs, and resource content.
    """
    
    def __init__(self, config: Optional[EncodedExfilConfig] = None):
        self.config = config or EncodedExfilConfig()
        
        # Try to import Rust implementation
        try:
            from plugins_rust.encoded_exfil_detection import ExfilDetectorEngine
            self._rust_engine = ExfilDetectorEngine(self.config)
            self._use_rust = True
        except ImportError:
            self._rust_engine = None
            self._use_rust = False
            logger.info("Rust implementation not available, using Python fallback")
    
    async def prompt_pre_fetch(self, payload: PromptPrehookPayload) -> PluginResult:
        """Hook for prompt pre-fetch"""
        if not payload.args:
            return PluginResult()
        
        findings = await self._scan(payload.args)
        return self._build_result(findings, "prompt_pre_fetch", payload.request_id)
    
    async def tool_post_invoke(self, result: ToolPostInvokeResult) -> PluginResult:
        """Hook for tool post-invoke"""
        if not result.output:
            return PluginResult()
        
        findings = await self._scan(result.output)
        return self._build_result(findings, "tool_post_invoke", result.request_id)
    
    async def resource_post_fetch(self, result: ResourcePostFetchResult) -> PluginResult:
        """Hook for resource post-fetch"""
        if not result.content:
            return PluginResult()
        
        findings = await self._scan(result.content)
        return self._build_result(findings, "resource_post_fetch", result.request_id)
    
    async def _scan(self, container: Any) -> Dict[str, Any]:
        """Scan container for encoded exfiltration"""
        if self._use_rust and self._rust_engine:
            try:
                return self._rust_engine.scan(container)
            except Exception as e:
                logger.warning(f"Rust scan failed, falling back to Python: {e}")
                self._use_rust = False
        
        return scan_container(container, self.config)
    
    def _build_result(self, findings: Dict[str, Any], hook_name: str, request_id: str) -> PluginResult:
        """Build plugin result from findings"""
        count = findings.get("count", 0)
        
        # Log detections if enabled
        if self.config.log_detections and count > 0:
            self._log_detection(hook_name, count, findings.get("findings", []), request_id)
        
        # Block if threshold met
        if count >= self.config.min_findings_to_block and self.config.block_on_detection:
            return PluginViolation(
                code="ENCODED_EXFIL_DETECTED",
                details={
                    "count": count,
                    "findings": findings.get("findings", []),
                    "implementation": "Rust" if self._use_rust else "Python",
                    "request_id": request_id,
                }
            )
        
        # Redact if enabled and content changed
        if self.config.redact_enabled and findings.get("redacted", False):
            return PluginResult(
                metadata={
                    "count": count,
                    "findings": findings.get("findings", []),
                    "implementation": "Rust" if self._use_rust else "Python",
                    "request_id": request_id,
                    "redacted": True,
                }
            )
        
        # Return metadata only
        return PluginResult(
            metadata={
                "count": count,
                "findings": findings.get("findings", []),
                "implementation": "Rust" if self._use_rust else "Python",
                "request_id": request_id,
                "redacted": False,
            }
        )
    
    def _log_detection(self, hook_name: str, count: int, findings: List[Dict], request_id: str):
        """Log detection information"""
        encoding_types = list(set(f.get("encoding", "unknown") for f in findings))
        logger.warning(
            f"Encoded exfiltration detected in {hook_name}: {count} findings, "
            f"encoding types: {encoding_types}, request_id: {request_id}"
        )
