from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class A2AAgentAggregateMetrics:
    def __init__(self, **kwargs):
        # Initialize with kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
