import os
from dotenv import load_dotenv

load_dotenv()

HASURA_URL = os.getenv("HASURA_URL", "")
HASURA_ADMIN_SECRET = os.getenv("HASURA_ADMIN_SECRET", "")
ACROSS_CLIENT_ID = os.getenv("ACROSS_CLIENT_ID", "")
ACROSS_CLIENT_SECRET = os.getenv("ACROSS_CLIENT_SECRET", "")
