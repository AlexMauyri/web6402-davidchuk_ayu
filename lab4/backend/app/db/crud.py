from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, load_only

from app.db.models import Comment, Thread, User


def _page_offset(page: int, page_size: int) -> int:
    if type(page) is not int or page < 1:
        raise ValueError("page должен быть целым числом не меньше 1")
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise ValueError("page_size должен быть целым числом от 1 до 100")
    return (page - 1) * page_size


async def create_user(
    session: AsyncSession, *, login: str, password_hash: str
) -> User:
    user = User(login=login, password_hash=password_hash)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id))


async def get_user_by_login(session: AsyncSession, login: str) -> User | None:
    return await session.scalar(select(User).where(User.login == login))


async def update_user_login(
    session: AsyncSession, user_id: int, *, login: str
) -> User | None:
    user = await get_user(session, user_id)
    if user is None:
        return None
    user.login = login
    await session.flush()
    return user


async def update_user_password_hash(
    session: AsyncSession, user_id: int, *, password_hash: str
) -> User | None:
    user = await get_user(session, user_id)
    if user is None:
        return None
    user.password_hash = password_hash
    await session.flush()
    return user


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    await session.flush()
    result = await session.scalar(
        delete(User)
        .where(User.id == user_id)
        .returning(User.id)
        .execution_options(synchronize_session="fetch")
    )
    return result is not None


async def create_thread(
    session: AsyncSession, *, title: str, text: str, created_by: int
) -> Thread:
    thread = Thread(title=title, text=text, created_by=created_by)
    session.add(thread)
    await session.flush()
    await get_thread(session, thread.id)
    return thread


async def get_thread(session: AsyncSession, thread_id: int) -> Thread | None:
    return await session.scalar(
        select(Thread)
        .options(joinedload(Thread.author).load_only(User.id, User.login, raiseload=True))
        .where(Thread.id == thread_id)
    )


async def list_threads(
    session: AsyncSession, *, page: int = 1, page_size: int = 20
) -> tuple[list[Thread], int]:
    offset = _page_offset(page, page_size)
    total = await session.scalar(select(func.count()).select_from(Thread))
    result = await session.scalars(
        select(Thread)
        .options(
            load_only(
                Thread.id, Thread.title, Thread.created_by, Thread.created_at,
                raiseload=True,
            ),
            joinedload(Thread.author).load_only(User.id, User.login, raiseload=True),
        )
        .order_by(Thread.created_at.desc(), Thread.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    return list(result.all()), total


async def update_thread(
    session: AsyncSession, thread_id: int, *, title: str, text: str
) -> Thread | None:
    thread = await get_thread(session, thread_id)
    if thread is None:
        return None
    thread.title = title
    thread.text = text
    await session.flush()
    return thread


async def delete_thread(session: AsyncSession, thread_id: int) -> bool:
    thread = await get_thread(session, thread_id)
    if thread is None:
        return False
    await session.delete(thread)
    await session.flush()
    return True


async def create_comment(
    session: AsyncSession, *, thread_id: int, user_id: int, text: str
) -> Comment:
    comment = Comment(thread_id=thread_id, user_id=user_id, text=text)
    session.add(comment)
    await session.flush()
    await get_comment(session, comment.id, thread_id=thread_id)
    return comment


async def get_comment(
    session: AsyncSession, comment_id: int, *, thread_id: int
) -> Comment | None:
    return await session.scalar(
        select(Comment)
        .options(joinedload(Comment.author).load_only(User.id, User.login, raiseload=True))
        .where(Comment.id == comment_id, Comment.thread_id == thread_id)
    )


async def list_comments(
    session: AsyncSession, *, thread_id: int, page: int = 1, page_size: int = 20
) -> tuple[list[Comment], int]:
    offset = _page_offset(page, page_size)
    total = await session.scalar(
        select(func.count()).select_from(Comment).where(Comment.thread_id == thread_id)
    )
    result = await session.scalars(
        select(Comment)
        .options(joinedload(Comment.author).load_only(User.id, User.login, raiseload=True))
        .where(Comment.thread_id == thread_id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .offset(offset)
        .limit(page_size)
    )
    return list(result.all()), total


async def update_comment(
    session: AsyncSession, comment_id: int, *, thread_id: int, text: str
) -> Comment | None:
    comment = await get_comment(session, comment_id, thread_id=thread_id)
    if comment is None:
        return None
    comment.text = text
    await session.flush()
    return comment


async def delete_comment(
    session: AsyncSession, comment_id: int, *, thread_id: int
) -> bool:
    comment = await get_comment(session, comment_id, thread_id=thread_id)
    if comment is None:
        return False
    await session.delete(comment)
    await session.flush()
    return True
