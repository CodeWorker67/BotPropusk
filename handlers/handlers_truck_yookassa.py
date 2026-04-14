"""Проверка оплаты грузового пропуска (ЮKassa)."""

from __future__ import annotations

import asyncio
import datetime
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot import bot
from config import RAZRAB, YUKASSA_SECRET_KEY, YUKASSA_SHOP_ID
from db.models import (
    AsyncSessionLocal,
    Contractor,
    Resident,
    TempPassYooKassaPayment,
    TemporaryPass,
)
from db.util import get_active_admins_managers_sb_tg_ids, text_warning
from handlers.handlers_admin_user_management import admin_reply_keyboard
from yookassa_api import get_payment_status

logger = logging.getLogger(__name__)

router = Router()


def _temp_pass_followup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оформить временный пропуск", callback_data="create_temporary_pass")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")],
        ]
    )


@router.callback_query(F.data.startswith("yk_check_"))
async def yk_check_truck_payment(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    try:
        pay_row_id = int((callback.data or "").split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    if not YUKASSA_SHOP_ID or not YUKASSA_SECRET_KEY:
        await callback.answer("Оплата недоступна", show_alert=True)
        return

    try:
        async with AsyncSessionLocal() as session:
            pay = await session.get(TempPassYooKassaPayment, pay_row_id)
            if not pay:
                await callback.answer("Платёж не найден", show_alert=True)
                return

            tp = await session.get(TemporaryPass, pay.temporary_pass_id)
            if not tp:
                await callback.answer("Пропуск не найден", show_alert=True)
                return

            res = await session.execute(select(Resident).where(Resident.tg_id == uid))
            resident = res.scalar()
            con = await session.execute(select(Contractor).where(Contractor.tg_id == uid))
            contractor = con.scalar()

            owns = False
            if tp.owner_type == "resident" and resident and tp.resident_id == resident.id:
                owns = True
            elif tp.owner_type == "contractor" and contractor and tp.contractor_id == contractor.id:
                owns = True

            if not owns:
                await callback.answer("Нет доступа", show_alert=True)
                return

            if tp.status == "approved":
                await callback.answer("Пропуск уже подтверждён", show_alert=True)
                return

            if tp.status != "awaiting_payment":
                await callback.answer("Заявка не ожидает оплаты", show_alert=True)
                return

            yk_status = await get_payment_status(YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY, pay.yookassa_payment_id)

            if yk_status == "succeeded":
                now = datetime.datetime.now()
                pay.status = "succeeded"
                pay.paid_at = now
                tp.status = "approved"
                tp.time_registration = now
                await session.commit()

                car_num = (tp.car_number or "").upper()
                kb = _temp_pass_followup_kb()
                await callback.message.answer(
                    f"✅ Ваш временный пропуск одобрен на машину с номером {car_num}",
                    reply_markup=kb,
                )
                await callback.message.answer(text_warning)

                for tg_id in await get_active_admins_managers_sb_tg_ids():
                    try:
                        if tp.owner_type == "resident" and resident:
                            note = f"Пропуск от резидента {resident.fio} на машину с номером {car_num} одобрен автоматически."
                        elif tp.owner_type == "contractor" and contractor:
                            note = (
                                f"Пропуск от подрядчика {contractor.fio}, "
                                f"{contractor.company} — {contractor.position}, "
                                f"на машину с номером {car_num} одобрен автоматически."
                            )
                        else:
                            note = f"Временный пропуск №{tp.id} одобрен автоматически после оплаты."
                        await bot.send_message(tg_id, text=note, reply_markup=admin_reply_keyboard)
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass

                await callback.answer("Оплата получена, пропуск подтверждён")
                return

            if yk_status is None:
                await callback.answer("Не удалось проверить оплату, попробуйте позже", show_alert=True)
                return

            await callback.answer("Оплаты пока не было — нажмите «Оплатить»", show_alert=True)
    except Exception as e:
        logger.exception("yk_check_truck_payment")
        await bot.send_message(RAZRAB, text=f"{uid} - {e!s}")
        await asyncio.sleep(0.05)
        await callback.answer("Ошибка", show_alert=True)
