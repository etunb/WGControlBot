"""Inline keyboards for bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Мои конфиги", callback_data="list_configs"),
        InlineKeyboardButton(text="➕ Создать конфиг", callback_data="create_config"),
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        )
        builder.row(
            InlineKeyboardButton(text="🔗 Пригласительная ссылка", callback_data="admin_referral"),
        )
    return builder.as_markup()


def back_to_menu_kb(is_admin: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀ В меню", callback_data="back_to_menu"),
    )
    return builder.as_markup()


def subnet_choice_kb(is_admin: bool, has_isolated: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Общая сеть (10.0.113.0/24)", callback_data="subnet_common"),
    )
    builder.row(
        InlineKeyboardButton(text="Своя изолированная сеть" if has_isolated else "Создать свою изолированную сеть", callback_data="subnet_isolated"),
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="Любая изолированная (ввести номер)", callback_data="subnet_isolated_any"),
        )
    return builder.as_markup()


def config_list_kb(configs: list, prefix: str = "view_cfg", is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in configs:
        status = "✅" if c.is_enabled else "⏸"
        builder.row(
            InlineKeyboardButton(text=f"{status} {c.name} — {c.address}", callback_data=f"{prefix}_{c.id}"),
        )
    builder.row(
        InlineKeyboardButton(text="◀ В меню", callback_data="back_to_menu"),
    )
    return builder.as_markup()


def config_actions_kb(peer_id: int, is_enabled: bool, is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_enabled:
        builder.row(
            InlineKeyboardButton(text="⏸ Отключить", callback_data=f"disable_peer_{peer_id}"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="▶ Включить", callback_data=f"enable_peer_{peer_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_peer_{peer_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="◀ К списку конфигов", callback_data="list_configs"),
    )
    return builder.as_markup()


def user_list_kb(users: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for u in users:
        status = "🟢" if u.is_active else "🔴"
        admin_mark = " (admin)" if u.is_admin else ""
        builder.row(
            InlineKeyboardButton(text=f"{status} {u.telegram_id} @{u.username or '—'}{admin_mark}", callback_data=f"user_{u.id}"),
        )
    builder.row(
        InlineKeyboardButton(text="◀ В меню", callback_data="back_to_menu"),
    )
    return builder.as_markup()


def user_actions_kb(user_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_active:
        builder.row(
            InlineKeyboardButton(text="⏸ Отключить", callback_data=f"disable_user_{user_id}"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="▶ Включить", callback_data=f"enable_user_{user_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_user_{user_id}"),
    )
    return builder.as_markup()
