from typing import Annotated

from fastapi import Cookie
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session, get_user_session
from .execption import SessionNotFound, UserNotFound


async def get_user(session_id: Annotated[str, Cookie()], session: Annotated[AsyncSession, get_session]):
    try:
        user_session = await get_user_session(session_id, session)
        return user_session.user
    except (SessionNotFound, UserNotFound):
        return None