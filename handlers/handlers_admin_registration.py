import asyncio
import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from bot import bot
from config import RAZRAB
from db.models import Resident, Contractor, RegistrationRequest, \
    ContractorRegistrationRequest, AsyncSessionLocal, ResidentContractorRequest, ContractorContractorRequest
from filters import IsAdminOrManager
from handlers.handlers_admin_user_management import admin_reply_keyboard

router = Router()
router.message.filter(IsAdminOrManager())
router.callback_query.filter(IsAdminOrManager())


class AddUserStates(StatesGroup):
    WAITING_PHONE = State()
    CHOOSE_TYPE = State()


class RegistrationRequestStates(StatesGroup):
    AWAIT_REJECT_RESIDENT_COMMENT = State()
    AWAIT_REJECT_SUBCONTRACTOR_COMMENT = State()
    AWAIT_EDIT_COMPANY = State()  # Добавлено
    AWAIT_EDIT_POSITION = State()  # Добавлено
    AWAIT_EDIT_CONTRACTOR_FIO = State()
    EDITING_CONTRACTOR_REQUEST = State()
    VIEWING_CONTRACTOR_REQUEST = State()
    AWAIT_REJECT_CONTRACTOR_COMMENT = State()
    VIEWING_REQUEST = State()
    EDITING_REQUEST = State()
    AWAIT_EDIT_FIO = State()
    AWAIT_EDIT_PLOT = State()
    AWAIT_EDIT_PHOTO = State()
    AWAIT_REJECT_COMMENT = State()


def edit_keyboard_contractor():
    return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ФИО", callback_data="edit_contractorfio"),
             InlineKeyboardButton(text="Компания", callback_data="edit_contractorcompany")],
            [InlineKeyboardButton(text="Должность", callback_data="edit_contractorposition")],
            [InlineKeyboardButton(text="✅ Готово", callback_data="edit_finishcontractor")]
        ])


def get_registration_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Регистрация резидентов", callback_data="registration_requests")],
        [InlineKeyboardButton(text="Регистрация подрядчиков", callback_data="contractor_requests")],
        [InlineKeyboardButton(text="Заявки подрядчиков от резидентов", callback_data="resident_contractor_requests")],
        [InlineKeyboardButton(text="Заявки субподрядчиков от подрядчиков", callback_data="contractor_contractor_requests")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])


def edit_keyboard_resident():
    return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="ФИО", callback_data="edit_fio"),
             InlineKeyboardButton(text="Номер участка", callback_data="edit_plot")],
            [InlineKeyboardButton(text="✅ Готово", callback_data="edit_finish")]
        ])


@router.callback_query(F.data == "registration_menu")
async def show_registration_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчик кнопки "Заявки на регистрацию"
@router.callback_query(F.data == "registration_requests")
async def show_pending_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RegistrationRequest)
                .filter(RegistrationRequest.status == 'pending')
            )
            requests = result.scalars().all()

            if not requests:
                await callback.answer("Нет заявок в ожидании")
                return

            buttons = [
                [InlineKeyboardButton(
                    text=f"{req.fio}",
                    callback_data=f"view_request_{req.id}"
                )]
                for req in requests
            ]

            await callback.message.edit_text(
                "Заявки на регистрацию:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчик для заявок подрядчиков
@router.callback_query(F.data == "contractor_requests")
async def show_contractor_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ContractorRegistrationRequest)
                .filter(ContractorRegistrationRequest.status == 'pending')
            )
            requests = result.scalars().all()

            if not requests:
                await callback.answer("Нет заявок подрядчиков")
                return

            buttons = [
                [InlineKeyboardButton(
                    text=f"{req.company}_{req.position}",
                    callback_data=f"view_cont_request_{req.id}"
                )] for req in requests
            ]

            await callback.message.edit_text(
                "Заявки подрядчиков:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчик выбора заявки
@router.callback_query(F.data.startswith("view_request_"))
async def view_request_details(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)

            await state.update_data(current_request_id=request_id)

            # Формируем сообщение с фото и данными
            text = (
                f"ФИО: {request.fio}\n"
                f"Участок: {request.plot_number}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )

            # Кнопки действий
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_requests")]
            ])

            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Просмотр заявки подрядчика
@router.callback_query(F.data.startswith("view_cont_request_"))
async def view_contractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])
        await state.update_data(current_contractor_request_id=request_id)

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {request.company}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_contractor_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_contractor_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_contractor_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="contractor_requests")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки
@router.callback_query(F.data == "approve_request")
async def approve_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            resident = await session.get(Resident, request.resident_id)

            # Обновляем данные резидента
            resident.fio = request.fio
            resident.plot_number = request.plot_number
            resident.photo_id = request.photo_id
            resident.tg_id = request.tg_id
            resident.username = request.username
            resident.time_registration = datetime.datetime.now()
            resident.status = True

            request.status = 'approved'
            await session.commit()

            # Отправляем уведомление пользователю
            await bot.send_message(
                chat_id=request.tg_id,
                text="🎉 Поздравляем с успешной регистрацией в качестве резидента! Для управления нажмите кнопку Главное меню.",
                reply_markup=admin_reply_keyboard
            )

            await callback.message.answer(text="✅ Заявка одобрена")
            await callback.message.answer(
                text="Меню регистрации:",
                reply_markup=get_registration_menu()
            )
            await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки подрядчика
@router.callback_query(F.data == "approve_contractor_request")
async def approve_contractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            contractor = await session.get(Contractor, request.contractor_id)

            contractor.fio = request.fio
            contractor.company = request.company
            contractor.position = request.position
            contractor.affiliation = request.affiliation
            contractor.tg_id = request.tg_id
            contractor.username = request.username
            contractor.status = True
            contractor.time_registration = datetime.datetime.now()

            request.status = 'approved'
            await session.commit()

            await bot.send_message(
                request.tg_id,
                "🎉 Поздравляем с успешной регистрацией в качестве подрядчика! Для управления нажмите кнопку Главное меню.",
                reply_markup=admin_reply_keyboard
            )

        await callback.message.edit_text("✅ Заявка одобрена")
        await callback.message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Начало редактирования
@router.callback_query(F.data == "edit_request")
async def start_editing(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=edit_keyboard_resident())
        await state.set_state(RegistrationRequestStates.EDITING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Начало редактирования
@router.callback_query(F.data == "edit_contractor_request")
async def start_contractor_editing(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=edit_keyboard_contractor())
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "edit_finish", RegistrationRequestStates.EDITING_REQUEST)
async def finish_editing(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)

            # Формируем обновленное сообщение
            text = (
                f"ФИО: {request.fio}\n"
                f"Участок: {request.plot_number}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )

            # Создаем клавиатуру с основными кнопками
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="requests")]
            ])


            # Отправляем новое сообщение с актуальными данными
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard
            )

        await state.set_state(RegistrationRequestStates.VIEWING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "edit_finishcontractor", RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
async def finish_editing(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)

            # Формируем обновленное сообщение
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {request.company}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            # Создаем клавиатуру с основными кнопками
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_contractor_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_contractor_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_contractor_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="contractor_requests")]
            ])

            # Отправляем новое сообщение с актуальными данными
            await callback.message.edit_text(
                text=text,
                reply_markup=keyboard
            )

        await state.set_state(RegistrationRequestStates.VIEWING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("edit_"), RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
async def handle_edit_actions(callback: CallbackQuery, state: FSMContext):
    try:
        action = callback.data.split("_")[-1]

        if action == "contractorfio":
            await callback.message.answer("Введите новое ФИО:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_CONTRACTOR_FIO)
        elif action == "contractorcompany":  # Добавлено
            await callback.message.answer("Введите новое название компании:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_COMPANY)
        elif action == "contractorposition":  # Добавлено
            await callback.message.answer("Введите новую должность:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_POSITION)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("edit_"), RegistrationRequestStates.EDITING_REQUEST)
async def handle_edit_actions(callback: CallbackQuery, state: FSMContext):
    try:
        action = callback.data.split("_")[-1]

        if action == "fio":
            await callback.message.answer("Введите новое ФИО:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_FIO)
        elif action == "plot":
            await callback.message.answer("Введите новый номер участка:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_PLOT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление ФИО
@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_FIO)
async def update_fio(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            request.fio = message.text
            await session.commit()
            # Формируем сообщение с фото и данными
            text = (
                f"ФИО: {message.text}\n"
                f"Участок: {request.plot_number}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )
            await message.answer(
                text=text,
                reply_markup=edit_keyboard_resident()
            )
        await state.set_state(RegistrationRequestStates.EDITING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_CONTRACTOR_FIO)
async def update_fio(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.fio = message.text
            await session.commit()
            # Формируем сообщение с фото и данными
            text = (
                f"ФИО: {message.text}\n"
                f"Компания: {request.company}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            await bot.send_message(
                chat_id=message.from_user.id,
                text=text,
                reply_markup=edit_keyboard_contractor()
            )
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_COMPANY)
async def update_company(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.company = message.text
            await session.commit()
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {message.text}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            await bot.send_message(
                chat_id=message.from_user.id,
                text=text,
                reply_markup=edit_keyboard_contractor()
            )
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_POSITION)
async def update_position(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.position = message.text
            await session.commit()
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {request.company}\n"
                f"Должность: {message.text}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            await bot.send_message(
                chat_id=message.from_user.id,
                text=text,
                reply_markup=edit_keyboard_contractor()
            )
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление Номер участка
@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_PLOT)
async def update_fio(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            request.plot_number = message.text
            await session.commit()
            # Формируем сообщение с фото и данными
            text = (
                f"ФИО: {request.fio}\n"
                f"Участок: {message.text}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )

            await message.answer(
                text=text,
                reply_markup=edit_keyboard_resident()
            )
        await state.set_state(RegistrationRequestStates.EDITING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Отклонение заявки
@router.callback_query(F.data == "reject_request")
async def start_reject(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите комментарий для отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_CONTRACTOR_COMMENT)
async def reject_request(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

            # Уведомление пользователя
            await bot.send_message(
                chat_id=request.tg_id,
                text=f"❌ Ваша заявка отклонена.\nПричина: {message.text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="Заполнить заново", callback_data="restart")]]))

        await message.answer("Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Отклонение заявки
@router.callback_query(F.data == "reject_contractor_request")
async def start_reject(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите комментарий для отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_CONTRACTOR_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_COMMENT)
async def reject_request(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

            # Уведомление пользователя
            await bot.send_message(
                chat_id=request.tg_id,
                text=f"❌ Ваша заявка отклонена.\nПричина: {message.text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="Заполнить заново", callback_data="restart")]]))

        await message.answer("Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "resident_contractor_requests")
async def show_resident_contractor_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ResidentContractorRequest)
                .filter(ResidentContractorRequest.status == 'pending')
            )
            requests = result.scalars().all()
            buttons = []
            for req in requests:
                resident = await session.get(Resident, req.resident_id)

                buttons.append(
                    [InlineKeyboardButton(
                        text=f"{resident.fio}",
                        callback_data=f"view_rescont_request_{req.id}"
                    )]
                )

            await callback.message.edit_text(
                "Заявки на подрядчиков от резидентов:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_rescont_request_"))
async def view_resident_request(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])
        await state.update_data(current_resident_request_id=request_id)

        async with AsyncSessionLocal() as session:
            request = await session.get(ResidentContractorRequest, request_id)
            resident = await session.get(Resident, request.resident_id)

            text = (
                f"📱 Телефон: {request.phone}\n"
                f"🏗 Виды работ: {request.work_types}\n"
                f"👤 Резидент: {resident.fio} (ID: {resident.id})"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_rescont_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_rescont_request")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки
@router.callback_query(F.data == "approve_rescont_request")
async def approve_resident_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_resident_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ResidentContractorRequest, request_id)
            resident = await session.get(Resident, request.resident_id)

            # Создаем запись подрядчика
            new_contractor = Contractor(
                phone=request.phone,
                work_types=request.work_types,
                affiliation=f"{resident.id}_{resident.fio}",
                status=False  # Требует завершения регистрации
            )
            session.add(new_contractor)
            await session.commit()

            # Обновляем статус заявки
            request.status = 'approved'
            await session.commit()

        await bot.send_message(
            chat_id=resident.tg_id,
            text=f"🎉 Заявка на регистрацию Вашего подрядчика ({request.phone}) одобрена! Для завершения регистрации подрядчика, перешлите "
                 "подрядчику ссылку на бот, подрядчик должен ввести номер телефона, который вы указали для его регистрации.",
            reply_markup=admin_reply_keyboard
        )
        await callback.message.edit_text("✅ Заявка одобрена!")
        await callback.message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "reject_rescont_request")
async def reject_resident_request(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите причину отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_RESIDENT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_RESIDENT_COMMENT)
async def process_reject_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_resident_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ResidentContractorRequest, request_id)
            resident = await session.get(Resident, request.resident_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

        await bot.send_message(
            chat_id=resident.tg_id,
            text=f"❌ Заявка на регистрацию Вашего подрядчика ({request.phone}) отклонена!\nПричина: {message.text}",
            reply_markup=admin_reply_keyboard
        )
        await message.edit_text("❌ Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "contractor_contractor_requests")
async def show_subcontractor_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ContractorContractorRequest)
                .filter(ContractorContractorRequest.status == 'pending')
            )
            requests = result.scalars().all()
            buttons = []
            for req in requests:
                contractor = await session.get(Contractor, req.contractor_id)

                buttons.append(
                    [InlineKeyboardButton(
                        text=f"{contractor.company}_{contractor.position}",
                        callback_data=f"view_subcontractor_request_{req.id}"
                    )]
                )

            await callback.message.edit_text(
                "Заявки на субподрядчиков от подрядчиков:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_subcontractor_request_"))
async def view_subcontractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])
        await state.update_data(current_subcontractor_request_id=request_id)

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorContractorRequest, request_id)
            contractor = await session.get(Contractor, request.contractor_id)

            text = (
                f"📱 Телефон: {request.phone}\n"
                f"🏗 Виды работ: {request.work_types}\n"
                f"👤 Подрядчик: {contractor.company}_{contractor.position}_{contractor.fio}"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_subcontractor_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_subcontractor_request")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки
@router.callback_query(F.data == "approve_subcontractor_request")
async def approve_subcontractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_subcontractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorContractorRequest, request_id)
            contractor = await session.get(Contractor, request.contractor_id)

            # Создаем запись подрядчика
            new_contractor = Contractor(
                phone=request.phone,
                work_types=request.work_types,
                affiliation=f"{contractor.id}_{contractor.company}_{contractor.position}_{contractor.fio}",
                status=False  # Требует завершения регистрации
            )
            session.add(new_contractor)
            await session.commit()

            # Обновляем статус заявки
            request.status = 'approved'
            await session.commit()

        await bot.send_message(
            chat_id=contractor.tg_id,
            text=f"🎉 Заявка на регистрацию Вашего субподрядчика ({request.phone}) одобрена! Для завершения регистрации субподрядчика, перешлите "
                 "субподрядчику ссылку на бот, субподрядчик должен ввести номер телефона, который вы указали для его регистрации.",
            reply_markup=admin_reply_keyboard
        )
        await callback.message.edit_text("✅ Заявка одобрена!")
        await callback.message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "reject_subcontractor_request")
async def reject_subcontractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите причину отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_SUBCONTRACTOR_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_SUBCONTRACTOR_COMMENT)
async def process_reject_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_subcontractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorContractorRequest, request_id)
            contractor = await session.get(Contractor, request.contractor_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

        await bot.send_message(
            chat_id=contractor.tg_id,
            text=f"❌ Заявка на регистрацию Вашего субподрядчика ({request.phone}) отклонена!\nПричина: {message.text}",
            reply_markup=admin_reply_keyboard
        )
        await message.answer("❌ Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)
