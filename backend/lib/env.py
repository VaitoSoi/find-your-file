from os import getenv
from typing import cast

try:
    import dotenv

    dotenv.load_dotenv()
except ImportError:
    ...

DB_URL = getenv("DB_URL", "sqlite+aiosqlie:///data/database.db")
REDIS_URL = getenv("REDIS_URL")

BUCKET_NAME = getenv("BUCKET_NAME", "find_your_file")
BUCKET_ENDPOINT = getenv("BUCKET_ENDPOINT")
BUCKET_ACCESS_KEY = getenv("BUCKET_ACCESS_KEY")
BUCKET_SECRET_KEY = getenv("BUCKET_SECRET_KEY")
BUCKET_REGION = getenv("BUCKET_REGION")

USE_HASH = getenv("USE_HASH", "true").lower() in ["true", "1", "yes"]

DEFAULT_MAX_SESSION_TIME = 30 * 24 * 60 * 60  # 30 days
try:
    MAX_SESSION_TIME = int(getenv("MAX_SESSION_TIME", DEFAULT_MAX_SESSION_TIME))
except TypeError:
    MAX_SESSION_TIME = DEFAULT_MAX_SESSION_TIME

if BUCKET_ENDPOINT is None:
    raise ValueError("missing bucket enpoint")
BUCKET_ENDPOINT = cast(str, BUCKET_ENDPOINT)


if REDIS_URL is None:
    raise ValueError("missing redis connection string")
REDIS_URL = cast(str, REDIS_URL)
