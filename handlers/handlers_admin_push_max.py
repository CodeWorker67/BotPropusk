"""Рассылка уведомления о боте в МАКС (команда /push_max, только админы)."""

import asyncio
import html
import logging

from aiogram import Router
from aiogram.filters import Command, StateFilter
from aiogram.types import Message
from aiogram.fsm.state import default_state
from sqlalchemy import select

from bot import bot
from config import RAZRAB
from db.models import AsyncSessionLocal, Contractor, Manager, Resident, Security
from filters import IsAdmin
from keyboard import kb_button

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(IsAdmin())

MAX_BOT_URL = "https://max.ru/id5020094422_bot"


def _max_announce_text(phone_display: str) -> str:
    return (
        f'Теперь бот работает так же в (<a href="{MAX_BOT_URL}">MAX</a>).\n\n'
        f'{MAX_BOT_URL}\n\n'
        f'Зайдите в бота, нажмите «Начать» '
        f"и введите ваш номер телефона, который вы указывали при регистрации в ТГ — "
        f"<b>{phone_display}</b>.\n\n"
        "Ваши данные автоматически подтянутся в бота МАКС и можно приступать к оформлению заявок."
    )


async def _collect_recipients() -> list[tuple[int, str, str]]:
    """
    Список (tg_id, роль для отчёта, телефон для текста).
    Один tg_id — одна запись (первая по порядку: СБ, менеджеры, резиденты, подрядчики).
    """
    async with AsyncSessionLocal() as session:
        seen: set[int] = set()
        out: list[tuple[int, str, str]] = []

        for model, role in (
            (Security, "СБ"),
            (Manager, "Менеджер"),
            (Resident, "Резидент"),
            (Contractor, "Подрядчик"),
        ):
            q = await session.execute(
                select(model.tg_id, model.phone).where(
                    model.tg_id.isnot(None),
                    model.status == True,
                )
            )
            for tg_id, phone in q.all():
                if tg_id in seen:
                    continue
                seen.add(tg_id)
                phone_str = (phone or "").strip() or "не указан в базе"
                out.append((int(tg_id), role, phone_str))
        return out


@router.message(Command("push_max"), StateFilter(default_state))
async def cmd_push_max(message: Message) -> None:
    recipients = await _collect_recipients()
    if not recipients:
        await message.answer("Нет получателей с привязанным tg_id (активные СБ, менеджеры, резиденты, подрядчики).")
        return

    markup = kb_button("Бот в МАКС", MAX_BOT_URL)
    ok = 0
    failed: list[str] = []

    await message.answer(f"Рассылка МАКС: получателей {len(recipients)}, отправляю…")

    for tg_id, role, phone_str in recipients:
        text = _max_announce_text(html.escape(phone_str))
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            ok += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            err = str(e).replace("\n", " ")[:200]
            failed.append(f"{role}, tg_id <code>{tg_id}</code>: {html.escape(err)}")
            logger.warning("push_max fail tg_id=%s: %s", tg_id, e)

    lines = [
        "<b>Отчёт рассылки МАКС</b>",
        f"Успешно: <b>{ok}</b>",
        f"Не отправлено: <b>{len(failed)}</b>",
    ]
    if failed:
        lines.append("")
        lines.append("<b>Ошибки:</b>")
        max_lines = 40
        for row in failed[:max_lines]:
            lines.append(row)
        if len(failed) > max_lines:
            lines.append(f"… и ещё {len(failed) - max_lines}.")

    report = "\n".join(lines)
    try:
        await message.answer(report, parse_mode="HTML")
    except Exception as e:
        await bot.send_message(RAZRAB, text=f"push_max report: {message.from_user.id} {e!s}")
        await message.answer(
            f"Отчёт слишком длинный. Успешно: {ok}, ошибок: {len(failed)}.",
            parse_mode="HTML",
        )
