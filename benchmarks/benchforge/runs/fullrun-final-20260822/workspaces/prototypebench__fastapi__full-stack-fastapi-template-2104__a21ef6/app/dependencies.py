from fastapi import Depends
from app.security import get_password_hash, verify_password

# Dependency to get the password hash
async def get_password_hash_dependency(password: str):
    return get_password_hash(password)

# Dependency to verify the password
async def verify_password_dependency(plain_password: str, hashed_password: str):
    return verify_password(plain_password, hashed_password)
