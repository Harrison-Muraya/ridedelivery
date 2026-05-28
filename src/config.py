from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):

    APP_NAME: str = "RideDelivery API"
    APP_ENV: str = "development"
    DEBUG: bool = True

    SECRET_KEY: str 
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    DATABASE_URL: str  
    DATABASE_URL_SYNC: str 

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    MPESA_CONSUMER_KEY: str = ""
    MPESA_CONSUMER_SECRET: str = ""
    MPESA_SHORTCODE: str = "174379"
    MPESA_PASSKEY: str = ""
    MPESA_CALLBACK_URL: str = "https://yourdomain.com/api/v1/payments/mpesa/callback"
    MPESA_ENV: str = "sandbox"

    RIDER_RESPONSE_TIMEOUT_SECONDS: int = 300
    MAX_SEARCH_RADIUS_KM: float = 10.0
    INITIAL_SEARCH_RADIUS_KM: float = 3.0
    MAX_ASSIGNMENT_ATTEMPTS: int = 5

    FCM_SERVER_KEY: str = ""  # Firebase Cloud Messaging for push notifications

    class Config:
        env_file = ".env"


settings = Settings()
