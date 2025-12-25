from datetime import datetime, timedelta
from enum import Enum as PyEnum
from typing import Awaitable, Callable, Optional, TypeVar, cast
from uuid import uuid4

# from sqlalchemy import event
from pydantic import BaseModel, Field as PydanticField
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
    and_,
    col,
    func,
    select,
    update,
)

from .cache import cache, invalidate, update as update_cache
from .env import DB_URL, MAX_SESSION_TIME
from .execption import (
    EntryNotFound,
    NotAuthor,
    SessionNotFound,
    SessionTooLong,
    UserNotFound,
)
from .hash import hash, verify
from .storage import delete_object, object_info

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


class EntryStatus(PyEnum):
    pending = "pending"
    finalized = "finalized"


class TransactionAction(PyEnum):
    add = "add"
    finalize = "finalize"
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
    type: EntryType = SQLField(sa_column=Column(SQLEnum(EntryType)))
    status: EntryStatus = SQLField(
        default=EntryStatus.pending, sa_column=Column(SQLEnum(EntryStatus))
    )

    author_id: str = SQLField(foreign_key="user.id", ondelete="CASCADE")
    author: "User" = Relationship(back_populates="entries")

    parent_id: Optional[str] = SQLField(
        default="root", foreign_key="entry.id", ondelete="CASCADE"
    )
    parent: Optional["Entry"] = Relationship()

    transactions: list["Transaction"] = Relationship(back_populates="entry")

    is_deleted: bool = SQLField(default=False)
    is_deleted_since: Optional[datetime] = SQLField(default=None)

    permission: EntryPermission = SQLField(
        default=EntryPermission.private, sa_column=Column(SQLEnum(EntryPermission))
    )
    permission_inclusive: list[str] = SQLField(
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
    status: EntryStatus
    author_id: str
    parent_id: Optional[str] = PydanticField(default=None)

    is_deleted: bool = PydanticField(default=False)
    is_deleted_since: Optional[datetime] = PydanticField(default=None)

    permission: EntryPermission
    permission_inclusive: list[str]

    created_at: datetime
    updated_at: datetime


class UpdateEntry(BaseModel):
    name: Optional[str]
    parent_id: Optional[str]
    permission: Optional[EntryPermission]
    permission_inclusive: Optional[list[str]]


class Transaction(SQLModel, table=True):
    __tablename__ = "transaction"  # pyright: ignore[reportAssignmentType]

    id: str = SQLField(primary_key=True, default_factory=lambda: uuid4().__str__())

    entry_id: str = SQLField(foreign_key="entry.id", ondelete="CASCADE")
    entry: Entry = Relationship(back_populates="transactions")

    actor_id: str = SQLField(foreign_key="user.id", ondelete="CASCADE")
    actor: "User" = Relationship()  # who do this transaction

    action: TransactionAction = SQLField(sa_column=Column(SQLEnum(TransactionAction)))

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
    username: str = SQLField(unique=True)
    display_name: str
    password: str  # Hashed

    entries: list[Entry] = Relationship(back_populates="author")
    sessions: list["Session"] = Relationship(back_populates="user")

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


class NewUser(BaseModel):
    username: str
    display_name: str
    password: str


class UpdateUser(BaseModel):
    username: Optional[str]
    display_name: Optional[str]
    password: Optional[str]


"""
Session
"""


class Session(SQLModel, table=True):
    __tablename__ = "session"  # pyright: ignore[reportAssignmentType]

    id: str = SQLField(default_factory=lambda: uuid4().__str__(), primary_key=True)

    user_id: str = SQLField(foreign_key="user.id", ondelete="CASCADE")
    user: User = Relationship()

    valid_until: datetime
    created_at: datetime = SQLField(default_factory=lambda: datetime.now())


class SlicedSession(BaseModel):
    id: str

    user_id: str
    user: SlicedUser

    valid_until: datetime
    created_at: datetime


"""
Database connection
"""

engine = create_async_engine(DB_URL)


# @event.listens_for(engine.sync_engine, "connect")
# def set_sqlite_pragma(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     cursor.execute("PRAGMA foreign_keys=ON;")
#     cursor.close()


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
        status=entry.status,
        author_id=entry.author_id,
        parent_id=entry.parent_id,
        is_deleted=entry.is_deleted,
        is_deleted_since=entry.is_deleted_since,
        permission=entry.permission,
        permission_inclusive=entry.permission_inclusive,
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
    cache_key = f"Entries#user={author_id}"
    if all:
        cache_key += "#all"
    if parent_id:
        cache_key += f"#parent={parent_id}"

    @cache(cache_key=cache_key, base_class=list[Entry])
    async def _inner(session: AsyncSession):
        conditions = [
            Entry.author_id == author_id,
            Entry.status == EntryStatus.finalized,
        ]
        if not all:
            conditions.append(Entry.is_deleted == False)  # noqa: E712
        if parent_id:
            await _get_entry(parent_id)
            conditions.append(Entry.parent_id == parent_id)
        statement = select(Entry).where(and_(*conditions))
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
    entry_id = uuid4().__str__()

    @update_cache(cache_key=f"Entry:{entry_id}")
    async def _inner(session: AsyncSession):
        entry = Entry(
            id=entry_id,
            name=name,
            type=type,
            author_id=author_id,
            parent_id=parent_id,
            status=EntryStatus.finalized
            if type == EntryType.directory
            else EntryStatus.pending,
        )
        transaction = Transaction(
            entry_id=entry_id, actor_id=author_id, action=TransactionAction.add
        )
        session.add_all([entry, transaction])
        await session.commit()
        await invalidate(f"Entries#user={entry.author_id}")
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


# Update
async def _update_entry(
    id: str, data: UpdateEntry, actor_id: str, _session: Optional[AsyncSession] = None
):
    @update_cache(cache_key=f"Entry:{id}")
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id, session)

        for key, val in data.model_dump().items():
            if val is None:
                continue
            if key == "permission" and actor_id != entry.author_id:
                raise NotAuthor()
            setattr(entry, key, val)

        transaction = Transaction(
            entry_id=id, action=TransactionAction.modify, actor_id=actor_id
        )

        session.add_all([entry, transaction])
        await session.commit()
        await invalidate(f"Entries#user={entry.author_id}")
        return entry

    return await create_session_and_run(_inner, _session)


async def update_entry(
    id: str, data: UpdateEntry, actor_id: str, _session: Optional[AsyncSession] = None
):
    return format_entry(await _update_entry(id, data, actor_id, _session))


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
        await invalidate(f"Entries#user={entry.author_id}")
        return (entry, transaction)

    return await create_session_and_run(_inner, _session)


async def remove_entry(id: str, actor_id: str, _session: Optional[AsyncSession] = None):
    return format_entry((await _remove_entry(id, actor_id, _session))[0])


# Remove "deleted" label
async def _restore_entry(id: str, _session: Optional[AsyncSession] = None):
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
            action=TransactionAction.restore,
            entry_id=entry.id,
            actor_id=entry.author_id,
        )
        session.add(transaction)

        await session.commit()
        await invalidate(f"Entries#user={entry.author_id}")
        return (entry, transaction)

    return await create_session_and_run(_inner, _session)


async def restore_entry(id: str, _session: Optional[AsyncSession] = None):
    return format_entry((await _restore_entry(id, _session))[0])


# Actually delete
async def delete_entry(id: str, actor_id: str, remove_object: bool = False, _session: Optional[AsyncSession] = None):
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id)
        transaction = Transaction(
            entry_id=entry.id, actor_id=actor_id, action=TransactionAction.delete
        )
        session.add(transaction)
        await session.delete(entry)
        if remove_object:
            await delete_object(entry.id)
        await invalidate(f"Entry:{id}", f"Entries#user={entry.author_id}")
        await session.commit()

    return await create_session_and_run(_inner, _session)


# Util
async def _finalize(id: str, _session: Optional[AsyncSession] = None):
    @update_cache(cache_key=f"Entry:{id}")
    async def _inner(session: AsyncSession):
        entry = await _get_entry(id, session)
        metadata = await object_info(entry.id)
        entry.size = metadata.size or 0
        entry.status = EntryStatus.finalized

        transaction = Transaction(
            action=TransactionAction.finalize, actor_id=entry.id, entry_id=entry.id
        )

        session.add_all([entry, transaction])
        await session.commit()
        await invalidate(f"Entries#user={entry.author_id}")
        return entry

    return await create_session_and_run(_inner, _session)


async def finalize(id: str, _session: Optional[AsyncSession] = None):
    return format_entry(await _finalize(id, _session))


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
    @cache(f"User:{id}", User)
    async def _inner(session: AsyncSession):
        statement = select(User).where(User.id == id)
        user = (await session.execute(statement)).scalar()
        if not user:
            raise UserNotFound()
        return user

    return await create_session_and_run(_inner, _session)


async def _get_user_by_username(username: str, _session: Optional[AsyncSession] = None):
    @cache(f"User#username:{username}", User)
    async def _inner(session: AsyncSession):
        statement = select(User).where(User.username == username)
        user = (await session.execute(statement)).scalar()
        if not user:
            raise UserNotFound()
        return user

    return await create_session_and_run(_inner, _session)


async def get_user(id: str, _session: Optional[AsyncSession] = None):
    return format_user(await _get_user(id, _session))


# Add one
async def _new_user(new_user: NewUser, _session: Optional[AsyncSession] = None):
    user_id = uuid4().__str__()

    @update_cache(f"User:{user_id}")
    async def _inner(session: AsyncSession):
        user = User(
            username=new_user.username,
            display_name=new_user.display_name,
            password=hash(new_user.password),
        )
        session.add(user)
        await session.commit()
        return user

    return await create_session_and_run(_inner, _session)


async def new_user(new_user: NewUser, _session: Optional[AsyncSession] = None):
    return format_user(await _new_user(new_user, _session))


# Update
async def _update_user(
    id: str, data: UpdateUser, _session: Optional[AsyncSession] = None
):
    @update_cache(f"User:{id}")
    async def _inner(session: AsyncSession):
        user = await _get_user(id, session)

        dumped_data = data.model_dump()
        for key in dumped_data:
            val = dumped_data[key]
            if key == "password":
                val = hash(val)
            setattr(user, key, val)

        session.add(user)
        await session.commit()
        return user

    return await create_session_and_run(_inner, _session)


async def update_user(
    id: str, data: UpdateUser, _session: Optional[AsyncSession] = None
):
    return format_user(await _update_user(id, data, _session))


# Delete
async def delete_user(id: str, _session: Optional[AsyncSession] = None):
    async def _inner(session: AsyncSession):
        user = await _get_user(id, session)
        await session.delete(user)
        await invalidate(f"User:{id}", "Users")

    return await create_session_and_run(_inner, _session)


# Utils
async def login(username: str, password: str, session: Optional[AsyncSession] = None):
    user = await _get_user_by_username(username, session)
    if verify(user.password, password):
        return user
    else:
        return None


async def can_see_entry(
    user_id: str,
    entry_id: Optional[str] = None,
    entry: Optional[SlicedEntry] = None,
    session: Optional[AsyncSession] = None,
):
    entry = entry or await get_entry(cast(str, entry_id), session)
    if entry is None:
        raise ValueError()

    if (
        entry.permission == EntryPermission.public
        or entry.permission == EntryPermission.public_readonly
    ):
        return True
    elif entry.permission == EntryPermission.private:
        return False
    elif (
        entry.permission == EntryPermission.inclusive
        or entry.permission == EntryPermission.inclusive_readonly
    ):
        user = await _get_user(user_id, session)
        if user.id in entry.permission_inclusive:
            return True
        else:
            return False
    else:
        return False


async def can_modify_entry(
    user_id: str, entry_id: str, session: Optional[AsyncSession] = None
):
    entry = await _get_entry(entry_id, session)

    if (
        entry.permission == EntryPermission.public_readonly
        or entry.permission == EntryPermission.inclusive_readonly
        or entry.permission == EntryPermission.private
    ):
        return False
    elif (
        entry.permission == EntryPermission.inclusive
        or entry.permission == EntryPermission.public
    ):
        user = await _get_user(user_id, session)
        if user.id in entry.permission_inclusive:
            return True
        else:
            return False
    else:
        return False


"""
Session
"""


def format_session(session: Session):
    return SlicedSession(
        id=session.id,
        user_id=session.user_id,
        user=format_user(session.user),
        valid_until=session.valid_until,
        created_at=session.created_at,
    )


# Create session
async def _create_session(
    user_id: str, expire_time: timedelta, _session: Optional[AsyncSession] = None
):
    id = uuid4().__str__()

    @update_cache(f"Session:{id}")
    async def _inner(_session: AsyncSession):
        if MAX_SESSION_TIME and expire_time > timedelta(seconds=MAX_SESSION_TIME):
            raise SessionTooLong()

        session = Session(
            id=id,
            user_id=user_id,
            valid_until=datetime.now() + expire_time,
        )
        _session.add(session)
        await _session.commit()
        return session

    return await create_session_and_run(_inner, _session)


async def create_session(
    user_id: str, expire_time: timedelta, _session: Optional[AsyncSession] = None
):
    return format_session(await _create_session(user_id, expire_time, _session))


# Get
async def _get_user_session(id: str, _session: Optional[AsyncSession] = None):
    @cache(f"Session:{id}", Session)
    async def _inner(_session: AsyncSession):
        statement = select(Session).where(Session.id == id)
        session = (await _session.execute(statement)).scalar()
        if not session:
            raise SessionNotFound()
        return session

    return await create_session_and_run(_inner, _session)


async def get_user_session(id: str, _session: Optional[AsyncSession] = None):
    return format_session(await _get_user_session(id, _session))


# Delete
async def delete_session(id: str, _session: Optional[AsyncSession] = None):
    async def _inner(_session: AsyncSession):
        session = await _get_user_session(id, _session)
        await _session.delete(session)
        await invalidate(f"Session:{id}")

    return await create_session_and_run(_inner, _session)
