from datetime import datetime
from enum import Enum as PyEnum
from typing import Awaitable, Callable, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field as PydanticField
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import aliased
from sqlmodel import (
    JSON,
    Column,
    DateTime,
    Enum as SQLEnum,
    Field as SQLField,
    Relationship,
    SQLModel,
    col,
    func,
    select,
    update,
)

from .cache import cache, invalidate, update as update_cache
from .env import DB_URL
from .execption import EntryNotFound, UserNotFound

"""
Object-related models
"""


class EntryType(PyEnum):
    file = "file"
    directory = "directory"
    other = "other"


class EntryPermission(PyEnum):
    private = "private"

    public = "public"
    public_readonly = "public_readonly"

    inclusive = "inclusive"
    inclusive_readonly = "inclusive_readonly"

    other = "other"


class TransactionAction(PyEnum):
    add = "add"
    remove = "remove"  # just marked as delete, file still in bucket
    restore = "restore"  # remove the "deleted" labe;
    delete = "delete"  # actually delete file
    modify = "modify"
    other = "other"


class Entry(SQLModel, table=True):
    __tablename__ = "entry"  # pyright: ignore[reportAssignmentType]

    id: str = SQLField(primary_key=True, default_factory=lambda: uuid4().__str__())
    name: str
    size: int = SQLField(default=0)
    type: EntryType = SQLField(sa_column=SQLEnum(EntryType))

    author_id: str = SQLField(foreign_key="user.id", ondelete="CASCADE")
    author: "User" = Relationship(back_populates="entries")

    parent_id: Optional[str] = SQLField(
        default="root", foreign_key="entry.id", ondelete="CASCADE"
    )
    parent: Optional["Entry"] = Relationship()

    transactions: list["Transaction"] = Relationship(back_populates="entry")

    is_deleted: bool = SQLField(default=False)
    is_deleted_since: Optional[datetime] = SQLField(default=None)

    view: EntryPermission = SQLField(default=EntryPermission.private, sa_column=SQLEnum(EntryPermission))
    view_inclusive: list[str] = SQLField(
        default=[], sa_column=Column(JSON)
    )  # list of user can see this

    created_at: datetime = SQLField(default_factory=lambda: datetime.now())
    updated_at: datetime = SQLField(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True), onupdate=func.now()),
    )


class SlicedEntry(BaseModel):
    id: str
    name: str
    type: EntryType
    size: int
    author_id: str
    parent_id: Optional[str] = PydanticField(default=None)

    is_deleted: bool = PydanticField(default=False)
    is_deleted_since: Optional[datetime] = PydanticField(default=None)

    view: EntryPermission
    view_inclusive: list[str]

    created_at: datetime
    updated_at: datetime


class UpdateEntry(BaseModel):
    name: Optional[str]
    parent_id: Optional[str]
    view: Optional[EntryPermission]
    view_inclusive: Optional[list[str]]


class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"  # pyright: ignore[reportAssignmentType]

    id: str = SQLField(foreign_key=True, default_factory=lambda: uuid4().__str__())

    entry_id: str = SQLField(foreign_key="entry.id", ondelete="CASCADE")
    entry: Entry = Relationship(back_populates="transactions")

    actor_id: str = SQLField(foreign_key="user.id", ondelete="CASCADE")
    actor: "User" = Relationship()  # who do this transaction

    action: TransactionAction = SQLField(sa_column=SQLEnum(TransactionAction))

    created_at: datetime = SQLField(default_factory=lambda: datetime.now())


class SlicedTransaction(BaseModel):
    id: str
    entry_id: str
    actor_id: str
    action: TransactionAction
    created_at: datetime


"""
User-related models
"""


class User(SQLModel, table=True):
    __tablename__ = "user"  # pyright: ignore[reportAssignmentType]

    id: str = SQLField(default_factory=lambda: uuid4().__str__(), primary_key=True)
    username: str
    display_name: str
    password: str  # Hashed

    entries: list[Entry] = Relationship(back_populates="author")

    created_at: datetime = SQLField(default_factory=lambda: datetime.now())
    updated_at: datetime = SQLField(
        default_factory=lambda: datetime.now(),
        sa_column=Column(DateTime(timezone=True), onupdate=func.now()),
    )


class SlicedUser(BaseModel):
    id: str
    username: str
    display_name: str

    created_at: datetime
    updated_at: datetime


class UpdateUser(BaseModel):
    username: str
    display_name: str
    password: str


"""
Database connection
"""

engine = create_async_engine(DB_URL)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


async def init():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


T = TypeVar("T")


async def create_session_and_run(
    func: Callable[[AsyncSession], Awaitable[T]],
    _session: AsyncSession | None = None,
) -> T:
    if _session:
        return await func(_session)
    else:
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as _session:
            return await func(_session)


async def get_session():
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session


"""
Entry
"""

# Helper functions


def format_entry(entry: Entry):
    return SlicedEntry(
        id=entry.id,
        name=entry.name,
        type=entry.type,
        size=entry.size,
        author_id=entry.author_id,
        parent_id=entry.parent_id,
        is_deleted=entry.is_deleted,
        is_deleted_since=entry.is_deleted_since,
        view=entry.view,
        view_inclusive=entry.view_inclusive,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def format_transaction(transaction: Transaction):
    return SlicedTransaction(
        id=transaction.id,
        action=transaction.action,
        entry_id=transaction.entry_id,
        actor_id=transaction.actor_id,
        created_at=transaction.created_at,
    )


# Get all
async def _get_entries(
    author_id: str,
    all: bool = False,
    parent_id: Optional[str] = None,
    _session: Optional[AsyncSession] = None,
):
    @cache(cache_key="Entries", base_class=list[Entry])
    async def _inner(session: AsyncSession):
        statement = select(Entry).where(Entry.author_id == author_id)
        if not all:
            statement = statement.where(Entry.is_deleted == False)  # noqa: E712
        if parent_id:
            await _get_entry(parent_id)
            statement = statement.where(Entry.parent_id == parent_id)
        return list((await session.execute(statement)).scalars().all())

    return await create_session_and_run(_inner, _session)


async def get_entries(
    author_id: str,
    all: bool = False,
    parent_id: Optional[str] = None,
    _session: Optional[AsyncSession] = None,
):
    return [
        format_entry(entry)
        for entry in await _get_entries(author_id, all, parent_id, _session)
    ]


# Get one
async def _get_entry(id: str, _session: Optional[AsyncSession] = None):
    @cache(cache_key=f"Entry:{id}", base_class=Entry)
    async def _inner(session: AsyncSession):
        statement = select(Entry).where(Entry.id == id)
        entry = (await session.execute(statement)).scalar()
        if entry is None:
            raise EntryNotFound()
        return entry

    return await create_session_and_run(_inner, _session)


async def get_entry(id: str, _session: Optional[AsyncSession] = None):
    return format_entry(await _get_entry(id, _session))


# Add
async def _add_entry(
    name: str,
    type: EntryType,
    author_id: str,
    parent_id: Optional[str] = None,
    _session: Optional[AsyncSession] = None,
):
    @update_cache(cache_key=f"Entry:{id}")
    async def _inner(session: AsyncSession):
        entry_id = uuid4().__str__()
        entry = Entry(
            id=entry_id, name=name, type=type, author_id=author_id, parent_id=parent_id
        )
        transaction = Transaction(
            entry_id=entry_id, actor_id=author_id, action=TransactionAction.add
        )
        session.add_all([entry, transaction])
        await session.commit()
        return (entry, transaction)

    return await create_session_and_run(_inner, _session)


async def add_entry(
    name: str,
    type: EntryType,
    author_id: str,
    parent_id: Optional[str] = None,
    _session: Optional[AsyncSession] = None,
):
    return format_entry(
        (await _add_entry(name, type, author_id, parent_id, _session))[0]
    )


async def _update_entry(
    id: str, data: UpdateEntry, _session: Optional[AsyncSession] = None
):
    @update_cache(cache_key=f"Entry:{id}")
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id, session)

        for key, val in data.model_dump().items():
            if val:
                setattr(entry, key, val)

        session.add(entry)
        await session.commit()
        return entry

    return await create_session_and_run(_inner, _session)


async def update_entry(
    id: str, data: UpdateEntry, _session: Optional[AsyncSession] = None
):
    return format_entry(await _update_entry(id, data, _session))


# Mark delete
async def _remove_entry(
    id: str, actor_id: str, _session: Optional[AsyncSession] = None
):
    @update_cache(cache_key=f"Entry:{id}")
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id, session)

        entry_alias = aliased(Entry)
        entry_hierarchy = (
            select(Entry.id).where(Entry.id == id).cte(recursive=True)
        )  # create cte
        entry_hierarchy = entry_hierarchy.union_all(  # combine
            select(entry_alias.id).where(
                entry_alias.parent_id == entry_hierarchy.c.id  # recursive part
            )
        )
        statement = (
            update(Entry)
            .where(col(Entry.id).in_(select(entry_hierarchy.c.id)))
            .values(is_deleted=True, is_deleted_since=datetime.now())
        )
        await session.execute(statement)

        transaction = Transaction(
            action=TransactionAction.remove, entry_id=entry.id, actor_id=actor_id
        )
        session.add(transaction)

        await session.commit()
        return (entry, transaction)

    return await create_session_and_run(_inner, _session)


async def remove_entry(id: str, actor_id: str, _session: Optional[AsyncSession] = None):
    return format_entry((await _remove_entry(id, actor_id, _session))[0])


# Remove "deleted" label
async def _restore_entry(
    id: str, actor_id: str, _session: Optional[AsyncSession] = None
):
    @update_cache(cache_key=f"Entry:{id}")
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id, session)

        entry_alias = aliased(Entry)
        entry_hierarchy = (
            select(Entry.id).where(Entry.id == id).cte(recursive=True)
        )  # create cte
        entry_hierarchy = entry_hierarchy.union_all(  # combine
            select(entry_alias.id).where(
                entry_alias.parent_id == entry_hierarchy.c.id  # recursive part
            )
        )
        statement = (
            update(Entry)
            .where(col(Entry.id).in_(select(entry_hierarchy.c.id)))
            .values(is_deleted=False, is_deleted_since=None)
        )
        await session.execute(statement)

        transaction = Transaction(
            action=TransactionAction.restore, entry_id=entry.id, actor_id=actor_id
        )
        session.add(transaction)

        await session.commit()
        return (entry, transaction)

    return await create_session_and_run(_inner, _session)


async def restore_entry(
    id: str, actor_id: str, _session: Optional[AsyncSession] = None
):
    return format_entry((await _restore_entry(id, actor_id, _session))[0])


# Actually delete
async def delete_entry(id: str, actor_id: str, _session: Optional[AsyncSession] = None):
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id)
        transaction = Transaction(
            entry_id=entry.id, actor_id=actor_id, action=TransactionAction.delete
        )
        session.add(transaction)
        await session.delete(entry)
        await session.commit()
        await invalidate(f"Entry:{id}")

    return await create_session_and_run(_inner, _session)


"""
User
"""


def format_user(user: User):
    return SlicedUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


# Get all
async def _get_users(_session: Optional[AsyncSession] = None):
    async def _inner(session: AsyncSession):
        statement = select(User)
        return list((await session.execute(statement)).scalars().all())

    return await create_session_and_run(_inner, _session)


async def get_users(_session: Optional[AsyncSession] = None):
    return [format_user(user) for user in await _get_users(_session)]


# Get one
async def _get_user(id: str, _session: Optional[AsyncSession] = None): 
    async def _inner(session: AsyncSession):
        statement = select(User).where(User.id == id)
        user = (await session.execute(statement)).scalar()
        if not user:
            raise UserNotFound()
        return user

    return await create_session_and_run(_inner, _session)

async def get_user(id: str, _session: Optional[AsyncSession] = None): 
    return format_user(await _get_user(id, _session))

# Update
async def _update_user(id: str, data: UpdateUser, _session: Optional[AsyncSession] = None):
    ...
