import asyncio
import datetime
from typing import Union

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func

from bot import bot
from config import PAGE_SIZE, RAZRAB
from db.models import AsyncSessionLocal, Appeal, Resident, User
from filters import IsAdminOrManager

router = Router()
router.message.filter(IsAdminOrManager())
router.callback_query.filter(IsAdminOrManager())


class AnswerAppealStates(StatesGroup):
    INPUT_RESPONSE_TEXT = State()


class AppealViewStates(StatesGroup):
    VIEWING_ACTIVE = State()
    VIEWING_CLOSED = State()


# Меню обращений
@router.callback_query(F.data == "appeals_management")
async def appeals_management(callback: CallbackQuery):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Активные обращения", callback_data="active_appeals")],
            [InlineKeyboardButton(text="Обращения закрытые", callback_data="closed_appeals")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])
        await callback.message.edit_text("Управление обращениями в УК", reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Показать активные обращения
@router.callback_query(F.data == "active_appeals")
async def show_active_appeals(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(AppealViewStates.VIEWING_ACTIVE)
        await state.update_data(appeal_page=0, appeal_status=False)
        await show_appeals(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Показать закрытые обращения
@router.callback_query(F.data == "closed_appeals")
async def show_closed_appeals(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(AppealViewStates.VIEWING_CLOSED)
        await state.update_data(appeal_page=0, appeal_status=True)
        await show_appeals(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Функция отображения списка обращений
async def show_appeals(message: Union[Message, CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        page = data.get('appeal_page', 0)
        status = data.get('appeal_status', False)

        async with AsyncSessionLocal() as session:
            # Получаем обращения
            total_count = await session.scalar(
                select(func.count(Appeal.id))
                .where(Appeal.status == status)
            )

            # Получаем обращения для текущей страницы
            result = await session.execute(
                select(Appeal)
                .where(Appeal.status == status)
                .order_by(Appeal.created_at.desc())
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            appeals = result.scalars().all()

        if not appeals:
            text = "Нет обращений в этом разделе"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for appeal in appeals:
            btn_text = f"Обращение #{appeal.id} - {appeal.created_at.strftime('%d.%m.%Y')}"
            buttons.append(
                [InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"view_appeal_{appeal.id}"
                )]
            )

        # Кнопки пагинации
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data="appeal_prev")
            )

        if (page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data="appeal_next")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="appeals_management")]
        )

        status_text = "активные" if not status else "закрытые"
        text = f"Обращения ({status_text}):"

        if isinstance(message, CallbackQuery):
            await message.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчики пагинации
@router.callback_query(F.data == "appeal_prev", StateFilter(AppealViewStates))
async def handle_appeal_prev(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('appeal_page', 0)
        if current_page > 0:
            await state.update_data(appeal_page=current_page - 1)
            await show_appeals(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "appeal_next", StateFilter(AppealViewStates))
async def handle_appeal_next(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('appeal_page', 0)
        await state.update_data(appeal_page=current_page + 1)
        await show_appeals(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Просмотр деталей обращения
@router.callback_query(F.data.startswith("view_appeal_"))
async def view_appeal_details(callback: CallbackQuery, state: FSMContext):
    try:
        appeal_id = int(callback.data.split("_")[-1])
        await state.update_data(current_appeal_id=appeal_id)

        async with AsyncSessionLocal() as session:
            appeal = await session.get(Appeal, appeal_id)
            if not appeal:
                await callback.answer("Обращение не найдено")
                return
            resident = await session.get(Resident, appeal.resident_id)

            # Для активных обращений
            if not appeal.status:
                text = (
                    f"<b>Обращение #{appeal.id}</b>\n\n"
                    f"<b>ФИО резидента:</b>\n{resident.fio}\n\n"
                    f"<b>Текст обращения:</b>\n{appeal.request_text}\n\n"
                    f"<b>Дата обращения:</b>\n{appeal.created_at.strftime('%d.%m.%Y')}"
                )

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✏️ Ответить на обращение", callback_data="answer_appeal")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_appeals_list")]
                ])

                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

            # Для закрытых обращений
            else:
                responser = await session.get(User, appeal.responser_id)

                text = (
                    f"<b>Обращение #{appeal.id}</b>\n\n"
                    f"<b>ФИО резидента:</b>\n{resident.fio}\n\n"
                    f"<b>Текст обращения:</b>\n{appeal.request_text}\n\n"
                    f"<b>Дата обращения:</b>\n{appeal.created_at.strftime('%d.%m.%Y')}\n\n"
                    f"<b>Ответчик от УК:</b>\n{responser.username if responser else 'Неизвестно'}\n\n"
                    f"<b>Ответ от УК:</b>\n{appeal.response_text}\n\n"
                    f"<b>Дата ответа:</b>\n{appeal.responsed_at.strftime('%d.%m.%Y')}"
                )

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_appeals_list")]
                ])

                await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Возврат к списку обращений
@router.callback_query(F.data == "back_to_appeals_list")
async def back_to_appeals_list(callback: CallbackQuery, state: FSMContext):
    try:
        await show_appeals(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Начало ответа на обращение
@router.callback_query(F.data == "answer_appeal")
async def start_answer_appeal(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите текст ответа:")
        await state.set_state(AnswerAppealStates.INPUT_RESPONSE_TEXT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Сохранение ответа на обращение
@router.message(F.text, AnswerAppealStates.INPUT_RESPONSE_TEXT)
async def save_appeal_response(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        appeal_id = data['current_appeal_id']

        async with AsyncSessionLocal() as session:
            # Получаем текущего администратора (ответчика)
            result = await session.execute(
                select(User)
                .where(User.id == message.from_user.id)
            )
            responser = result.scalar()

            if not responser:
                # Создаем запись пользователя, если не существует
                responser = User(
                    id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    time_start=datetime.datetime.now()
                )
                session.add(responser)
                await session.commit()

            # Обновляем обращение
            appeal = await session.get(Appeal, appeal_id)
            appeal.response_text = message.text
            appeal.responser_id = responser.id
            appeal.responsed_at = datetime.datetime.now()
            appeal.status = True  # Закрываем обращение

            await session.commit()

        # Уведомляем резидента
        resident = await session.get(Resident, appeal.resident_id)
        await bot.send_message(
            chat_id=resident.tg_id,
            text=f"✅ По вашему обращению #{appeal_id} - {appeal.created_at.strftime('%d.%m.%Y')} получен ответ от УК (Обращения в УК > Обращения закрытые)"
        )

        await message.answer("✅ Ответ успешно сохранен и отправлен резиденту!")
        await state.clear()

        # Возвращаемся в меню обращений
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Активные обращения", callback_data="active_appeals")],
            [InlineKeyboardButton(text="Обращения закрытые", callback_data="closed_appeals")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])
        await message.answer("Управление обращениями в УК", reply_markup=keyboard)

    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)