import pwdlib

# Use Argon2 by default
pwd_context = pwdlib.Context(schemes=['argon2'])

# Function to get the password hash
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# Function to verify the password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Function to autoupdate old Bcrypt passwords
def autoupdate_password(hashed_password: str) -> str:
    if pwd_context.identify(hashed_password) == 'bcrypt':
        # Rehash the password using Argon2
        plain_password = pwd_context.decrypt(hashed_password)
        return get_password_hash(plain_password)
    return hashed_password
