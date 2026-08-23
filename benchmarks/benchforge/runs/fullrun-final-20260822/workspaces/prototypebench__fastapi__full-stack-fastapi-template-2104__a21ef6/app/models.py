from pydantic import BaseModel

# User model
class User(BaseModel):
    username: str
    email: str
    full_name: str | None = None
    disabled: bool | None = None
    hashed_password: str
