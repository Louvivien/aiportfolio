# backend/app/database.py

import os

from dotenv import find_dotenv, load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Locate and load the .env file
dotenv_path = find_dotenv()
if not dotenv_path:
    raise FileNotFoundError("No .env file found—make sure it's in the project root")
load_dotenv(dotenv_path)

# Grab the MongoDB URI
MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI is not set in .env")

# Initialize the async MongoDB client
client = AsyncIOMotorClient(MONGODB_URI)
db = client.aiportfolio  # your database (auto-created on first write)
