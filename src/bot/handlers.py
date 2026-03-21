"""Telegram bot handlers: configs and admin."""
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.db import get_db_path
from src.db.models import SUBNET_COMMON, SUBNET_ISOLATED
from src.db.repository import (
    add_peer,
    add_user,
    create_referral_link,
    delete_peer,
    delete_user,
    get_peer_by_id,
    get_user_by_id,
    get_user_by_telegram_id,
    get_next_isolated_subnet_index,
    list_all_peers,
    list_peers_for_user,
    list_used_addresses,
    list_users,
    set_peer_enabled,
    set_user_active,
    set_user_isolated_subnet,
    use_referral_link,
)
from src.wireguard.manager import WireGuardManager, generate_keypair
from .filters import HasAccessFilter, IsAdminFilter
from .keyboards import (
    config_actions_kb,
    config_list_kb,
    main_menu,
    subnet_choice_kb,
    user_actions_kb,
    user_list_kb,
)


def build_client_config(
    private_key: str,
    address: str,
    server_public_key: str,
    endpoint: str,
    port: int,
) -> str:
    lines = [
        "[Interface]",
        f"PrivateKey = {private_key}",
        f"Address = {address}",
        "",
        "[Peer]",
        f"PublicKey = {server_public_key}",
        f"Endpoint = {endpoint}:{port}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
    ]
    return "\n".join(lines)


class CreateConfigStates(StatesGroup):
    choosing_subnet = State()
    entering_name = State()
    entering_subnet_index = State()  # admin: any isolated index


def create_router(
    admin_ids: list[int],
    wg_manager: WireGuardManager,
    server_public_key: str,
    server_endpoint: str,
    server_port: int,
    db_path: Path | None,
) -> Router:
    router = Router()
    has_access = HasAccessFilter(admin_ids)
    is_admin = IsAdminFilter(admin_ids)

    @router.message(Command("start"), F.text.regexp(r"^/start\s+ref_"))
    async def cmd_start_with_payload(message: Message):
        text = (message.text or "").strip()
        parts = text.split(maxsplit=1)
        token = (parts[1] or "").strip()
        if not token.startswith("ref_"):
            return
        uid = message.from_user.id  # type: ignore
        username = message.from_user.username if message.from_user else None
        used = await use_referral_link(token, uid, username, db_path)
        if used:
            await message.answer(
                "Вы успешно добавлены в бота. Ниже меню управления VPN.",
                reply_markup=main_menu(False),
            )
        else:
            await message.answer(
                "Эта пригласительная ссылка уже использована или недействительна. Обратитесь к администратору за новой ссылкой."
            )

    @router.message(Command("start"), has_access)
    async def cmd_start(message: Message):
        uid = message.from_user.id  # type: ignore
        user = await get_user_by_telegram_id(uid)
        if not user and uid in (admin_ids or []):
            user = await add_user(uid, message.from_user.username, True, db_path)
        is_ad = user.is_admin if user else (uid in (admin_ids or []))
        await message.answer(
            "WireGuard VPN. Управление конфигами — через меню ниже.",
            reply_markup=main_menu(is_ad),
        )

    @router.message(Command("start"))
    async def cmd_start_no_access(message: Message):
        await message.answer(
            "У вас нет доступа. Попросите у администратора пригласительную ссылку или добавление в систему."
        )

    @router.callback_query(F.data == "back_to_menu", has_access)
    async def back_to_menu(cb: CallbackQuery):
        await cb.answer()
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        is_ad = (user and user.is_admin) or (cb.from_user.id in (admin_ids or []))
        await cb.message.edit_text(
            "WireGuard VPN. Управление конфигами — через меню ниже.",
            reply_markup=main_menu(is_ad),
        )

    # --- Config list ---
    @router.callback_query(F.data == "list_configs", has_access)
    async def list_configs(cb: CallbackQuery):
        await cb.answer()
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user:
            await cb.message.edit_text("Пользователь не найден.")
            return
        configs = await list_peers_for_user(user.id, db_path)
        if not configs:
            await cb.message.edit_text("У вас пока нет конфигов.", reply_markup=main_menu(user.is_admin))
            return
        text = "Ваши конфиги (выберите для управления):\n\n" + "\n".join(
            f"{'✅' if c.is_enabled else '⏸'} {c.name} — {c.address}"
            for c in configs
        )
        await cb.message.edit_text(text, reply_markup=config_list_kb(configs, "view_cfg", user.is_admin))

    # --- View single config (to enable/disable/delete) ---
    @router.callback_query(F.data.startswith("view_cfg_"), has_access)
    async def view_config(cb: CallbackQuery):
        await cb.answer()
        peer_id = int(cb.data.split("_")[-1])
        peer = await get_peer_by_id(peer_id, db_path)
        if not peer:
            await cb.message.edit_text("Конфиг не найден.")
            return
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user or (user.id != peer.user_id and not user.is_admin):
            await cb.message.answer("Нет доступа к этому конфигу.")
            return
        text = f"{peer.name}\nАдрес: {peer.address}\nСеть: {peer.subnet_type}\nСтатус: {'вкл' if peer.is_enabled else 'выкл'}"
        await cb.message.edit_text(text, reply_markup=config_actions_kb(peer.id, peer.is_enabled, user.is_admin if user else False))

    # --- Create config flow ---
    @router.callback_query(F.data == "create_config", has_access)
    async def create_config_start(cb: CallbackQuery, state: FSMContext):
        await cb.answer()
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user:
            await cb.message.edit_text("Пользователь не найден.")
            return
        await state.set_state(CreateConfigStates.choosing_subnet)
        await state.update_data(user_id=user.id, is_admin=user.is_admin, has_isolated=user.isolated_subnet_index is not None)
        await cb.message.edit_text(
            "Выберите тип сети:",
            reply_markup=subnet_choice_kb(user.is_admin, user.isolated_subnet_index is not None),
        )

    @router.callback_query(CreateConfigStates.choosing_subnet, F.data.startswith("subnet_"))
    async def create_config_subnet_chosen(cb: CallbackQuery, state: FSMContext):
        await cb.answer()
        data = await state.get_data()
        if cb.data == "subnet_common":
            await state.update_data(subnet_type=SUBNET_COMMON, subnet_index=None)
            await state.set_state(CreateConfigStates.entering_name)
            await cb.message.edit_text(
                "Введите название интерфейса (как вам удобно его называть): латиница, цифры или подчёркивание."
            )
            return
        if cb.data == "subnet_isolated":
            user = await get_user_by_id(data["user_id"], db_path)
            if not user:
                await cb.message.edit_text("Ошибка: пользователь не найден.")
                await state.clear()
                return
            subnet_index = user.isolated_subnet_index
            if subnet_index is None:
                subnet_index = await get_next_isolated_subnet_index(db_path)
                await set_user_isolated_subnet(user.id, subnet_index, db_path)
            await state.update_data(subnet_type=SUBNET_ISOLATED, subnet_index=subnet_index)
            await state.set_state(CreateConfigStates.entering_name)
            await cb.message.edit_text(
                "Введите название интерфейса (как вам удобно его называть): латиница, цифры или подчёркивание."
            )
            return
        if cb.data == "subnet_isolated_any" and data.get("is_admin"):
            await state.set_state(CreateConfigStates.entering_subnet_index)
            await cb.message.edit_text(
                "Введите номер изолированной подсети (1–255, не 113):"
            )
            return
        await cb.message.edit_text("Неверный выбор.")
        await state.clear()

    @router.message(CreateConfigStates.entering_subnet_index, F.text)
    async def create_config_subnet_index_entered(message: Message, state: FSMContext):
        try:
            idx = int(message.text.strip())
            if idx == 113 or idx < 1 or idx > 255:
                await message.answer("Номер должен быть 1–255 и не 113.")
                return
        except ValueError:
            await message.answer("Введите число.")
            return
        await state.update_data(subnet_type=SUBNET_ISOLATED, subnet_index=idx)
        await state.set_state(CreateConfigStates.entering_name)
        await message.answer(
            "Введите название интерфейса (как вам удобно его называть): латиница, цифры или подчёркивание."
        )

    @router.message(CreateConfigStates.entering_name, F.text)
    async def create_config_name_entered(message: Message, state: FSMContext):
        name = (message.text or "").strip().replace(" ", "_")[:64] or "config"
        data = await state.get_data()
        user_id = data["user_id"]
        subnet_type = data["subnet_type"]
        subnet_index = data.get("subnet_index")

        try:
            priv, pub = generate_keypair()
            used = await list_used_addresses(db_path)
            address = wg_manager.add_peer(pub, subnet_type, subnet_index, used)
            wg_manager.reload_wg()
        except Exception as e:
            await message.answer(f"Ошибка WireGuard: {e}")
            await state.clear()
            return

        try:
            peer = await add_peer(user_id, name, subnet_type, subnet_index, address, priv, pub, db_path)
        except Exception as e:
            await message.answer(f"Ошибка БД: {e}")
            await state.clear()
            return

        config_text = build_client_config(
            priv, address, server_public_key, server_endpoint, server_port
        )
        file = BufferedInputFile(config_text.encode(), filename=f"{name}.conf")
        await message.answer_document(file, caption=f"Конфиг «{name}» создан.\nАдрес: {address}")
        await state.clear()

    # --- Disable / Enable / Delete peer ---
    @router.callback_query(F.data.startswith("disable_peer_"), has_access)
    async def disable_peer_cb(cb: CallbackQuery):
        await cb.answer()
        peer_id = int(cb.data.split("_")[-1])
        peer = await get_peer_by_id(peer_id, db_path)
        if not peer:
            await cb.message.edit_text("Конфиг не найден.")
            return
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user or (user.id != peer.user_id and not user.is_admin):
            await cb.answer("Нет доступа.", show_alert=True)
            return
        wg_manager.remove_peer(peer.public_key)
        wg_manager.reload_wg()
        await set_peer_enabled(peer_id, False, db_path)
        await cb.message.edit_text(f"Конфиг «{peer.name}» отключён.", reply_markup=config_actions_kb(peer.id, False))

    @router.callback_query(F.data.startswith("enable_peer_"), has_access)
    async def enable_peer_cb(cb: CallbackQuery):
        await cb.answer()
        peer_id = int(cb.data.split("_")[-1])
        peer = await get_peer_by_id(peer_id, db_path)
        if not peer:
            await cb.message.edit_text("Конфиг не найден.")
            return
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user or (user.id != peer.user_id and not user.is_admin):
            await cb.answer("Нет доступа.", show_alert=True)
            return
        # Addresses already in use by other enabled peers
        all_peers = await list_all_peers(db_path)
        used = {p.address for p in all_peers if p.is_enabled and p.id != peer_id}
        try:
            wg_manager.add_peer(peer.public_key, peer.subnet_type, peer.subnet_index, list(used))
            wg_manager.reload_wg()
        except Exception as e:
            await cb.message.edit_text(f"Ошибка: {e}")
            return
        await set_peer_enabled(peer_id, True, db_path)
        await cb.message.edit_text(f"Конфиг «{peer.name}» включён.", reply_markup=config_actions_kb(peer.id, True))

    @router.callback_query(F.data.startswith("delete_peer_"), has_access)
    async def delete_peer_cb(cb: CallbackQuery):
        await cb.answer()
        peer_id = int(cb.data.split("_")[-1])
        peer = await get_peer_by_id(peer_id, db_path)
        if not peer:
            await cb.message.edit_text("Конфиг не найден.")
            return
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user or (user.id != peer.user_id and not user.is_admin):
            await cb.answer("Нет доступа.", show_alert=True)
            return
        wg_manager.remove_peer(peer.public_key)
        wg_manager.reload_wg()
        await delete_peer(peer_id, db_path)
        await cb.message.edit_text("Конфиг удалён.")

    # --- Admin: users ---
    @router.callback_query(F.data == "admin_users", is_admin)
    async def admin_users_list(cb: CallbackQuery):
        await cb.answer()
        users = await list_users(db_path)
        if not users:
            await cb.message.edit_text("Нет пользователей.", reply_markup=main_menu(True))
            return
        text = "Пользователи:\n" + "\n".join(
            f"{'🟢' if u.is_active else '🔴'} {u.telegram_id} @{u.username or '—'}"
            for u in users
        )
        await cb.message.edit_text(text, reply_markup=user_list_kb(users))

    @router.callback_query(F.data.startswith("user_"), is_admin)
    async def admin_user_actions(cb: CallbackQuery):
        await cb.answer()
        user_id = int(cb.data.split("_")[-1])
        u = await get_user_by_id(user_id, db_path)
        if not u:
            await cb.message.edit_text("Пользователь не найден.")
            return
        text = f"User: {u.telegram_id} @{u.username or '—'}\nActive: {u.is_active}\nAdmin: {u.is_admin}"
        await cb.message.edit_text(text, reply_markup=user_actions_kb(u.id, u.is_active))

    @router.callback_query(F.data.startswith("disable_user_"), is_admin)
    async def admin_disable_user(cb: CallbackQuery):
        await cb.answer()
        uid = int(cb.data.split("_")[-1])
        u = await get_user_by_id(uid, db_path)
        if u:
            await set_user_active(u.telegram_id, False, db_path)
            await cb.message.edit_text("Пользователь отключён.", reply_markup=user_actions_kb(u.id, False))
        else:
            await cb.message.edit_text("Пользователь не найден.")

    @router.callback_query(F.data.startswith("enable_user_"), is_admin)
    async def admin_enable_user(cb: CallbackQuery):
        await cb.answer()
        uid = int(cb.data.split("_")[-1])
        u = await get_user_by_id(uid, db_path)
        if u:
            await set_user_active(u.telegram_id, True, db_path)
            await cb.message.edit_text("Пользователь включён.", reply_markup=user_actions_kb(u.id, True))

    @router.callback_query(F.data.startswith("delete_user_"), is_admin)
    async def admin_delete_user(cb: CallbackQuery):
        await cb.answer()
        uid = int(cb.data.split("_")[-1])
        u = await get_user_by_id(uid, db_path)
        if u:
            await delete_user(u.telegram_id, db_path)
        await cb.message.edit_text("Пользователь удалён.")

    # --- Admin: add user (by command /add_user <telegram_id> or reply) ---
    @router.message(Command("add_user"), is_admin, F.text)
    async def admin_add_user_cmd(message: Message):
        parts = (message.text or "").strip().split()
        if len(parts) < 2:
            await message.answer("Использование: /add_user <telegram_id> [admin: 0|1]")
            return
        try:
            tid = int(parts[1])
            is_admin_flag = len(parts) > 2 and parts[2] in ("1", "true", "yes")
        except ValueError:
            await message.answer("telegram_id должен быть числом.")
            return
        username = message.from_user.username if message.from_user else None
        await add_user(tid, username, is_admin_flag, db_path)
        await message.answer(f"Пользователь {tid} добавлен.")

    # --- Admin: stats ---
    @router.callback_query(F.data == "admin_stats", is_admin)
    async def admin_stats(cb: CallbackQuery):
        await cb.answer()
        peers = await list_all_peers(db_path)
        total = len(peers)
        enabled = sum(1 for p in peers if p.is_enabled)
        await cb.message.edit_text(
            f"Всего конфигов: {total}\nВключено: {enabled}",
            reply_markup=main_menu(True),
        )

    # --- Admin: one-time referral link ---
    @router.callback_query(F.data == "admin_referral", is_admin)
    async def admin_referral(cb: CallbackQuery):
        await cb.answer()
        user = await get_user_by_telegram_id(cb.from_user.id)  # type: ignore
        if not user:
            await cb.message.edit_text("Ошибка: пользователь не найден.")
            return
        token = await create_referral_link(user.id, db_path)
        me = await cb.bot.get_me()
        bot_username = me.username if me else "Bot"
        url = f"https://t.me/{bot_username}?start={token}"
        await cb.message.edit_text(
            "Одноразовая пригласительная ссылка (после перехода станет недействительной):\n\n"
            f"{url}\n\nОтправьте её пользователю. Кто первый перейдёт — тот будет добавлен; повторное использование невозможно.",
            reply_markup=main_menu(True),
        )

    return router
