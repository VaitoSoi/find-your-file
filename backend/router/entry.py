from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lib.db import (
    EntryType,
    SlicedUser,
    UpdateEntry,
    add_entry,
    delete_entry,
    finalize,
    get_entries,
    get_entry,
    get_session,
    remove_entry,
    restore_entry,
    update_entry,
)
from lib.dependency import check_can_see_id, require_user
from lib.storage import add_object, get_object

router = APIRouter(prefix="/entry", tags=["entry"])


@router.get("/metadatas", summary="Get all entries' metadata")
async def api_get_entries(
    user: Annotated[SlicedUser, Depends(require_user)],
    all: bool = False,  # Include "deleted" marked entries
    parent_id: Optional[str] = None,
):
    return await get_entries(user.id, all, parent_id)


@router.get(
    "/metadata", summary="Get entry metadata", dependencies=[Depends(check_can_see_id)]
)
async def api_get_entry(id: str):
    entry = await get_entry(id)
    return entry


@router.get(
    "/content",
    summary="Get entry actual content",
    dependencies=[Depends(check_can_see_id)],
)
async def api_get_entry_content(id: str):
    entry = await get_entry(id)
    return await get_object(entry.id)


@router.post("/", summary="Add new entry")
async def api_add_entry(
    user: Annotated[SlicedUser, Depends(require_user)],
    name: str,
    type: EntryType,
    parent_id: Optional[str] = None,
):
    new_entry = await add_entry(
        name=name, type=type, author_id=user.id, parent_id=parent_id
    )
    return await add_object(new_entry.id)


@router.put(
    "/finalize",
    summary="Mark entry uploading process is done",
    dependencies=[Depends(check_can_see_id)],
)
async def api_finalize(
    id: str,
):
    return await finalize(id)


@router.put(
    "/metadata",
    summary="Update entry metadata",
    dependencies=[Depends(check_can_see_id)],
)
async def api_update_entry(
    user: Annotated[SlicedUser, Depends(require_user)],
    id: str,
    data: UpdateEntry,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return await update_entry(id, data, user.id, session)


@router.delete(
    "/", summary="Mark entry as deleted", dependencies=[Depends(check_can_see_id)]
)
async def api_remove_entry(
    user: Annotated[SlicedUser, Depends(require_user)],
    id: str,
    force: bool = False
):
    if not force:
        return await remove_entry(id, user.id)

    else:
        return await delete_entry(id, user.id, True)


@router.put(
    "/restore",
    summary='Remove "deleted" label',
    dependencies=[Depends(check_can_see_id)],
)
async def api_restore_entry(
    id: str,
):
    return await restore_entry(id)
