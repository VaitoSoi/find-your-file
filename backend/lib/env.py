from os import getenv
from typing import cast

DB_URL = getenv("DB_URL", "sqlite+aiosqlie:///data/database.db")

BUCKET_NAME = getenv("BUCKET_NAME", "find_your_file")
BUCKET_ENDPOINT = getenv("BUCKET_ENDPOINT")
BUCKET_ACCESS_KEY = getenv("BUCKET_ACCESS_KEY")
BUCKET_SECRET_KEY = getenv("BUCKET_SECRET_KEY")
BUCKET_REGION = getenv("BUCKET_REGION")

if BUCKET_ENDPOINT is None:
    raise ValueError("missing bucket enpoint")
BUCKET_ENDPOINT = cast(str, BUCKET_ENDPOINT)
