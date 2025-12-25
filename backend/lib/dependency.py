from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SlicedUser, can_see_entry, get_session, get_user_session
from .execption import SessionNotFound, UserNotFound


async def get_user(session_id: Annotated[str, Cookie()], session: Annotated[AsyncSession, Depends(get_session)]):
    try:
        user_session = await get_user_session(session_id, session)
        return user_session.user
    except (SessionNotFound, UserNotFound):
        return None
    
async def require_user(user: Annotated[SlicedUser, Depends(get_user)]):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "no auth cookie"}
        )
    return user

# seeable = can see
async def check_can_see_id(user: Annotated[SlicedUser, Depends(get_user)], id: str):
    if not await can_see_entry(user.id, id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "you are not allowed to view this entry"}
        )
