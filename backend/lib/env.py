from os import getenv
from typing import cast
from uuid import uuid4

DB_URL = getenv("DB_URL", "sqlite+aiosqlie:///data/database.db")
REDIS_URL = getenv("REDIS_URL")

BUCKET_NAME = getenv("BUCKET_NAME", "find_your_file")
BUCKET_ENDPOINT = getenv("BUCKET_ENDPOINT")
BUCKET_ACCESS_KEY = getenv("BUCKET_ACCESS_KEY")
BUCKET_SECRET_KEY = getenv("BUCKET_SECRET_KEY")
BUCKET_REGION = getenv("BUCKET_REGION")

SIGNATURE = getenv("SIGNATURE", uuid4().__str__())

if BUCKET_ENDPOINT is None:
    raise ValueError("missing bucket enpoint")
BUCKET_ENDPOINT = cast(str, BUCKET_ENDPOINT)


if REDIS_URL is None:
    raise ValueError("missing redis connection string")
REDIS_URL = cast(str, REDIS_URL)
