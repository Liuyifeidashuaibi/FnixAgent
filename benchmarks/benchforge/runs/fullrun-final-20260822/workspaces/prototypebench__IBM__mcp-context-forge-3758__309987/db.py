from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Gateway(Base):
    """Gateway model with mTLS support."""
    __tablename__ = "gateways"
    
    id = Column(Integer, primary_key=True)
    # ... other fields ...
    
    # mTLS fields (as mentioned in PR lines 4609-4610)
    client_cert = Column(Text, nullable=True)
    client_key = Column(Text, nullable=True)
    
    def __init__(
        self,
        # ... other parameters ...
        client_cert: Optional[str] = None,
        client_key: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.client_cert = client_cert
        self.client_key = client_key
