import motor.motor_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from config import Config
import asyncio
from typing import Optional, Any
import datetime

class Database:
    def __init__(self):
        self._client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.collection = None
        self.retry_count = 3
        self.retry_delay = 2  # seconds
        self._connected = False
        
        if not Config.DATABASE_URL:
            print("⚠️ WARNING: DATABASE_URL not set. Links will not be permanent.")
            self._connected = False
        else:
            # Connection will be established when connect() is called
            pass

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self, retry: bool = True) -> bool:
        """Database connection establish karta hai with retry logic."""
        if not Config.DATABASE_URL:
            print("⚠️ No DATABASE_URL provided. Running in memory-only mode.")
            self.db = None
            self.collection = None
            self._connected = False
            return False
        
        attempts = 0
        max_attempts = self.retry_count if retry else 1
        
        while attempts < max_attempts:
            try:
                print(f"🔄 Connecting to database... (Attempt {attempts + 1}/{max_attempts})")
                
                # Add connection timeout
                self._client = motor.motor_asyncio.AsyncIOMotorClient(
                    Config.DATABASE_URL,
                    serverSelectionTimeoutMS=5000,  # 5 second timeout
                    connectTimeoutMS=10000,
                    socketTimeoutMS=30000
                )
                
                # Test the connection
                await self._client.admin.command('ping')
                
                self.db = self._client["StreamLinksDB"]
                self.collection = self.db["links"]
                
                # Create indexes for better performance
                await self._create_indexes()
                
                self._connected = True
                print("✅ Database connection established successfully.")
                return True
                
            except ConnectionFailure as e:
                attempts += 1
                print(f"❌ Database connection failed: {e}")
                
                if attempts < max_attempts and retry:
                    print(f"⏳ Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    print("❌ Failed to connect to database after all attempts.")
                    self._connected = False
                    self.db = None
                    self.collection = None
                    
                    if self._client:
                        self._client.close()
                        self._client = None
                    
                    return False
                    
            except Exception as e:
                print(f"❌ Unexpected error connecting to database: {e}")
                self._connected = False
                return False
        
        return False

    async def _create_indexes(self):
        """Create necessary database indexes for faster queries."""
        if self.collection is not None:
            try:
                # Create unique index on _id (already exists by default)
                # Create additional index for message_id if needed
                await self.collection.create_index("message_id")
                print("✅ Database indexes created.")
            except Exception as e:
                print(f"⚠️ Warning: Could not create indexes: {e}")

    async def disconnect(self):
        """Database connection ko band karta hai."""
        if self._client:
            self._client.close()
            self._client = None
            self.db = None
            self.collection = None
            self._connected = False
            print("🔌 Database connection closed.")

    async def is_connected(self) -> bool:
        """Check if database is connected."""
        if not self._connected or self._client is None:
            return False
        
        try:
            await self._client.admin.command('ping')
            return True
        except:
            return False

    async def save_link(self, unique_id: str, message_id: int) -> bool:
        """Save a link mapping to the database."""
        if self.collection is None:
            print("⚠️ Database not available. Link not saved.")
            return False
        
        try:
            # Use update with upsert to avoid duplicate key errors
            result = await self.collection.update_one(
                {'_id': unique_id},
                {'$set': {'message_id': message_id, 'updated_at': datetime.datetime.utcnow()}},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                print(f"✅ Link saved: {unique_id} -> {message_id}")
                return True
            else:
                print(f"⚠️ Link not saved: {unique_id}")
                return False
                
        except DuplicateKeyError:
            print(f"⚠️ Duplicate key error for {unique_id}. Updating existing entry...")
            try:
                result = await self.collection.update_one(
                    {'_id': unique_id},
                    {'$set': {'message_id': message_id, 'updated_at': datetime.datetime.utcnow()}}
                )
                return result.modified_count > 0
            except Exception as e:
                print(f"❌ Error updating existing link: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error saving link to database: {e}")
            return False

    async def get_link(self, unique_id: str) -> Optional[int]:
        """Get message_id for a given unique_id."""
        if self.collection is None:
            print("⚠️ Database not available. Cannot retrieve link.")
            return None
        
        try:
            doc = await self.collection.find_one({'_id': unique_id})
            if doc:
                return doc.get('message_id')
            return None
            
        except Exception as e:
            print(f"❌ Error retrieving link from database: {e}")
            return None

    async def delete_link(self, unique_id: str) -> bool:
        """Delete a link from the database."""
        if self.collection is None:
            print("⚠️ Database not available. Cannot delete link.")
            return False
        
        try:
            result = await self.collection.delete_one({'_id': unique_id})
            if result.deleted_count > 0:
                print(f"✅ Link deleted: {unique_id}")
                return True
            else:
                print(f"⚠️ Link not found: {unique_id}")
                return False
                
        except Exception as e:
            print(f"❌ Error deleting link from database: {e}")
            return False

    async def get_all_links(self, limit: int = 100) -> list:
        """Get all links from the database (for admin purposes)."""
        if self.collection is None:
            print("⚠️ Database not available.")
            return []
        
        try:
            cursor = self.collection.find().limit(limit)
            return await cursor.to_list(length=limit)
            
        except Exception as e:
            print(f"❌ Error retrieving all links: {e}")
            return []

    async def get_link_count(self) -> int:
        """Get total number of links in the database."""
        if self.collection is None:
            return 0
        
        try:
            return await self.collection.count_documents({})
        except Exception as e:
            print(f"❌ Error counting links: {e}")
            return 0

    async def ensure_connection(self):
        """Ensure database connection is active, reconnect if needed."""
        if not await self.is_connected():
            print("🔄 Reconnecting to database...")
            await self.connect(retry=True)
            return await self.is_connected()
        return True

# Global database instance
db = Database()
