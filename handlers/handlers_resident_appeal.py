import asyncio
from typing import Union

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func

from bot import bot
from config import PAGE_SIZE, RAZRAB
from db.models import Resident, AsyncSessionLocal, Appeal
from db.util import get_active_admins_and_managers_tg_ids
from filters import IsResident
from handlers.handlers_admin_user_management import admin_reply_keyboard

router = Router()
router.message.filter(IsResident())  # Применяем фильтр резидентства ко всем хендлерам сообщений
router.callback_query.filter(IsResident())  # Применяем фильтр резидентства ко всем хендлерам колбеков


# Классы состояний для обращений
class AppealStates(StatesGroup):
    INPUT_REQUEST_TEXT = State()


class AppealViewStates(StatesGroup):
    VIEWING_PENDING = State()
    VIEWING_CLOSED = State()


# Меню обращений
@router.callback_query(F.data == "appeals_menu")
async def appeals_menu(callback: CallbackQuery):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подать обращение", callback_data="create_appeal")],
            [InlineKeyboardButton(text="Обращения в ожидании", callback_data="pending_appeals")],
            [InlineKeyboardButton(text="Обращения закрытые", callback_data="closed_appeals")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        await callback.message.answer("Управление обращениями в УК", reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Начало создания обращения
@router.callback_query(F.data == "create_appeal")
async def start_appeal_creation(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите текст вашего обращения:")
        await state.set_state(AppealStates.INPUT_REQUEST_TEXT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Сохранение обращения
@router.message(F.text, AppealStates.INPUT_REQUEST_TEXT)
async def save_appeal(message: Message, state: FSMContext):
    try:
        async with AsyncSessionLocal() as session:
            # Получаем текущего резидента
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            if not resident:
                await message.answer("❌ Ошибка: резидент не найден")
                await state.clear()
                return

            # Создаем обращение
            new_appeal = Appeal(
                request_text=message.text,
                resident_id=resident.id,
                status=False  # Ожидание ответа
            )

            session.add(new_appeal)
            await session.commit()

        await message.answer("✅ Ваше обращение успешно отправлено в УК!")
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            try:
                await bot.send_message(
                    tg_id,
                    text=f'Поступило обращение от резидента {resident.fio}.\n(Обращения к УК > Обращения в ожидании)',
                    reply_markup=admin_reply_keyboard
                )
                await asyncio.sleep(0.05)
            except:
                pass
        await state.clear()

        # Возвращаемся в меню обращений
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подать обращение", callback_data="create_appeal")],
            [InlineKeyboardButton(text="Обращения в ожидании", callback_data="pending_appeals")],
            [InlineKeyboardButton(text="Обращения закрытые", callback_data="closed_appeals")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        await message.answer("Управление обращениями в УК", reply_markup=keyboard)

    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Показать обращения в ожидании
@router.callback_query(F.data == "pending_appeals")
async def show_pending_appeals(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(AppealViewStates.VIEWING_PENDING)
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
            # Получаем текущего резидента
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            if not resident:
                if isinstance(message, CallbackQuery):
                    await message.message.answer("❌ Резидент не найден")
                else:
                    await message.answer("❌ Резидент не найден")
                return

            # Получаем общее количество обращений
            total_count = await session.scalar(
                select(func.count(Appeal.id))
                .where(
                    Appeal.resident_id == resident.id,
                    Appeal.status == status
                )
            )

            # Получаем обращения для текущей страницы
            result = await session.execute(
                select(Appeal)
                .where(
                    Appeal.resident_id == resident.id,
                    Appeal.status == status
                )
                .order_by(Appeal.created_at.desc())
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            appeals = result.scalars().all()

        if not appeals:
            text = "У вас нет обращений в этом разделе"
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
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="appeals_menu")]
        )

        status_text = "в ожидании" if not status else "закрытые"
        text = f"Ваши обращения ({status_text}):"

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
async def view_appeal_details(callback: CallbackQuery):
    try:
        appeal_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            appeal = await session.get(Appeal, appeal_id)
            if not appeal:
                await callback.answer("Обращение не найдено")
                return

            # Формируем текст в зависимости от статуса
            if appeal.status:  # Закрытое обращение
                text = (
                    f"<b>Обращение #{appeal.id}</b>\n\n"
                    f"<b>Текст обращения:</b>\n{appeal.request_text}\n\n"
                    f"<b>Дата обращения:</b>\n{appeal.created_at.strftime('%d.%m.%Y')}\n\n"
                    f"<b>Ответ от УК:</b>\n{appeal.response_text}\n\n"
                    f"<b>Дата ответа:</b>\n{appeal.responsed_at.strftime('%d.%m.%Y')}"
                )
            else:  # Ожидающее обращение
                text = (
                    f"<b>Обращение #{appeal.id}</b>\n\n"
                    f"<b>Текст обращения:</b>\n{appeal.request_text}\n\n"
                    f"<b>Дата обращения:</b>\n{appeal.created_at.strftime('%d.%m.%Y')}\n\n"
                    f"<i>Статус: в обработке УК</i>"
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