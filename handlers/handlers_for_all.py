import asyncio
from aiogram import Router, F
from aiogram.filters import CommandStart, ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.types import Message, ContentType, CallbackQuery, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from datetime import datetime

from bot import bot
from config import RAZRAB
from db.util import add_user_to_db, get_active_admins_and_managers_tg_ids
from db.models import (
    AsyncSessionLocal,
    Manager,
    Security,
    Resident,
    Contractor,
    RegistrationRequest,
    ContractorRegistrationRequest
)
from db.util import update_user_blocked, update_user_unblocked
from handlers.handlers_admin_user_management import is_valid_phone, admin_reply_keyboard
from handlers.handlers_security import security_reply_keyboard

router = Router()


class UserRegistration(StatesGroup):
    INPUT_FIO_CONTRACTOR = State()
    INPUT_COMPANY = State()
    INPUT_POSITION = State()
    INPUT_PHONE = State()
    INPUT_FIO = State()
    INPUT_PLOT = State()
    INPUT_PHOTO = State()
    INPUT_FIO_SECURITY_MANAGER = State()


async def _handle_exception(user_id, error):
    await bot.send_message(RAZRAB, f'{user_id} - {error}')
    await asyncio.sleep(0.05)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated):
    await update_user_blocked(event.from_user.id)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated):
    await update_user_unblocked(event.from_user.id)


async def _get_existing_request(model, tg_id):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(model)
            .filter(model.tg_id == tg_id)
            .order_by(model.created_at.desc())
        )
        return result.scalars().first()


async def check_phone_in_tables(phone: str):
    async with AsyncSessionLocal() as session:
        for model, user_type in [
            (Manager, 'manager'),
            (Security, 'security'),
            (Resident, 'resident'),
            (Contractor, 'contractor')
        ]:
            result = await session.execute(select(model).filter(model.phone == phone))
            if user := result.scalars().first():
                return (user_type, user)
    return (None, None)


async def update_user_data(user_type, user_db_id, tg_user, fio):
    async with AsyncSessionLocal() as session:
        # Загружаем объект в текущей сессии
        if user_type == 'manager':
            user_db = await session.get(Manager, user_db_id)
        else:  # security
            user_db = await session.get(Security, user_db_id)

        if not user_db:
            return

        user_db.tg_id = tg_user.id
        user_db.username = tg_user.username
        user_db.first_name = tg_user.first_name
        user_db.last_name = tg_user.last_name
        user_db.time_registration = datetime.now()
        user_db.status = True
        user_db.fio = fio

        session.add(user_db)
        await session.commit()

        role_name = "менеджер" if user_type == 'manager' else "сотрудник СБ"
        tg_ids = await get_active_admins_and_managers_tg_ids()

        for tg_id in tg_ids:
            await bot.send_message(tg_id, f"Зарегистрирован новый {role_name}: {fio}")
            await asyncio.sleep(0.05)


@router.message(CommandStart())
async def process_start_user(message: Message, state: FSMContext):
    try:
        await add_user_to_db(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
            datetime.now()
        )

        resident_request = await _get_existing_request(RegistrationRequest, message.from_user.id)
        contractor_request = await _get_existing_request(ContractorRegistrationRequest, message.from_user.id)
        request = resident_request or contractor_request

        if request:
            if request.status == 'pending':
                await message.answer("⏳ Ваша заявка находится в обработке")
            elif request.status == 'rejected':
                text = f"❌ Ваша заявка отклонена. Причина: {request.admin_comment}\n\n"
                await message.answer(text + "Введите номер телефона для повторной регистрации:")
                await state.set_state(UserRegistration.INPUT_PHONE)
            elif request.status == 'approved':
                await message.answer("✅ Ваша заявка одобрена! Добро пожаловать!")
            return

        await message.answer("Введите номер телефона в формате 8XXXXXXXXXX:")
        await state.set_state(UserRegistration.INPUT_PHONE)
    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_PHONE)
async def process_phone_input(message: Message, state: FSMContext):
    try:
        phone = message.text
        if not is_valid_phone(phone):
            await message.answer('Телефон должен быть в формате 8XXXXXXXXXX.\nПопробуйте ввести еще раз!')
            return

        user_type, user_db = await check_phone_in_tables(phone)
        print(user_type, user_db)
        data = {'phone': phone}

        if user_type in ['manager', 'security']:
            data.update(user_type=user_type, user_db_id=user_db.id)
            await state.set_data(data)
            await message.answer("Введите ваше ФИО:")
            await state.set_state(UserRegistration.INPUT_FIO_SECURITY_MANAGER)
            return

        async def _check_existing(model, status_field):
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(model).filter(
                        getattr(model, status_field) == user_db.id,
                        model.status.in_(['pending', 'rejected'])
                    )
                )
                return result.scalars().first()

        if user_type == 'resident':
            if existing_request := await _check_existing(RegistrationRequest, 'resident_id'):
                await state.clear()
                if existing_request.status == 'pending':
                    await message.answer("Ваша заявка находится в обработке")
                    return
            data['resident_id'] = user_db.id
            if user_db.fio:
                next_state = UserRegistration.INPUT_PLOT
                prompt = "Введите номер участка:"
            else:
                next_state = UserRegistration.INPUT_FIO
                prompt = "Введите ФИО:"

        elif user_type == 'contractor':
            if existing_request := await _check_existing(ContractorRegistrationRequest, 'contractor_id'):
                await state.clear()
                if existing_request.status == 'pending':
                    await message.answer("Ваша заявка находится в обработке")
                    return
            data['contractor_id'] = user_db.id
            next_state = UserRegistration.INPUT_FIO_CONTRACTOR
            prompt = "Введите ФИО:"

        else:
            await message.answer("Номер не найден в системе. Введите телефон еще раз.")
            return

        await state.set_data(data)
        await message.answer(prompt)
        await state.set_state(next_state)

    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_FIO)
async def process_fio_input(message: Message, state: FSMContext):
    try:
        await state.update_data(fio=message.text)
        await message.answer("Введите номер участка:")
        await state.set_state(UserRegistration.INPUT_PLOT)
    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_PLOT)
async def process_plot_input(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        plot_number = message.text

        async with AsyncSessionLocal() as session:
            new_request = RegistrationRequest(
                resident_id=data['resident_id'],
                fio=data['fio'],
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                plot_number=plot_number,
            )
            session.add(new_request)
            await session.commit()

        await message.answer("Заявка отправлена на модерацию")
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            await bot.send_message(
                tg_id,
                text='Поступила заявка на регистрацию резидента (Регистрация > Регистрация резидентов',
                reply_markup=admin_reply_keyboard
            )
            await asyncio.sleep(0.05)
        await state.clear()
    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_FIO_CONTRACTOR)
async def process_contractor_fio(message: Message, state: FSMContext):
    try:
        await state.update_data(fio=message.text)
        await message.answer("Введите название компании:")
        await state.set_state(UserRegistration.INPUT_COMPANY)
    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_COMPANY)
async def process_company(message: Message, state: FSMContext):
    try:
        await state.update_data(company=message.text)
        await message.answer("Введите вашу должность:")
        await state.set_state(UserRegistration.INPUT_POSITION)
    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_POSITION)
async def process_position(message: Message, state: FSMContext):
    try:
        await state.update_data(position=message.text)
        data = await state.get_data()

        async with AsyncSessionLocal() as session:
            new_request = ContractorRegistrationRequest(
                contractor_id=data['contractor_id'],
                fio=data['fio'],
                company=data['company'],
                position=data['position'],
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
            session.add(new_request)
            await session.commit()

        await message.answer("Заявка отправлена на модерацию!")
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            await bot.send_message(
                tg_id,
                text='Поступила заявка на регистрацию подрядчика (Регистрация > Регистрация подрядчика',
                reply_markup=admin_reply_keyboard
            )
            await asyncio.sleep(0.05)
        await state.clear()
    except Exception as e:
        await _handle_exception(message.from_user.id, e)


@router.callback_query(F.data == "restart")
async def restart_application(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите номер телефона:")
        await state.set_state(UserRegistration.INPUT_PHONE)
    except Exception as e:
        await _handle_exception(callback.from_user.id, e)


@router.message(F.text, UserRegistration.INPUT_FIO_SECURITY_MANAGER)
async def process_fio_security_manager(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        fio = message.text
        user_type = data['user_type']
        user_db_id = data['user_db_id']

        await update_user_data(user_type, user_db_id, message.from_user, fio)

        reply_text = {
            'manager': "Регистрация менеджера завершена! Добро пожаловать!",
            'security': "Регистрация сотрудника СБ завершена! Добро пожаловать!"
        }[user_type] + ' Для продолжения работы нажмите кнопку Главное меню!'

        keyboard = admin_reply_keyboard if user_type == 'manager' else security_reply_keyboard
        await message.answer(reply_text, reply_markup=keyboard)

        await state.clear()
    except Exception as e:
        await _handle_exception(message.from_user.id, e)
