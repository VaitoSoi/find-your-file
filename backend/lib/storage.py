from asyncio import to_thread
from datetime import timedelta

from minio import Minio

from .env import (
    BUCKET_ACCESS_KEY,
    BUCKET_ENDPOINT,
    BUCKET_NAME,
    BUCKET_REGION,
    BUCKET_SECRET_KEY,
)

client = Minio(
    BUCKET_ENDPOINT, BUCKET_ACCESS_KEY, BUCKET_SECRET_KEY, region=BUCKET_REGION
)


async def object_info(id: str):
    return await to_thread(client.stat_object, bucket_name=BUCKET_NAME, object_name=id)


async def add_object(id: str):
    presigned_url = await to_thread(
        client.presigned_put_object,
        bucket_name=BUCKET_NAME,
        object_name=id,
        expires=timedelta(minutes=5),
    )
    return presigned_url


async def get_object(id: str):
    presigned_url = await to_thread(
        client.presigned_get_object,
        bucket_name=BUCKET_NAME,
        object_name=id,
        expires=timedelta(hours=6),
    )
    return presigned_url


async def delete_object(id: str):
    await to_thread(
        client.remove_object,
        bucket_name=BUCKET_NAME,
        object_name=id,
    )
