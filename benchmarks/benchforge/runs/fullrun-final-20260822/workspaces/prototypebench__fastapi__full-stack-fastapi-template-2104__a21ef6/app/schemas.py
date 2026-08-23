from pydantic import BaseModel
from typing import Optional

# Schema for user creation
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None

# Schema for user in database
class UserInDB(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    hashed_password: str
