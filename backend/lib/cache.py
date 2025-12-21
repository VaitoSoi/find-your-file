import functools
import json
from typing import Awaitable, Callable, TypeVar

from pydantic import BaseModel
from redis.asyncio import Redis

from .env import REDIS_URL

__all__ = ["cache", "update", "invalidate"]

T = TypeVar("T")

client = Redis.from_url(REDIS_URL)


def cache(
    cache_key: str,
    base_class: type[T],
    ttl: int = 60,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            cache = await client.get(cache_key) if cache_key else None
            if cache:
                if base_class and issubclass(base_class, BaseModel):
                    return base_class.model_validate_json(cache)
                else:
                    return json.loads(cache)

            else:
                value = await func(*args, **kwargs)
                if cache_key:
                    json_value = value
                    if isinstance(value, BaseModel):
                        json_value = value.model_dump_json()
                    else:
                        json_value = json.dumps(value)
                    await client.set(cache_key, json_value, ex=ttl)
                return value

        return wrapper

    return decorator


def update(
    cache_key: str,
    ttl: int = 60,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            value = await func(*args, **kwargs)
            if cache_key:
                json_value = value
                if isinstance(value, BaseModel):
                    json_value = value.model_dump_json()
                else:
                    json_value = json.dumps(value)
                await client.set(cache_key, json_value, ex=ttl)
            return value

        return wrapper

    return decorator


async def invalidate(cache_key: str, *cache_keys: list[str]):
    return await client.delete(cache_key, *cache_key)
