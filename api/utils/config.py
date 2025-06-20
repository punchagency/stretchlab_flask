import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # This is where i load my env files
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
