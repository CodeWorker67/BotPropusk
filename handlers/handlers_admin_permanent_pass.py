import asyncio
import logging
import datetime
from typing import Union

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State, default_state
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func

from bot import bot
from db.models import AsyncSessionLocal, Resident, PermanentPass
from config import PAGE_SIZE, RAZRAB
from db.util import get_active_admins_managers_sb_tg_ids
from filters import IsAdminOrManager
from handlers.handlers_admin_user_management import admin_reply_keyboard

router = Router()
router.message.filter(IsAdminOrManager())
router.callback_query.filter(IsAdminOrManager())


class PermanentPassStates(StatesGroup):
    AWAIT_EDIT_DESTINATION = State()
    AWAIT_REJECT_COMMENT = State()
    EDITING_PASS = State()
    AWAIT_EDIT_CAR_BRAND = State()
    AWAIT_EDIT_CAR_MODEL = State()
    AWAIT_EDIT_CAR_NUMBER = State()
    AWAIT_EDIT_CAR_OWNER = State()
    AWAIT_EDIT_SECURITY_COMMENT = State()


def get_passes_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Постоянные пропуска", callback_data="permanent_passes_menu")],
        [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_passes_menu")],
        [InlineKeyboardButton(text="Выписать временный пропуск", callback_data="issue_self_pass")],
        [InlineKeyboardButton(text="Выписать постоянный пропуск", callback_data="issue_permanent_self_pass")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])


def get_permanent_passes_management():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На подтверждении", callback_data="pending_permanent_passes")],
        [InlineKeyboardButton(text="Подтвержденные", callback_data="approved_permanent_passes")],
        [InlineKeyboardButton(text="Отклоненные", callback_data="rejected_permanent_passes")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_passes")]
    ])


@router.callback_query(F.data == "passes_menu")
async def passes_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "Пропуска:",
            reply_markup=get_passes_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "permanent_passes_menu")
async def permanent_passes_menu(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        await callback.message.edit_text(
            "Управление постоянными пропусками:",
            reply_markup=get_permanent_passes_management()
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


@router.callback_query(F.data == "pending_permanent_passes")
async def show_pending_passes(message: Union[Message, CallbackQuery], state: FSMContext):
    try:

        data = await state.get_data()
        current_page = data.get('pass_current_page', 0)

        async with AsyncSessionLocal() as session:
            # Получаем общее количество заявок
            total_count = await session.scalar(
                select(func.count(PermanentPass.id))
                .where(PermanentPass.status == 'pending')
            )

            # Получаем заявки для текущей страницы
            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.status == 'pending')
                .order_by(PermanentPass.created_at.desc())
                .offset(current_page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            requests = result.all()

        if not requests:
            text = "Нет пропусков на подтверждении"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for req, fio in requests:
            # Берем первые два слова из ФИО
            fio_short = ' '.join(fio.split()[:2])
            text = f"{fio_short}_{req.car_number}"
            buttons.append(
                [InlineKeyboardButton(text=text, callback_data=f"view_pass_{req.id}")]
            )

        # Добавляем кнопки пагинации
        pagination_buttons = []
        if current_page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"pass_prev_{current_page - 1}")
            )

        if (current_page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data=f"pass_next_{current_page + 1}")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="permanent_passes_menu")]
        )

        text = "Пропуска требуют подтверждения:"
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        await state.update_data(
            pass_current_page=current_page,
            pass_total_count=total_count
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("pass_prev_") | F.data.startswith("pass_next_"))
async def handle_pass_pagination(callback: CallbackQuery, state: FSMContext):
    try:
        action, page_str = callback.data.split("_")[1:3]
        page = int(page_str)
        await state.update_data(pass_current_page=page)
        await show_pending_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_pass_"))
async def view_pass_details(callback: CallbackQuery, state: FSMContext):
    try:
        pass_id = int(callback.data.split("_")[-1])
        await state.update_data(current_pass_id=pass_id)

        async with AsyncSessionLocal() as session:
            # Получаем пропуск и связанного резидента
            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            if not pass_request:
                await callback.answer("Пропуск не найден")
                return

            # Формируем текст сообщения
            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            # Формируем клавиатуру действий (добавляем кнопку Редактировать)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_pass_{pass_id}")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_pass")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_pass")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_pending_passes")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_pending_passes")
async def back_to_pending_list(callback: CallbackQuery, state: FSMContext):
    try:
        await show_pending_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("approve_pass_"))
async def approve_pass(callback: CallbackQuery, state: FSMContext):
    try:
        pass_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            # Получаем пропуск
            pass_request = await session.get(PermanentPass, pass_id)
            if not pass_request:
                await callback.answer("Пропуск не найден")
                return

            # Обновляем статус и время
            pass_request.status = 'approved'
            pass_request.time_registration = datetime.datetime.now()
            await session.commit()

            # Получаем резидента для отправки сообщения
            resident = await session.get(Resident, pass_request.resident_id)

            # Отправляем сообщение резиденту
            try:
                await bot.send_message(
                    resident.tg_id,
                    f"✅ Ваш постоянный пропуск на машину с номером {pass_request.car_number} одобрен!"
                )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение резиденту: {e}")
            tg_ids = await get_active_admins_managers_sb_tg_ids()
            for tg_id in tg_ids:
                try:
                    await bot.send_message(
                        tg_id,
                        text=f'Постоянный пропуск от резидента {resident.fio} на машину с номером {pass_request.car_number} одобрен.',
                        reply_markup=admin_reply_keyboard
                    )
                    await asyncio.sleep(0.05)
                except:
                    pass
            # Сообщение админу
            await callback.message.answer(
                "Управление постоянными пропусками:",
                reply_markup=get_permanent_passes_management()
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "reject_pass")
async def start_reject_pass(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите комментарий для резидента:")
        await state.set_state(PermanentPassStates.AWAIT_REJECT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, PermanentPassStates.AWAIT_REJECT_COMMENT)
async def process_reject_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        if not pass_id:
            await message.answer("Ошибка: ID пропуска не найден")
            await state.clear()
            return

        async with AsyncSessionLocal() as session:
            # Получаем пропуск
            pass_request = await session.get(PermanentPass, pass_id)
            if not pass_request:
                await message.answer("Пропуск не найден")
                await state.clear()
                return

            # Обновляем статус и комментарий
            pass_request.status = 'rejected'
            pass_request.time_registration = datetime.datetime.now()
            pass_request.resident_comment = message.text
            await session.commit()

            # Получаем резидента для отправки сообщения
            resident = await session.get(Resident, pass_request.resident_id)

            # Отправляем сообщение резиденту
            try:
                await bot.send_message(
                    resident.tg_id,
                    f"❌ Ваша заявка на постоянный пропуск для машины с номером {pass_request.car_number} отклонена.\n"
                    f"Причина: {message.text}"
                )
            except Exception as e:
                logging.error(f"Не удалось отправить сообщение резиденту: {e}")

            # Сообщение админу
            await message.answer("❌ Заявка отклонена")
            await message.answer(
                "Управление постоянными пропусками:",
                reply_markup=get_permanent_passes_management()
            )

        # Возвращаем админа в список pending пропусков
        await show_pending_passes(message, state)
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Клавиатура для редактирования пропуска
def get_edit_pass_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Марка", callback_data="edit_car_brand"),
            InlineKeyboardButton(text="Модель", callback_data="edit_car_model"),
        ],
        [
            InlineKeyboardButton(text="Номер", callback_data="edit_car_number"),
            InlineKeyboardButton(text="Владелец", callback_data="edit_car_owner"),
        ],
        [
            InlineKeyboardButton(text="Пункт назначения", callback_data="edit_car_destination"),
            InlineKeyboardButton(text="Коммент. для СБ", callback_data="edit_security_comment"),
        ],
        [
            InlineKeyboardButton(text="✅ Готово", callback_data="edit_finish_pass")
        ]
    ])


# Обработчик кнопки "Редактировать"
@router.callback_query(F.data == "edit_pass")
async def start_editing_pass(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=get_edit_pass_keyboard())
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "edit_finish_pass", PermanentPassStates.EDITING_PASS)
async def finish_editing_pass(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            # Получаем пропуск и связанного резидента
            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            # Формируем текст сообщения
            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            # Формируем клавиатуру действий
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_pass_{pass_id}")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_pass")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_pass")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_pending_passes")]
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard
            )

        await state.set_state(default_state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)



# Обработчики для кнопок редактирования
@router.callback_query(F.data.startswith("edit_"), PermanentPassStates.EDITING_PASS)
async def handle_edit_pass_actions(callback: CallbackQuery, state: FSMContext):
    try:
        action = callback.data.split("_")[1] + '_' + callback.data.split("_")[2]

        if action == "car_brand":
            await callback.message.answer("Введите новую марку машины:")
            await state.set_state(PermanentPassStates.AWAIT_EDIT_CAR_BRAND)
        elif action == "car_model":
            await callback.message.answer("Введите новую модель машины:")
            await state.set_state(PermanentPassStates.AWAIT_EDIT_CAR_MODEL)
        elif action == "car_number":
            await callback.message.answer("Введите новый номер машины:")
            await state.set_state(PermanentPassStates.AWAIT_EDIT_CAR_NUMBER)
        elif action == "car_owner":
            await callback.message.answer("Введите нового владельца машины:")
            await state.set_state(PermanentPassStates.AWAIT_EDIT_CAR_OWNER)
        elif action == "car_destination":
            await callback.message.answer("Введите новый номер участка:")
            await state.set_state(PermanentPassStates.AWAIT_EDIT_DESTINATION)
        elif action == "security_comment":
            await callback.message.answer("Введите новый комментарий для СБ:")
            await state.set_state(PermanentPassStates.AWAIT_EDIT_SECURITY_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление марки машины
@router.message(F.text, PermanentPassStates.AWAIT_EDIT_CAR_BRAND)
async def update_car_brand(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(PermanentPass, pass_id)
            pass_request.car_brand = message.text
            await session.commit()

            # Получаем обновленные данные
            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            # Формируем текст сообщения
            text = (
                f"ФИО: {fio}\n"
                f"Марка: {message.text}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            # Отправляем обновленное сообщение
            await message.answer(
                text,
                reply_markup=get_edit_pass_keyboard()
            )
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление модели машины (аналогично для остальных полей)
@router.message(F.text, PermanentPassStates.AWAIT_EDIT_CAR_MODEL)
async def update_car_model(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(PermanentPass, pass_id)
            pass_request.car_model = message.text
            await session.commit()

            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {message.text}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            await message.answer(
                text,
                reply_markup=get_edit_pass_keyboard()
            )
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление номера машины
@router.message(F.text, PermanentPassStates.AWAIT_EDIT_CAR_NUMBER)
async def update_car_number(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(PermanentPass, pass_id)
            pass_request.car_number = message.text.upper().strip()
            await session.commit()

            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {message.text}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            await message.answer(
                text,
                reply_markup=get_edit_pass_keyboard()
            )
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление владельца машины
@router.message(F.text, PermanentPassStates.AWAIT_EDIT_CAR_OWNER)
async def update_car_owner(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(PermanentPass, pass_id)
            pass_request.car_owner = message.text
            await session.commit()

            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {message.text}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            await message.answer(
                text,
                reply_markup=get_edit_pass_keyboard()
            )
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, PermanentPassStates.AWAIT_EDIT_DESTINATION)
async def update_destination(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(PermanentPass, pass_id)
            pass_request.destination = message.text
            await session.commit()

            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {message.text}\n"
                f"Комментарий для СБ: {pass_request.security_comment}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            await message.answer(
                text,
                reply_markup=get_edit_pass_keyboard()
            )
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление комментария для СБ
@router.message(F.text, PermanentPassStates.AWAIT_EDIT_SECURITY_COMMENT)
async def update_security_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        pass_id = data.get('current_pass_id')

        async with AsyncSessionLocal() as session:
            pass_request = await session.get(PermanentPass, pass_id)
            pass_request.security_comment = message.text
            await session.commit()

            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для СБ: {message.text}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            await message.answer(
                text,
                reply_markup=get_edit_pass_keyboard()
            )
        await state.set_state(PermanentPassStates.EDITING_PASS)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "approved_permanent_passes")
async def show_approved_passes(message: Union[Message, CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('pass_current_page', 0)

        async with AsyncSessionLocal() as session:
            # Получаем общее количество заявок
            total_count = await session.scalar(
                select(func.count(PermanentPass.id))
                .where(PermanentPass.status == 'approved')
            )

            # Получаем заявки для текущей страницы
            result = await session.execute(
                select(PermanentPass)
                .where(PermanentPass.status == 'approved')
                .order_by(PermanentPass.created_at.desc())
                .offset(current_page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            requests = result.scalars()

        if not requests:
            text = "Нет подтвержденных пропусков"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for req in requests:
            if req.resident_id:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(select(Resident).where(Resident.id == req.resident_id))
                    resident = result.scalar()
                    fio_short = ' '.join(resident.fio.split()[:2])
                    text = f"{fio_short}_{req.car_number}"
            else:
                fio = req.security_comment.replace('Выписал', '')
                if 'Администратор' in fio:
                    fio_short = 'Администратор'
                else:
                    fio_short = ' '.join(fio.split()[:2])
                text = f"{fio_short}_{req.car_number}"
            buttons.append(
                [InlineKeyboardButton(text=text, callback_data=f"view_ap_pass_{req.id}")]
            )

        # Добавляем кнопки пагинации
        pagination_buttons = []
        if current_page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"ap_pass_prev_{current_page - 1}")
            )

        if (current_page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data=f"ap_pass_next_{current_page + 1}")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="permanent_passes_menu")]
        )

        text = "Подтвержденные постоянные пропуска:"
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        await state.update_data(
            pass_current_page=current_page,
            pass_total_count=total_count
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("ap_pass_prev_") | F.data.startswith("ap_pass_next_"))
async def handle_pass_pagination(callback: CallbackQuery, state: FSMContext):
    try:
        action, page_str = callback.data.split("_")[1:3]
        page = int(page_str)
        await state.update_data(pass_current_page=page)
        await show_pending_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_ap_pass_"))
async def view_pass_details(callback: CallbackQuery, state: FSMContext):
    try:
        pass_id = int(callback.data.split("_")[-1])
        await state.update_data(current_pass_id=pass_id)

        async with AsyncSessionLocal() as session:
            # Получаем пропуск и связанного резидента
            result = await session.execute(
                select(PermanentPass)
                .where(PermanentPass.id == pass_id)
            )
            pass_request = result.scalar()

        if not pass_request:
            await callback.answer("Пропуск не найден")
            return

        if pass_request.resident_id:
            async with AsyncSessionLocal() as session:
                # Получаем пропуск и связанного резидента
                result = await session.execute(
                    select(Resident)
                    .where(Resident.id == pass_request.resident_id)
                )
                resident = result.scalar()
                fio = resident.fio
        else:
            fio = pass_request.security_comment.replace('Выписал ', '')


        # Формируем текст сообщения
        text = (
            f"ФИО: {fio}\n"
            f"Марка: {pass_request.car_brand}\n"
            f"Модель: {pass_request.car_model}\n"
            f"Номер: {pass_request.car_number}\n"
            f"Владелец: {pass_request.car_owner}\n"
            f"Пункт назначения: {pass_request.destination}\n"
            f"Комментарий для СБ: {pass_request.security_comment or 'нет'}\n"
            f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"Время подтверждения: {pass_request.time_registration.strftime('%d.%m.%Y %H:%M')}"
        )

        # Формируем клавиатуру действий (добавляем кнопку Редактировать)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_approved_passes")]
        ])

        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_approved_passes")
async def back_to_pending_list(callback: CallbackQuery, state: FSMContext):
    try:
        await show_approved_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "rejected_permanent_passes")
async def show_rejected_passes(message: Union[Message, CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('pass_current_page', 0)

        async with AsyncSessionLocal() as session:
            # Получаем общее количество заявок
            total_count = await session.scalar(
                select(func.count(PermanentPass.id))
                .where(PermanentPass.status == 'rejected')
            )

            # Получаем заявки для текущей страницы
            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.status == 'rejected')
                .order_by(PermanentPass.created_at.desc())
                .offset(current_page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            requests = result.all()

        if not requests:
            text = "Нет отклоненных пропусков"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for req, fio in requests:
            # Берем первые два слова из ФИО
            fio_short = ' '.join(fio.split()[:2])
            text = f"{req.id}_{fio_short}"
            buttons.append(
                [InlineKeyboardButton(text=text, callback_data=f"view_rej_pass_{req.id}")]
            )

        # Добавляем кнопки пагинации
        pagination_buttons = []
        if current_page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data=f"rej_pass_prev_{current_page - 1}")
            )

        if (current_page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data=f"rej_pass_next_{current_page + 1}")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="permanent_passes_menu")]
        )

        text = "Отклоненные постоянные пропуска:"
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

        await state.update_data(
            pass_current_page=current_page,
            pass_total_count=total_count
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("rej_pass_prev_") | F.data.startswith("rej_pass_next_"))
async def handle_pass_pagination(callback: CallbackQuery, state: FSMContext):
    try:
        action, page_str = callback.data.split("_")[1:3]
        page = int(page_str)
        await state.update_data(pass_current_page=page)
        await show_pending_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_rej_pass_"))
async def view_pass_details(callback: CallbackQuery, state: FSMContext):
    try:
        pass_id = int(callback.data.split("_")[-1])
        await state.update_data(current_pass_id=pass_id)

        async with AsyncSessionLocal() as session:
            # Получаем пропуск и связанного резидента
            result = await session.execute(
                select(PermanentPass, Resident.fio)
                .join(Resident, Resident.id == PermanentPass.resident_id)
                .where(PermanentPass.id == pass_id)
            )
            pass_request, fio = result.first()

            if not pass_request:
                await callback.answer("Пропуск не найден")
                return

            # Формируем текст сообщения
            text = (
                f"ФИО: {fio}\n"
                f"Марка: {pass_request.car_brand}\n"
                f"Модель: {pass_request.car_model}\n"
                f"Номер: {pass_request.car_number}\n"
                f"Владелец: {pass_request.car_owner}\n"
                f"Пункт назначения: {pass_request.destination}\n"
                f"Комментарий для резидента: {pass_request.resident_comment or 'нет'}\n"
                f"Время создания: {pass_request.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                f"Время отклонения: {pass_request.time_registration.strftime('%d.%m.%Y %H:%M')}"
            )

            # Формируем клавиатуру действий (добавляем кнопку Редактировать)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_rejected_passes")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_rejected_passes")
async def back_to_rejected_list(callback: CallbackQuery, state: FSMContext):
    try:
        await show_rejected_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)
