from pydantic import BaseSettings


class Settings(BaseSettings):
    pagination_max_page_size: int = 100
    
    class Config:
        env_file = ".env"


settings = Settings()
