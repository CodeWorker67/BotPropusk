# handlers_admin_temporary_pass.py
import asyncio
import logging
import datetime
from typing import Union

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State, default_state
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func, delete

from bot import bot
from date_parser import parse_date
from db.models import AsyncSessionLocal, Resident, Contractor, TemporaryPass
from config import ADMIN_IDS, PAGE_SIZE, RAZRAB
from db.util import get_active_admins_managers_sb_tg_ids
from filters import IsAdminOrManager
from handlers.handlers_admin_user_management import admin_reply_keyboard
from handlers.handlers_admin_permanent_pass import passes_menu

router = Router()
router.message.filter(IsAdminOrManager())
router.callback_query.filter(IsAdminOrManager())


class TemporaryPassStates(StatesGroup):
    AWAIT_EDIT_DESTINATION = State()
    AWAIT_REJECT_COMMENT = State()
    EDITING_PASS = State()
    AWAIT_EDIT_CAR_BRAND = State()
    AWAIT_EDIT_CAR_MODEL = State()
    AWAIT_EDIT_CAR_NUMBER = State()
    AWAIT_EDIT_CARGO_TYPE = State()
    AWAIT_EDIT_PURPOSE = State()
    AWAIT_EDIT_VISIT_DATE = State()
    AWAIT_EDIT_COMMENT = State()
    AWAIT_EDIT_SECURITY_COMMENT = State()


def get_temporary_passes_management():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На подтверждении", callback_data="pending_temporary_passes")],
        [InlineKeyboardButton(text="Подтвержденные", callback_data="approved_temporary_passes")],
        [InlineKeyboardButton(text="Отклоненные", callback_data="rejected_temporary_passes")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_passes")]
    ])


@router.callback_query(F.data == "temporary_passes_menu")
async def temporary_passes_menu(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        await callback.message.edit_text(
            "Управление временными пропусками:",
            reply_markup=get_temporary_passes_management()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_passes")
async def back_to_passes(callback: CallbackQuery):
    try:
        await passes_menu(callback)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


async def show_temporary_passes(message: Union[Message, CallbackQuery], state: FSMContext, status: str):
    try:
        data = await state.get_data()
        current_page = data.get('temp_pass_current_page', 0)

        async with AsyncSessionLocal() as session:
            # Получаем общее количество заявок
            total_count = await session.scalar(
                select(func.count(TemporaryPass.id))
                .where(TemporaryPass.status == status)
            )

            # Получаем заявки для текущей страницы
            result = await session.execute(
                select(TemporaryPass, Resident.fio, Contractor.fio)
                .outerjoin(Resident, Resident.id == TemporaryPass.resident_id)
                .outerjoin(Contractor, Contractor.id == TemporaryPass.contractor_id)
                .where(TemporaryPass.status == status)
                .order_by(TemporaryPass.created_at.desc())
                .offset(current_page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            requests = result.all()

        if not requests:
            text = f"Нет пропусков со статусом '{status}'"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text, reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="temporary_passes_menu")]]))
            return

        # Формируем кнопки
        buttons = []
        for req, res_fio, con_fio in requests:
            owner_name = res_fio or con_fio or "Представитель УК Eli Estate"
            fio_short = ' '.join(owner_name.split()[:2])
            btn_text = f"{fio_short}_{req.car_number}"
            buttons.append(
                [InlineKeyboardButton(text=btn_text, callback_data=f"view_temp_pass_{req.id}")]
            )

        # Добавляем кнопки пагинации
        pagination_buttons = []
        if current_page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"temp_pass_prev_{current_page - 1}_{status}")
            )

        if (current_page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data=f"temp_pass_next_{current_page + 1}_{status}")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="temporary_passes_menu")]
        )

        status_text = {
            'pending': "На подтверждении",
            'approved': "Подтвержденные",
            'rejected': "Отклоненные"
        }[status]

        text = f"Временные пропуска ({status_text}):"
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        await state.update_data(
            temp_pass_current_page=current_page,
            temp_pass_total_count=total_count,
            temp_pass_status=status
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("pending_temporary_passes"))
async def show_pending_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await show_temporary_passes(callback, state, 'pending')
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("approved_temporary_passes"))
async def show_approved_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await show_temporary_passes(callback, state, 'approved')
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("rejected_temporary_passes"))
async def show_rejected_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await show_temporary_passes(callback, state, 'rejected')
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("temp_pass_prev_") | F.data.startswith("temp_pass_next_"))
async def handle_temp_pass_pagination(callback: CallbackQuery, state: FSMContext):
    try:
        parts = callback.data.split("_")
        action = parts[2]
        page = int(parts[3])
        status = parts[4]
        await state.update_data(temp_pass_current_page=page)
        await show_temporary_passes(callback, state, status)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


async def get_pass_owner_info(session, pass_request):
    if pass_request.owner_type == "resident":
        resident = await session.get(Resident, pass_request.resident_id)
        return f"Резидент: {resident.fio}" if resident else "Резидент не найден"
    elif pass_request.owner_type == "contractor":
        contractor = await session.get(Contractor, pass_request.contractor_id)
        return f"Подрядчик: {contractor.fio}" if contractor else "Подрядчик не найден"
    else:
        return "Представитель УК"


@router.callback_query(F.data.startswith("view_temp_pass_"))
async def view_temp_pass_details(callback: CallbackQuery, state: FSMContext):
    try:
        pass_id = int(callback.data.split("_")[-1])
        await state.update_data(current_temp_pass_id=pass_id)

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            if not pass_request:
                await callback.answer("Пропуск не найден")
                return

            owner_info = await get_pass_owner_info(session, pass_request)
            if pass_request.purpose in ['6', '13', '29']:
                value = f'{int(pass_request.purpose) + 1} дней\n'
            else:
                value = '2 дня\n'
            # Формируем текст сообщения
            text = (
                f"{owner_info}\n"
                f"Тип ТС: {'Легковой' if pass_request.vehicle_type == 'car' else 'Грузовой'}\n"
                f"Категория веса: {pass_request.weight_category or 'Н/Д'}\n"
                f"Категория длины: {pass_request.length_category or 'Н/Д'}\n"
                f"Тип груза: {pass_request.cargo_type or 'Н/Д'}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                # f"Цель визита: {pass_request.purpose}\n"
                f"Дата визита: {pass_request.visit_date.strftime('%d.%m.%Y')}\n"
                f"Действие пропуска: {value}"
                f"Комментарий владельца: {pass_request.owner_comment or 'нет'}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            if pass_request.time_registration:
                text += f"\nВремя обработки: {pass_request.time_registration.strftime('%d.%m.%Y %H:%M')}"

            # Формируем клавиатуру действий
            keyboard_buttons = []
            if pass_request.status == 'pending':
                keyboard_buttons.extend([
                    [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_temp_pass_{pass_id}")],
                    [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_temp_pass")],
                    [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_temp_pass")]
                ])

            keyboard_buttons.append(
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_temp_passes_list")]
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_temp_passes_list")
async def back_to_temp_passes_list(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        status = data.get('temp_pass_status', 'pending')
        await show_temporary_passes(callback, state, status)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("approve_temp_pass_"))
async def approve_temp_pass(callback: CallbackQuery, state: FSMContext):
    try:
        pass_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            if not pass_request:
                await callback.answer("Пропуск не найден")
                return

            pass_request.status = 'approved'
            pass_request.time_registration = datetime.datetime.now()
            await session.commit()

            # Отправляем сообщение владельцу
            text_to_all = ''
            try:
                owner_id = None
                if pass_request.owner_type == "resident" and pass_request.resident_id:
                    resident = await session.get(Resident, pass_request.resident_id)
                    owner_id = resident.tg_id
                    text_to_all = f'от резидента {resident.fio}'
                elif pass_request.owner_type == "contractor" and pass_request.contractor_id:
                    contractor = await session.get(Contractor, pass_request.contractor_id)
                    owner_id = contractor.tg_id
                    text_to_all = f'от подрядчика {contractor.company}, {contractor.position}, {contractor.fio}'

                if owner_id:
                    await bot.send_message(
                        owner_id,
                        f"✅ Ваш временный пропуск на машину {pass_request.car_brand} {pass_request.car_number} одобрен!\n"
                        f"Дата визита: {pass_request.visit_date.strftime('%d.%m.%Y')}"
                    )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение владельцу: {e}")

            tg_ids = await get_active_admins_managers_sb_tg_ids()

            for tg_id in tg_ids:
                try:
                    await bot.send_message(
                        tg_id,
                        text=f'Временный пропуск {text_to_all} на машину с номером {pass_request.car_number} одобрен.',
                        reply_markup=admin_reply_keyboard
                    )
                    await asyncio.sleep(0.05)
                except:
                    pass
            await callback.message.answer(
                "Управление временными пропусками:",
                reply_markup=get_temporary_passes_management()
            )

    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "reject_temp_pass")
async def start_reject_temp_pass(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите комментарий для владельца пропуска:")
        await state.set_state(TemporaryPassStates.AWAIT_REJECT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporaryPassStates.AWAIT_REJECT_COMMENT)
async def process_temp_reject_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        if not pass_id:
            await message.answer("Ошибка: ID пропуска не найден")
            await state.clear()
            return

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            if not pass_request:
                await message.answer("Пропуск не найден")
                await state.clear()
                return

            pass_request.status = 'rejected'
            pass_request.time_registration = datetime.datetime.now()
            pass_request.resident_comment = message.text
            await session.commit()

            # Отправляем сообщение владельцу
            try:
                owner_id = None
                if pass_request.owner_type == "resident" and pass_request.resident_id:
                    resident = await session.get(Resident, pass_request.resident_id)
                    owner_id = resident.tg_id
                elif pass_request.owner_type == "contractor" and pass_request.contractor_id:
                    contractor = await session.get(Contractor, pass_request.contractor_id)
                    owner_id = contractor.tg_id

                if owner_id:
                    await bot.send_message(
                        owner_id,
                        f"❌ Ваш временный пропуск на машину {pass_request.car_number} отклонен.\n"
                        f"Причина: {message.text}"
                    )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение владельцу: {e}")

            await message.answer("Пропуск отклонен")
            await message.answer(
                "Управление временными пропусками:",
                reply_markup=get_temporary_passes_management()
            )

        # Возвращаем админа в список
        data = await state.get_data()
        status = data.get('temp_pass_status', 'pending')
        await show_temporary_passes(message, state, status)
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


def get_temp_edit_pass_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Марка", callback_data="edit_temp_car_brand"),
            InlineKeyboardButton(text="Номер", callback_data="edit_temp_car_number"),
        ],
        [
            InlineKeyboardButton(text="Тип груза", callback_data="edit_temp_cargo_type"),
            InlineKeyboardButton(text="Дата визита", callback_data="edit_temp_visit_date"),
        ],
        [
            InlineKeyboardButton(text="Коммент. владельца", callback_data="edit_temp_comment"),
            InlineKeyboardButton(text="Пункт назначения", callback_data="edit_temp_destination"),
        ],
        [
            InlineKeyboardButton(text="Коммент. для СБ", callback_data="edit_temp_security_comment"),
            InlineKeyboardButton(text="✅ Готово", callback_data="edit_temp_finish_pass"),
        ],
    ])


@router.callback_query(F.data == "edit_temp_pass")
async def start_editing_temp_pass(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=get_temp_edit_pass_keyboard())
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "edit_temp_finish_pass", TemporaryPassStates.EDITING_PASS)
async def finish_editing_temp_pass(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            owner_info = await get_pass_owner_info(session, pass_request)
            if pass_request.purpose in ['6', '13', '29']:
                value = f'{int(pass_request.purpose) + 1} дней\n'
            else:
                value = '2 дня\n'
            text = (
                f"{owner_info}\n"
                f"Тип ТС: {'Легковой' if pass_request.vehicle_type == 'car' else 'Грузовой'}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Тип груза: {pass_request.cargo_type}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                # f"Цель визита: {pass_request.purpose}\n"
                f"Дата визита: {pass_request.visit_date.strftime('%d.%m.%Y')}\n"
                f"Действие пропуска: {value}"
                f"Комментарий владельца: {pass_request.owner_comment or 'нет'}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}"
            )

            keyboard_buttons = []
            if pass_request.status == 'pending':
                keyboard_buttons.extend([
                    [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_temp_pass_{pass_id}")],
                    [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_temp_pass")],
                    [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_temp_pass")]
                ])

            keyboard_buttons.append(
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_temp_passes_list")]
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard
            )

        await state.set_state(default_state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("edit_temp_"), TemporaryPassStates.EDITING_PASS)
async def handle_edit_temp_pass_actions(callback: CallbackQuery, state: FSMContext):
    try:
        action = callback.data.replace("edit_temp_", "")

        if action == "car_brand":
            await callback.message.answer("Введите новую марку машины:")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_CAR_BRAND)
        elif action == "car_number":
            await callback.message.answer("Введите новый номер машины:")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_CAR_NUMBER)
        elif action == "cargo_type":
            await callback.message.answer("Введите новый тип груза:")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_CARGO_TYPE)
        elif action == "destination":
            await callback.message.answer("Введите новую пункт назначения(номер участка):")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_DESTINATION)
        # elif action == "purpose":
        #     await callback.message.answer("Введите новую цель визита:")
        #     await state.set_state(TemporaryPassStates.AWAIT_EDIT_PURPOSE)
        elif action == "visit_date":
            await callback.message.answer("Введите новую дату визита (в формате ДД.ММ, ДД.ММ.ГГГГ или например '5 июня'):")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_VISIT_DATE)
        elif action == "comment":
            await callback.message.answer("Введите новый комментарий владельца:")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_COMMENT)
        elif action == "security_comment":
            await callback.message.answer("Введите новый комментарий для СБ:")
            await state.set_state(TemporaryPassStates.AWAIT_EDIT_SECURITY_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление марки машины
@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_CAR_BRAND)
async def update_temp_car_brand(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.car_brand = message.text
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление номера машины
@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_CAR_NUMBER)
async def update_temp_car_number(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.car_number = message.text.upper().strip()
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление типа груза
@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_CARGO_TYPE)
async def update_temp_cargo_type(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.cargo_type = message.text
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_DESTINATION)
async def update_temp_purpose(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.destination = message.text
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление цели визита
# @router.message(F.text, TemporaryPassStates.AWAIT_EDIT_PURPOSE)
# async def update_temp_purpose(message: Message, state: FSMContext):
#     try:
#         data = await state.get_data()
#         pass_id = data.get('current_temp_pass_id')
#
#         async with AsyncSessionLocal() as session:
#             pass_request = await session.get(TemporaryPass, pass_id)
#             pass_request.purpose = message.text
#             await session.commit()
#             await update_temp_pass_view(message, pass_request, session)
#         await state.set_state(TemporaryPassStates.EDITING_PASS)
#     except Exception as e:
#         await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
#         await asyncio.sleep(0.05)


# Обновление даты визита
@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_VISIT_DATE)
async def update_temp_visit_date(message: Message, state: FSMContext):
    try:
        user_input = message.text.strip()
        visit_date = parse_date(user_input)
        now = datetime.datetime.now().date()

        if not visit_date:
            await message.answer("❌ Неверный формат даты! Введите в формате ДД.ММ, ДД.ММ.ГГГГ или например '5 июня'")
            return

        if visit_date < now:
            await message.answer("Дата не может быть меньше текущей даты. Введите снова:")
            return

        max_date = now + datetime.timedelta(days=31)
        if visit_date > max_date:
            await message.answer("Пропуск нельзя заказать на месяц вперед. Введите снова:")
            return
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.visit_date = visit_date
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление комментария владельца
@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_COMMENT)
async def update_temp_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.owner_comment = message.text
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление комментария для СБ
@router.message(F.text, TemporaryPassStates.AWAIT_EDIT_SECURITY_COMMENT)
async def update_temp_security_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_temp_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(TemporaryPass, pass_id)
            pass_request.security_comment = message.text
            await session.commit()
            await update_temp_pass_view(message, pass_request, session)
        await state.set_state(TemporaryPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


async def update_temp_pass_view(message: Message, pass_request, session):
    owner_info = await get_pass_owner_info(session, pass_request)
    if pass_request.purpose in ['6', '13', '29']:
        value = f'{int(pass_request.purpose) + 1} дней\n'
    else:
        value = '2 дня\n'
    text = (
        f"{owner_info}\n"
        f"Тип ТС: {'Легковой' if pass_request.vehicle_type == 'car' else 'Грузовой'}\n"
        f"Номер: {pass_request.car_number}\n"
        f"Марка: {pass_request.car_brand}\n"
        f"Тип груза: {pass_request.cargo_type}\n"
        f"Пункт назначения: {pass_request.destination}\n"
        # f"Цель визита: {pass_request.purpose}\n"
        f"Дата визита: {pass_request.visit_date.strftime('%d.%m.%Y')}\n"
        f"Действие пропуска: {value}"
        f"Комментарий владельца: {pass_request.owner_comment or 'нет'}\n"
        f"Комментарий для СБ: {pass_request.security_comment or 'нет'}"
    )
    await message.answer(text, reply_markup=get_temp_edit_pass_keyboard())


@router.message(Command("delete_temporary"), IsAdminOrManager())
async def delete_old_temporary_passes(message: Message):
    if message.from_user.id != RAZRAB:
        return
    """Удаление временных пропусков старше 30 дней"""
    try:
        cutoff_date = datetime.datetime.now().date() - datetime.timedelta(days=30)

        async with AsyncSessionLocal() as session:
            # Удаляем временные пропуска
            result = await session.execute(
                delete(TemporaryPass).where(TemporaryPass.created_at <= cutoff_date)
            )
            deleted_count = result.rowcount

            await session.commit()

        await message.answer(
            f"✅ Удалено {deleted_count} временных пропусков за период до {cutoff_date.strftime('%d.%m.%Y')}",
            reply_markup=admin_reply_keyboard
        )

    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await message.answer("❌ Произошла ошибка при удалении пропусков")