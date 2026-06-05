import os
from dotenv import load_dotenv

load_dotenv()

#ALLOWED_ACTIVITY_TYPES = os.getenv("ALLOWED_ACTIVITY_TYPES", "").split(",")
HASURA_URL = str(os.getenv("HASURA_URL"))
HASURA_ADMIN_SECRET = str(os.getenv("HASURA_ADMIN_SECRET"))
ACROSS_CLIENT_ID = str(os.getenv("ACROSS_CLIENT_ID"))
ACROSS_CLIENT_SECRET = str(os.getenv("ACROSS_CLIENT_SECRET"))