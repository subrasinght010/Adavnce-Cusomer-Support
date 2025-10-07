"""
Environment Configuration - Manage different environments
"""

import os
from enum import Enum
from typing import Dict, Any


class Environment(str, Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class Config:
    """Base configuration"""
    
    # App Settings
    APP_NAME = "AI Communication System"
    VERSION = "1.0.0"
    DEBUG = False
    
    # Server
    HOST = "0.0.0.0"
    PORT = 8080
    
    # Database
    DATABASE_URL = "sqlite+aiosqlite:///./mydatabase.db"
    DB_POOL_SIZE = 20
    DB_MAX_OVERFLOW = 40
    
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "change_this_in_production")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_HOURS = 24
    
    # Workers
    ENABLE_EMAIL_WORKER = True
    ENABLE_FOLLOWUP_WORKER = True
    ENABLE_CALLBACK_WORKER = False
    
    # Logging
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "json"  # json or text
    
    # Rate Limiting
    RATE_LIMIT_ENABLED = True
    RATE_LIMIT_REQUESTS = 10
    RATE_LIMIT_WINDOW = 60  # seconds
    
    # Queue
    USE_MESSAGE_QUEUE = False
    QUEUE_MAX_SIZE = 1000
    
    # Monitoring
    ENABLE_METRICS = False
    ENABLE_HEALTH_CHECKS = True


class DevelopmentConfig(Config):
    """Development environment configuration"""
    
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    
    # Relaxed rate limiting
    RATE_LIMIT_REQUESTS = 100
    
    # Shorter intervals for testing
    EMAIL_CHECK_INTERVAL = 10
    FOLLOWUP_CHECK_INTERVAL = 60
    
    # Disable some features for development
    ENABLE_METRICS = False
    USE_MESSAGE_QUEUE = False


class StagingConfig(Config):
    """Staging environment configuration"""
    
    DEBUG = False
    LOG_LEVEL = "INFO"
    
    # Use PostgreSQL in staging
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:pass@localhost/staging_db"
    )
    
    # Enable all features
    ENABLE_EMAIL_WORKER = True
    ENABLE_FOLLOWUP_WORKER = True
    ENABLE_METRICS = True
    USE_MESSAGE_QUEUE = True


class ProductionConfig(Config):
    """Production environment configuration"""
    
    DEBUG = False
    LOG_LEVEL = "WARNING"
    
    # PostgreSQL with connection pooling
    DATABASE_URL = os.getenv("DATABASE_URL")
    DB_POOL_SIZE = 50
    DB_MAX_OVERFLOW = 100
    
    # Strict security
    SECRET_KEY = os.getenv("SECRET_KEY")  # Must be set
    
    # Enable all features
    ENABLE_EMAIL_WORKER = True
    ENABLE_FOLLOWUP_WORKER = True
    ENABLE_CALLBACK_WORKER = True
    ENABLE_METRICS = True
    USE_MESSAGE_QUEUE = True
    
    # Production rate limits
    RATE_LIMIT_REQUESTS = 5
    RATE_LIMIT_WINDOW = 60
    
    # Longer intervals to reduce load
    EMAIL_CHECK_INTERVAL = 60
    FOLLOWUP_CHECK_INTERVAL = 300


class TestingConfig(Config):
    """Testing environment configuration"""
    
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    
    # In-memory database for tests
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    
    # Disable workers during tests
    ENABLE_EMAIL_WORKER = False
    ENABLE_FOLLOWUP_WORKER = False
    
    # Fast intervals for tests
    EMAIL_CHECK_INTERVAL = 1
    FOLLOWUP_CHECK_INTERVAL = 1


# Configuration mapping
config_map = {
    Environment.DEVELOPMENT: DevelopmentConfig,
    Environment.STAGING: StagingConfig,
    Environment.PRODUCTION: ProductionConfig,
    Environment.TESTING: TestingConfig
}


def get_config() -> Config:
    """Get configuration based on environment"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    try:
        environment = Environment(env)
    except ValueError:
        print(f"⚠️ Unknown environment '{env}', defaulting to development")
        environment = Environment.DEVELOPMENT
    
    config_class = config_map.get(environment, DevelopmentConfig)
    return config_class()


def validate_config(config: Config) -> bool:
    """Validate configuration"""
    errors = []
    
    # Check required settings for production
    if isinstance(config, ProductionConfig):
        if config.SECRET_KEY == "change_this_in_production":
            errors.append("SECRET_KEY must be changed in production")
        
        if not config.DATABASE_URL:
            errors.append("DATABASE_URL must be set in production")
        
        if not os.getenv("TWILIO_ACCOUNT_SID"):
            errors.append("TWILIO_ACCOUNT_SID must be set")
        
        if not os.getenv("TWILIO_AUTH_TOKEN"):
            errors.append("TWILIO_AUTH_TOKEN must be set")
    
    if errors:
        print("\n" + "=" * 60)
        print("❌ CONFIGURATION ERRORS")
        print("=" * 60)
        for error in errors:
            print(f"  - {error}")
        print("=" * 60 + "\n")
        return False
    
    return True


def print_config(config: Config):
    """Print current configuration"""
    print("\n" + "=" * 60)
    print(f"CONFIGURATION: {config.__class__.__name__}")
    print("=" * 60)
    
    # Get all config attributes
    attrs = {
        key: value 
        for key, value in vars(config).items() 
        if not key.startswith('_')
    }
    
    for key, value in sorted(attrs.items()):
        # Hide sensitive values
        if 'SECRET' in key or 'PASSWORD' in key or 'TOKEN' in key:
            value = "***HIDDEN***"
        print(f"{key}: {value}")
    
    print("=" * 60 + "\n")


# Load configuration on import
current_config = get_config()