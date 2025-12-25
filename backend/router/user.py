from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from lib.db import (
    NewUser,
    SlicedUser,
    UpdateUser,
    create_session,
    delete_user,
    login,
    new_user,
    update_user,
)
from lib.dependency import require_user
from lib.execption import UserNotFound
from lib.response import HTTP_EXECEPTION_MESSAGE, MESSAGE_OK

router = APIRouter(
    prefix="/user",
    tags=["user"],
)


class LoginBody(BaseModel):
    username: str
    password: str


@router.get(
    "/",
    summary="Get infomation about current user",
)
async def get_me(user: Annotated[SlicedUser | None, Depends(require_user)]):
    return user


@router.post("/", summary="Register new user")
async def api_new_user(user: NewUser):  # noqa: F821
    return await new_user(user)


@router.post(
    "/login",
    summary="Grab the session id",
    responses={
        200: MESSAGE_OK(),
        401: HTTP_EXECEPTION_MESSAGE("user not found or wrong password"),
        404: HTTP_EXECEPTION_MESSAGE("user not found"),
    },
)
async def api_login(
    body: LoginBody,
    response: Response,
    expire_time: timedelta = timedelta(days=7),
):
    try:
        user = await login(body.username, body.password)
    except UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"message": "user not found"}
        )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "wrong password"},
        )

    session = await create_session(user.id, expire_time)
    response.set_cookie("session_id", session.id)

    return {"message": "ok"}


@router.put("/", summary="Update this user")
async def api_update_user(
    user: Annotated[SlicedUser, Depends(require_user)], new_user: UpdateUser
):
    return await update_user(user.id, new_user)


@router.delete("/", summary="Delete this user", responses={200: MESSAGE_OK()})
async def api_delete_user(user: Annotated[SlicedUser, Depends(require_user)]):
    await delete_user(user.id)
    return {"message": "ok"}
