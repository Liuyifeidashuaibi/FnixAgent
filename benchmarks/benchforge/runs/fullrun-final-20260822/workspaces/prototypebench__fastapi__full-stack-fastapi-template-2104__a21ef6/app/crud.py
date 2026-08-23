from app.models import User

# CRUD operations for users
def get_user(db, username: str) -> User | None:
    # Dummy implementation
    return User(
        username='testuser',
        email='test@example.com',
        full_name='Test User',
        disabled=False,
        hashed_password='$argon2i$v=19$m=65536,t=2,p=1$some_salt$some_hash'
    )

def create_user(db, user: User) -> User:
    # Dummy implementation
    return user
