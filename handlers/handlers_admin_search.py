# handlers_admin_search.py
import asyncio
import html as html_lib
import logging
from aiogram import Router, F
from aiogram.fsm import state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func, or_, and_
from datetime import datetime, timedelta

from bot import bot
from db.models import AsyncSessionLocal, PermanentPass, TemporaryPass, Resident, Contractor
from config import PASS_TIME, ADMIN_IDS, RAZRAB, FUTURE_LIMIT
from filters import IsAdminOrManager
from db.util import get_active_admins_managers_sb_tg_ids
from temporary_truck import approved_temp_search_card_html

router = Router()
router.message.filter(IsAdminOrManager())
router.callback_query.filter(IsAdminOrManager())


class SearchStates(StatesGroup):
    WAITING_NUMBER = State()
    WAITING_DIGITS = State()
    WAITING_DESTINATION = State()


class DeletePassStates(StatesGroup):
    WAITING_REASON = State()


# Клавиатура меню поиска
def get_search_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск по номеру", callback_data="search_by_number")],
        [InlineKeyboardButton(text="🔢 Поиск по цифрам", callback_data="search_by_digits")],
        [InlineKeyboardButton(text="🏡 Поиск по номеру участка", callback_data="search_by_destination")],
        [InlineKeyboardButton(text="📋 Все временные пропуска", callback_data="all_temp_passes")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])


@router.callback_query(F.data == "search_pass")
async def search_pass_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "Выберите тип поиска пропуска:",
            reply_markup=get_search_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "search_by_number")
async def start_search_by_number(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите номер машины полностью:")
        await state.set_state(SearchStates.WAITING_NUMBER)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, SearchStates.WAITING_NUMBER)
async def search_by_number(message: Message, state: FSMContext):
    try:
        car_number = message.text.upper().strip()
        today = datetime.now().date()
        found = False
        await state.clear()

        async with AsyncSessionLocal() as session:
            # 1. Поиск постоянных пропусков резидентов
            perm_stmt = select(PermanentPass, Resident.fio, Resident.plot_number) \
                .join(Resident, PermanentPass.resident_id == Resident.id) \
                .where(
                PermanentPass.car_number == car_number,
                PermanentPass.status == 'approved'
            )
            perm_result = await session.execute(perm_stmt)
            perm_passes = perm_result.all()

            admin_stmt = select(PermanentPass).where(
                PermanentPass.car_number == car_number,
                PermanentPass.status == 'approved',
                PermanentPass.resident_id == None
            )
            admin_result = await session.execute(admin_stmt)
            admin_passes = admin_result.scalars()
            future_limit = today + timedelta(days=FUTURE_LIMIT)

            temp_res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ).join(Resident, TemporaryPass.resident_id == Resident.id).where(
                TemporaryPass.car_number == car_number,
                TemporaryPass.status == 'approved')

            temp_res_passes = []
            temp_res_result = await session.execute(temp_res_stmt)
            for res_pass in temp_res_result:
                temp_pass, fio, plot_number = res_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    temp_res_passes.append(res_pass)

            # 3. Поиск временных пропусков подрядчиков
            temp_contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.car_number == car_number,
                TemporaryPass.status == 'approved')

            temp_contr_passes = []
            temp_contr_result = await session.execute(temp_contr_stmt)
            for contr_pass in temp_contr_result:
                temp_pass, fio, company, position = contr_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    temp_contr_passes.append(contr_pass)

            temp_staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.car_number == car_number,
                TemporaryPass.status == 'approved'
            )

            temp_staff_result = await session.execute(temp_staff_stmt)
            temp_staff_passes = []
            for staff_pass in temp_staff_result.scalars().all():
                days_ = staff_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = staff_pass.visit_date + timedelta(days=days)
                if (staff_pass.visit_date <= today and old_end_date >= today) or (
                        staff_pass.visit_date > today and staff_pass.visit_date <= future_limit):
                    temp_staff_passes.append(staff_pass)

            # Обработка постоянных пропусков резидентов
            for pass_data in perm_passes:
                found = True
                perm_pass, fio, plot_number = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_permanent_{perm_pass.id}")]
                ])
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

            # Обработка постоянных пропусков staff
            for pass_data in admin_passes:
                found = True
                perm_pass = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск представителя УК</b>\n\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"🏠 Место назначения: {perm_pass.destination}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_permanent_{perm_pass.id}")]
                ])
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

            # Обработка временных пропусков резидентов
            for pass_data in temp_res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                hdr = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {html_lib.escape(str(fio or ''))}\n"
                    f"🏠 Номер участка: {html_lib.escape(str(plot_number or ''))}\n"
                )
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=False)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Обработка временных пропусков подрядчиков
            for pass_data in temp_contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                hdr = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {html_lib.escape(str(fio or ''))}\n"
                    f"🏢 Компания: {html_lib.escape(str(company or ''))}\n"
                    f"💼 Должность: {html_lib.escape(str(position or ''))}\n"
                )
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=True)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Обработка временных пропусков staff
            for temp_pass in temp_staff_passes:
                found = True
                hdr = "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=True)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Формируем итоговое сообщение
            if found:
                reply_text = "🔍 Поиск осуществлен"
            else:
                reply_text = "❌ Совпадений не найдено"

            await message.answer(
                reply_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "search_by_digits")
async def start_search_by_digits(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите часть номера машины:")
        await state.set_state(SearchStates.WAITING_DIGITS)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, SearchStates.WAITING_DIGITS)
async def search_by_digits(message: Message, state: FSMContext):
    try:
        digits = message.text.strip()
        today = datetime.now().date()
        await state.clear()
        found = False

        async with AsyncSessionLocal() as session:
            # 1. Поиск постоянных пропусков
            perm_stmt = select(PermanentPass, Resident.fio, Resident.plot_number) \
                .join(Resident, PermanentPass.resident_id == Resident.id) \
                .where(
                PermanentPass.status == 'approved',
                PermanentPass.car_number.ilike(f"%{digits}%")
            )
            perm_result = await session.execute(perm_stmt)
            perm_passes = perm_result.all()

            admin_stmt = select(PermanentPass).where(
                PermanentPass.car_number.ilike(f"%{digits}%"),
                PermanentPass.status == 'approved',
                PermanentPass.resident_id == None
            )
            admin_result = await session.execute(admin_stmt)
            admin_passes = admin_result.scalars()

            future_limit = today + timedelta(days=FUTURE_LIMIT)

            temp_res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ) \
                .join(Resident, TemporaryPass.resident_id == Resident.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.car_number.ilike(f"%{digits}%")
            )

            temp_res_result = await session.execute(temp_res_stmt)
            temp_res_passes = []
            for res_pass in temp_res_result:
                temp_pass, fio, plot_number = res_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    temp_res_passes.append(res_pass)

            # 3. Поиск временных пропусков подрядчиков
            temp_contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.car_number.ilike(f"%{digits}%")
            )

            temp_contr_result = await session.execute(temp_contr_stmt)
            temp_contr_passes = []
            for contr_pass in temp_contr_result:
                temp_pass, fio, company, position = contr_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    temp_contr_passes.append(contr_pass)

            temp_staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.status == 'approved',
                TemporaryPass.car_number.ilike(f"%{digits}%")
            )

            temp_staff_result = await session.execute(temp_staff_stmt)
            temp_staff_passes = []
            for staff_pass in temp_staff_result.scalars().all():
                days_ = staff_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = staff_pass.visit_date + timedelta(days=days)
                if (staff_pass.visit_date <= today and old_end_date >= today) or (
                        staff_pass.visit_date > today and staff_pass.visit_date <= future_limit):
                    temp_staff_passes.append(staff_pass)

            # Обработка постоянных пропусков
            for pass_data in perm_passes:
                found = True
                perm_pass, fio, plot_number = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_permanent_{perm_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            for pass_data in admin_passes:
                found = True
                perm_pass = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск представителя УК</b>\n\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"🏠 Место назначения: {perm_pass.destination}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_permanent_{perm_pass.id}")]
                ])
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

            # Обработка временных пропусков резидентов
            for pass_data in temp_res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                hdr = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {html_lib.escape(str(fio or ''))}\n"
                    f"🏠 Номер участка: {html_lib.escape(str(plot_number or ''))}\n"
                )
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=False)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Обработка временных пропусков подрядчиков
            for pass_data in temp_contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                hdr = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {html_lib.escape(str(fio or ''))}\n"
                    f"🏢 Компания: {html_lib.escape(str(company or ''))}\n"
                    f"💼 Должность: {html_lib.escape(str(position or ''))}\n"
                )
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=True)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            for temp_pass in temp_staff_passes:
                found = True
                hdr = "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=True)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

        # Формируем итоговое сообщение
        if found:
            reply_text = "🔍 Поиск осуществлен"
        else:
            reply_text = "❌ Совпадений не найдено"

        await message.answer(
            reply_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
            )
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "all_temp_passes")
async def show_all_temp_passes(callback: CallbackQuery):
    try:
        today = datetime.now().date()
        found = False

        async with AsyncSessionLocal() as session:
            future_limit = today + timedelta(days=FUTURE_LIMIT)
            res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ) \
                .join(Resident, TemporaryPass.resident_id == Resident.id) \
                .where(
                TemporaryPass.status == 'approved')

            temp_res_result = await session.execute(res_stmt)
            res_passes = []
            for res_pass in temp_res_result:
                temp_pass, fio, plot_number = res_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    res_passes.append(res_pass)

            # Поиск временных пропусков подрядчиков
            contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.status == 'approved')

            temp_contr_result = await session.execute(contr_stmt)
            contr_passes = []
            for contr_pass in temp_contr_result:
                temp_pass, fio, company, position = contr_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    contr_passes.append(contr_pass)

            staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.status == 'approved'
            )

            staff_result = await session.execute(staff_stmt)
            staff_passes = []
            for staff_pass in staff_result.scalars().all():
                days_ = staff_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = staff_pass.visit_date + timedelta(days=days)
                if (staff_pass.visit_date <= today and old_end_date >= today) or (
                        staff_pass.visit_date > today and staff_pass.visit_date <= future_limit):
                    staff_passes.append(staff_pass)

            # Обработка пропусков резидентов
            for pass_data in res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                days = 1
                days_ = temp_pass.purpose
                if days_.isdigit():
                    days = int(days_)
                if temp_pass.purpose in ['6', '13', '29']:
                    value = f'{int(temp_pass.purpose) + 1} дней\n'
                else:
                    value = '2 дня\n'
                text = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=days)).strftime('%d.%m.%Y')}\n"
                    f"Действие пропуска: {value}"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Обработка временных пропусков подрядчиков
            for pass_data in contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                days = 1
                days_ = temp_pass.purpose
                if days_.isdigit():
                    days = int(days_)
                if temp_pass.purpose in ['6', '13', '29']:
                    value = f'{int(temp_pass.purpose) + 1} дней\n'
                elif temp_pass.purpose == '1':
                    value = '2 дня\n'
                else:
                    value = '1 день\n'
                text = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {fio}\n"
                    f"🏢 Компания: {company}\n"
                    f"💼 Должность: {position}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=days)).strftime('%d.%m.%Y')}\n"
                    f"Действие пропуска: {value}"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            for temp_pass in staff_passes:
                found = True
                days = 1
                days_ = temp_pass.purpose
                if days_.isdigit():
                    days = int(days_)
                if temp_pass.purpose in ['6', '13', '29']:
                    value = f'{int(temp_pass.purpose) + 1} дней\n'
                elif temp_pass.purpose == '1':
                    value = '2 дня\n'
                else:
                    value = '1 день\n'
                text = (
                    "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=days)).strftime('%d.%m.%Y')}\n"
                    f"Действие пропуска: {value}"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Формируем итоговое сообщение
            if found:
                reply_text = "🔍 Поиск осуществлен"
            else:
                reply_text = "❌ Актуальных временных пропусков не найдено"

            await callback.message.answer(
                reply_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
                )
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "search_by_destination")
async def start_search_by_destination(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите номер участка:")
        await state.set_state(SearchStates.WAITING_DESTINATION)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, SearchStates.WAITING_DESTINATION)
async def search_by_destination(message: Message, state: FSMContext):
    try:
        dest = message.text.strip()
        today = datetime.now().date()
        await state.clear()
        found = False

        async with AsyncSessionLocal() as session:
            # 1. Поиск постоянных пропусков
            perm_stmt = select(PermanentPass, Resident.fio, Resident.plot_number) \
                .join(Resident, PermanentPass.resident_id == Resident.id) \
                .where(
                PermanentPass.status == 'approved',
                PermanentPass.destination.ilike(f"%{dest}%")
            )
            perm_result = await session.execute(perm_stmt)
            perm_passes = perm_result.all()

            admin_stmt = select(PermanentPass).where(
                PermanentPass.destination.ilike(f"%{dest}%"),
                PermanentPass.status == 'approved',
                PermanentPass.resident_id == None
            )
            admin_result = await session.execute(admin_stmt)
            admin_passes = admin_result.scalars()

            future_limit = today + timedelta(days=FUTURE_LIMIT)

            temp_res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ) \
                .join(Resident, TemporaryPass.resident_id == Resident.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.destination.ilike(f"%{dest}%")
            )

            temp_res_result = await session.execute(temp_res_stmt)
            temp_res_passes = []
            for res_pass in temp_res_result:
                temp_pass, fio, plot_number = res_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    temp_res_passes.append(res_pass)

            # 3. Поиск временных пропусков подрядчиков
            temp_contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.destination.ilike(f"%{dest}%")
            )

            temp_contr_result = await session.execute(temp_contr_stmt)
            temp_contr_passes = []
            for contr_pass in temp_contr_result:
                temp_pass, fio, company, position = contr_pass
                days_ = temp_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = temp_pass.visit_date + timedelta(days=days)
                if (temp_pass.visit_date <= today and old_end_date >= today) or (
                        temp_pass.visit_date > today and temp_pass.visit_date <= future_limit):
                    temp_contr_passes.append(contr_pass)

            temp_staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.status == 'approved',
                TemporaryPass.destination.ilike(f"%{dest}%")
            )

            temp_staff_result = await session.execute(temp_staff_stmt)
            temp_staff_passes = []
            for staff_pass in temp_staff_result.scalars().all():
                days_ = staff_pass.purpose
                days = 1
                if days_.isdigit():
                    days = int(days_)
                old_end_date = staff_pass.visit_date + timedelta(days=days)
                if (staff_pass.visit_date <= today and old_end_date >= today) or (
                        staff_pass.visit_date > today and staff_pass.visit_date <= future_limit):
                    temp_staff_passes.append(staff_pass)

            # Обработка постоянных пропусков
            for pass_data in perm_passes:
                found = True
                perm_pass, fio, plot_number = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_permanent_{perm_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            for pass_data in admin_passes:
                found = True
                perm_pass = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск представителя УК</b>\n\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"🏠 Место назначения: {perm_pass.destination}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_permanent_{perm_pass.id}")]
                ])
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

            # Обработка временных пропусков резидентов
            for pass_data in temp_res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                hdr = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {html_lib.escape(str(fio or ''))}\n"
                    f"🏠 Номер участка: {html_lib.escape(str(plot_number or ''))}\n"
                )
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=False)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            # Обработка временных пропусков подрядчиков
            for pass_data in temp_contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                hdr = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {html_lib.escape(str(fio or ''))}\n"
                    f"🏢 Компания: {html_lib.escape(str(company or ''))}\n"
                    f"💼 Должность: {html_lib.escape(str(position or ''))}\n"
                )
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=True)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

            for temp_pass in temp_staff_passes:
                found = True
                hdr = "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                text = approved_temp_search_card_html(temp_pass, hdr, include_destination=True)
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Удалить пропуск", callback_data=f"delete_temporary_{temp_pass.id}")]
                ])
                await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
                await asyncio.sleep(0.05)

        # Формируем итоговое сообщение
        if found:
            reply_text = "🔍 Поиск осуществлен"
        else:
            reply_text = "❌ Совпадений не найдено"

        await message.answer(
            reply_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
            )
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Хендлеры для удаления пропусков
@router.callback_query(F.data.startswith("delete_permanent_") | F.data.startswith("delete_temporary_"))
async def start_delete_pass(callback: CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split('_')
        pass_type = parts[1]  # permanent или temporary
        pass_id = int(parts[2])

        await state.update_data(
            pass_type=pass_type,
            pass_id=pass_id,
            message_id=callback.message.message_id,
            chat_id=callback.message.chat.id,
            original_text=callback.message.html_text
        )

        await callback.message.answer("Напишите причину удаления:")
        await state.set_state(DeletePassStates.WAITING_REASON)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(DeletePassStates.WAITING_REASON)
async def process_delete_reason(message: Message, state: FSMContext):
    try:
        reason = message.text
        data = await state.get_data()
        pass_type = data.get('pass_type')
        pass_id = data.get('pass_id')
        message_id = data.get('message_id')
        chat_id = data.get('chat_id')
        original_text = data.get('original_text')

        async with AsyncSessionLocal() as session:
            if pass_type == 'permanent':
                pass_record = await session.get(PermanentPass, pass_id)
                if pass_record:
                    # Отправляем уведомление
                    if pass_record.resident_id:
                        # Пропуск резидента
                        resident = await session.get(Resident, pass_record.resident_id)
                        if resident and resident.tg_id:
                            try:
                                await bot.send_message(
                                    resident.tg_id,
                                    f"❌ Ваш постоянный пропуск удален.\n\n"
                                    f"Марка: {pass_record.car_brand}\n"
                                    f"Модель: {pass_record.car_model}\n"
                                    f"Номер: {pass_record.car_number}\n"
                                    f"Владелец: {pass_record.car_owner}\n"
                                    f"Пункт назначения: {pass_record.destination}\n"
                                    f"Причина: {reason}"
                                )
                            except Exception as e:
                                logging.error(f"Не удалось отправить сообщение резиденту: {e}")
                    else:
                        # Пропуск представителя УК
                        tg_ids = await get_active_admins_managers_sb_tg_ids()
                        for tg_id in tg_ids:
                            try:
                                await bot.send_message(
                                    tg_id,
                                    f"❌ Постоянный пропуск представителя УК удален.\n\n"
                                    f"Марка: {pass_record.car_brand}\n"
                                    f"Модель: {pass_record.car_model}\n"
                                    f"Номер: {pass_record.car_number}\n"
                                    f"Владелец: {pass_record.car_owner}\n"
                                    f"Пункт назначения: {pass_record.destination}\n"
                                    f"Причина: {reason}"
                                )
                                await asyncio.sleep(0.05)
                            except:
                                pass

                    # Удаляем запись
                    await session.delete(pass_record)
                    await session.commit()

            elif pass_type == 'temporary':
                pass_record = await session.get(TemporaryPass, pass_id)
                if pass_record:
                    # Формируем информацию о пропуске
                    days = 1
                    days_ = pass_record.purpose
                    if days_.isdigit():
                        days = int(days_)
                    if pass_record.purpose in ['6', '13', '29']:
                        value = f'{int(pass_record.purpose) + 1} дней\n'
                    elif pass_record.purpose == '1':
                        value = '2 дня\n'
                    else:
                        value = '1 день\n'

                    pass_info = (
                        f"Тип ТС: {'Легковой' if pass_record.vehicle_type == 'car' else 'Грузовой'}\n"
                        f"Номер: {pass_record.car_number}\n"
                        f"Марка: {pass_record.car_brand}\n"
                        f"Тип груза: {pass_record.cargo_type}\n"
                        f"Пункт назначения: {pass_record.destination}\n"
                        f"Дата визита: {pass_record.visit_date.strftime('%d.%m.%Y')} - "
                        f"{(pass_record.visit_date + timedelta(days=days)).strftime('%d.%m.%Y')}\n"
                        f"Действие пропуска: {value}"
                        f"Комментарий владельца: {pass_record.owner_comment or 'нет'}\n"
                        f"Комментарий для СБ: {pass_record.security_comment or 'нет'}"
                    )

                    # Отправляем уведомление
                    if pass_record.owner_type == 'resident' and pass_record.resident_id:
                        # Пропуск резидента
                        resident = await session.get(Resident, pass_record.resident_id)
                        if resident and resident.tg_id:
                            try:
                                await bot.send_message(
                                    resident.tg_id,
                                    f"❌ Ваш временный пропуск удален.\n\n{pass_info}\n\nПричина: {reason}"
                                )
                            except Exception as e:
                                logging.error(f"Не удалось отправить сообщение резиденту: {e}")

                    elif pass_record.owner_type == 'contractor' and pass_record.contractor_id:
                        # Пропуск подрядчика
                        contractor = await session.get(Contractor, pass_record.contractor_id)
                        if contractor and contractor.tg_id:
                            try:
                                await bot.send_message(
                                    contractor.tg_id,
                                    f"❌ Ваш временный пропуск удален.\n\n{pass_info}\n\nПричина: {reason}"
                                )
                            except Exception as e:
                                logging.error(f"Не удалось отправить сообщение подрядчику: {e}")

                    else:
                        # Пропуск представителя УК
                        tg_ids = await get_active_admins_managers_sb_tg_ids()
                        for tg_id in tg_ids:
                            try:
                                await bot.send_message(
                                    tg_id,
                                    f"❌ Временный пропуск представителя УК удален.\n\n{pass_info}\n\nПричина: {reason}"
                                )
                                await asyncio.sleep(0.05)
                            except:
                                pass

                    # Удаляем запись
                    await session.delete(pass_record)
                    await session.commit()

        # Редактируем исходное сообщение
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{original_text}\n\n❌ Пропуск удален. Причина: {reason}",
                parse_mode="HTML",
                reply_markup=None
            )
        except Exception as e:
            logging.error(f"Не удалось отредактировать сообщение: {e}")

        await message.answer("✅ Пропуск успешно удален")
        await state.clear()

    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)