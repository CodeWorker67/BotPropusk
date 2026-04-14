"""По фото от админа (вне сценариев FSM) присылает file_id для использования в боте."""

import asyncio

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message
from aiogram.fsm.state import default_state

from bot import bot
from config import RAZRAB
from filters import IsAdmin

router = Router()
router.message.filter(IsAdmin())


@router.message(F.photo, StateFilter(default_state))
async def admin_reply_photo_file_id(message: Message) -> None:
    try:
        lines: list[str] = ["<b>Telegram: вложение фото</b>"]
        for n, p in enumerate(message.photo, start=1):
            lines.append(f"Размер #{n}: <code>{p.file_id}</code> (file_unique_id: <code>{p.file_unique_id}</code>)")
        lines.append("")
        lines.append("<i>Для картинки категорий грузовых ТС задайте в .env переменную TRUCK_CATEGORIES_PHOTO_FILE_ID "
                     "(лучше взять самый крупный размер — последнюю строку).</i>")
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as e:
        await bot.send_message(RAZRAB, text=f"admin_photo_info: {message.from_user.id} {e!s}")
        await asyncio.sleep(0.05)
