"""Custom filters: is_admin, has_access."""
from aiogram.filters import BaseFilter
from aiogram.types import Message

from src.db.repository import get_user_by_telegram_id


class IsAdminFilter(BaseFilter):
    """User is in config admin_ids or DB user with is_admin."""

    def __init__(self, admin_ids: list[int], db_path=None):
        self.admin_ids = set(admin_ids or [])
        self.db_path = db_path

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        uid = message.from_user.id
        if uid in self.admin_ids:
            return True
        user = await get_user_by_telegram_id(uid, self.db_path)
        return user is not None and user.is_admin


class HasAccessFilter(BaseFilter):
    """User is admin or registered (in DB) and active."""

    def __init__(self, admin_ids: list[int], db_path=None):
        self.admin_ids = set(admin_ids or [])
        self.db_path = db_path

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        uid = message.from_user.id
        if uid in self.admin_ids:
            return True
        user = await get_user_by_telegram_id(uid, self.db_path)
        return user is not None and user.is_active
