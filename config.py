import os
import sys
from dotenv import load_dotenv
from typing import Union, Optional

# Load environment variables
load_dotenv(".env")

class Config:
    """Configuration class for the bot with validation and helper methods."""
    
    # Required configurations
    API_ID: int = int(os.environ.get("API_ID", 0))
    API_HASH: str = os.environ.get("API_HASH", "")
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")
    OWNER_ID: int = int(os.environ.get("OWNER_ID", 0))
    
    @staticmethod
    def _parse_channel(value: str) -> Union[int, str, None]:
        """Parse channel ID or username from environment variable."""
        if not value:
            return None
        value = value.strip()
        # If it's a number, convert to int
        if value.lstrip('-').isdigit():
            return int(value)
        # Otherwise treat as username (with or without @)
        return value.lstrip('@')
    
    # Storage channel - can be int (ID) or str (username)
    _storage_channel_str = os.environ.get("STORAGE_CHANNEL", "")
    STORAGE_CHANNEL: Union[int, str, None] = _parse_channel(_storage_channel_str)
    
    # Force subscribe channel
    _fsub_channel_str = os.environ.get("FORCE_SUB_CHANNEL", "")
    FORCE_SUB_CHANNEL: Union[int, str, None] = _parse_channel(_fsub_channel_str)
    
    # URLs
    BASE_URL: str = os.environ.get("BASE_URL", "").rstrip('/')
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    REDIRECT_BLOGGER_URL: str = os.environ.get("REDIRECT_BLOGGER_URL", "")
    BLOGGER_PAGE_URL: str = os.environ.get("BLOGGER_PAGE_URL", "")
    
    # Bot username (to be set dynamically by the bot)
    BOT_USERNAME: str = os.environ.get("BOT_USERNAME", "")
    
    # Optional: Additional configurations
    MAX_FILE_SIZE: int = int(os.environ.get("MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024))  # 2GB default
    STREAM_CHUNK_SIZE: int = int(os.environ.get("STREAM_CHUNK_SIZE", 1024 * 1024))  # 1MB default
    CACHE_TTL: int = int(os.environ.get("CACHE_TTL", 3600))  # 1 hour default
    
    @classmethod
    def validate(cls) -> bool:
        """Validate all required configuration values."""
        errors = []
        warnings = []
        
        # Check required configs
        if not cls.API_ID:
            errors.append("API_ID is not set or invalid")
        if not cls.API_HASH:
            errors.append("API_HASH is not set")
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN is not set")
        if not cls.OWNER_ID:
            warnings.append("OWNER_ID is not set - admin commands may not work")
        if not cls.STORAGE_CHANNEL:
            errors.append("STORAGE_CHANNEL is not set - bot needs a storage channel")
        if not cls.BASE_URL:
            warnings.append("BASE_URL is not set - download links may not work correctly")
        
        # Check URL format
        if cls.BASE_URL and not cls.BASE_URL.startswith(('http://', 'https://')):
            warnings.append("BASE_URL should start with http:// or https://")
        
        # Log warnings and errors
        if warnings:
            print("\n⚠️ WARNINGS:")
            for warning in warnings:
                print(f"  • {warning}")
        
        if errors:
            print("\n❌ ERRORS:")
            for error in errors:
                print(f"  • {error}")
            print("\nPlease fix these errors in your .env file.")
            return False
        
        print("✅ All required configurations are valid.")
        return True
    
    @classmethod
    def is_channel_id(cls, channel: Union[int, str]) -> bool:
        """Check if the channel is an ID (int) or username."""
        return isinstance(channel, int)
    
    @classmethod
    def get_channel_display(cls, channel: Union[int, str, None]) -> str:
        """Get a human-readable channel identifier."""
        if channel is None:
            return "Not Set"
        if isinstance(channel, int):
            return f"Channel ID: {channel}"
        return f"Channel Username: @{channel.lstrip('@')}"
    
    @classmethod
    def display_config(cls) -> None:
        """Display current configuration (without sensitive data)."""
        print("\n📋 Current Configuration:")
        print(f"  • API_ID: {cls.API_ID if cls.API_ID else '❌ Not Set'}")
        print(f"  • API_HASH: {'✅ Set' if cls.API_HASH else '❌ Not Set'}")
        print(f"  • BOT_TOKEN: {'✅ Set' if cls.BOT_TOKEN else '❌ Not Set'}")
        print(f"  • OWNER_ID: {cls.OWNER_ID if cls.OWNER_ID else '⚠️ Not Set'}")
        print(f"  • STORAGE_CHANNEL: {cls.get_channel_display(cls.STORAGE_CHANNEL)}")
        print(f"  • FORCE_SUB_CHANNEL: {cls.get_channel_display(cls.FORCE_SUB_CHANNEL)}")
        print(f"  • BASE_URL: {cls.BASE_URL if cls.BASE_URL else '⚠️ Not Set'}")
        print(f"  • DATABASE_URL: {'✅ Set' if cls.DATABASE_URL else '⚠️ Not Set'}")
        print(f"  • BOT_USERNAME: {cls.BOT_USERNAME if cls.BOT_USERNAME else '⚠️ Not Set'}")
        print(f"  • MAX_FILE_SIZE: {cls.get_readable_size(cls.MAX_FILE_SIZE)}")
        print()
    
    @staticmethod
    def get_readable_size(size: int) -> str:
        """Convert size in bytes to human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"
    
    @classmethod
    def is_ready(cls) -> bool:
        """Quick check if the bot is ready to run."""
        return all([
            cls.API_ID,
            cls.API_HASH,
            cls.BOT_TOKEN,
            cls.STORAGE_CHANNEL
        ])
    
    @classmethod
    def get_storage_channel_id(cls) -> Optional[int]:
        """Get storage channel ID as integer."""
        if isinstance(cls.STORAGE_CHANNEL, int):
            return cls.STORAGE_CHANNEL
        return None
    
    @classmethod
    def get_storage_channel_username(cls) -> Optional[str]:
        """Get storage channel username as string (without @)."""
        if isinstance(cls.STORAGE_CHANNEL, str):
            return cls.STORAGE_CHANNEL.lstrip('@')
        return None
    
    @classmethod
    def update_bot_username(cls, username: str) -> None:
        """Update BOT_USERNAME dynamically."""
        if username:
            cls.BOT_USERNAME = username.lstrip('@')
            print(f"✅ Bot username set to: @{cls.BOT_USERNAME}")
        else:
            print("⚠️ Warning: Invalid bot username provided")

# Create a config instance for easy access
config = Config()

# Auto-validate on import
if not Config.is_ready():
    print("\n⚠️ Bot is not fully configured. Some features may not work.")
