from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

client = AsyncIOMotorClient(settings.mongo_uri)
db = client[settings.mongo_db_name]

users_collection = db["users"]
expenses_collection = db["expenses"]


async def ensure_indexes() -> None:
    """Create indexes needed for correctness and query performance.

    Run once at startup. Indexes are idempotent (safe to call repeatedly).
    """
    await users_collection.create_index("email", unique=True)

    # Every expense query is scoped to a user, and most also filter/sort by date,
    # so a compound index on (user_id, date) covers the common access patterns.
    await expenses_collection.create_index([("user_id", 1), ("date", 1)])
    await expenses_collection.create_index([("user_id", 1), ("category", 1)])
