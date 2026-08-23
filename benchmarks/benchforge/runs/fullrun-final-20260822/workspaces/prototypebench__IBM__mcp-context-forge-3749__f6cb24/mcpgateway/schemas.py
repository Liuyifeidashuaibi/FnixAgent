from pydantic import BaseModel, validator
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Import settings - assuming this is how it's done in the actual code
try:
    from .settings import settings
except ImportError:
    # Fallback for when settings module is not available
    class MockSettings:
        validation_strict = True
    settings = MockSettings()


class ToolCreate(BaseModel):
    name: str
    description: str
    
    @validator('description')
    def validate_description(cls, v):
        # Note: backticks (`) are allowed as they are commonly used in Markdown
        # for inline code examples in tool descriptions
        forbidden_patterns = ["&&", ";", "||", "$(", "|", "> ", "< "]
        for pat in forbidden_patterns:
            if pat in v:
                if settings.validation_strict:
                    raise ValueError(f"Description contains unsafe characters: '{pat}'")
                logger.warning("Description contains potentially unsafe characters: '%s' (VALIDATION_STRICT=false, proceeding)", pat)
                break
        return v

# Other schema classes would go here...
