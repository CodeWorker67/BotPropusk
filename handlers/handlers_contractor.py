import asyncio
import datetime
import random
from typing import Union

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, \
    CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from sqlalchemy import select, func

from bot import bot
from config import PAGE_SIZE, RAZRAB, PASS_TIME, MAX_CAR_PASSES, MAX_TRUCK_PASSES
from date_parser import parse_date
from db.models import Resident, AsyncSessionLocal, ResidentContractorRequest, PermanentPass, Contractor, TemporaryPass, \
    ContractorContractorRequest
from db.util import get_active_admins_and_managers_tg_ids, get_active_admins_managers_sb_tg_ids, text_warning
from filters import IsResident, IsContractor
from handlers.handlers_admin_user_management import admin_reply_keyboard, is_valid_phone

router = Router()
router.message.filter(IsContractor())  # Применяем фильтр подрядчика ко всем хендлерам сообщений
router.callback_query.filter(IsContractor())  # Применяем фильтр подрядчика ко всем хендлерам колбеков


class ContractorContractorRegistration(StatesGroup):
    INPUT_PHONE = State()
    INPUT_WORK_TYPES = State()


class TemporaryPassViewStates(StatesGroup):
    VIEWING_PENDING = State()
    VIEWING_APPROVED = State()
    VIEWING_REJECTED = State()


class TemporaryPassStates(StatesGroup):
    CHOOSE_VEHICLE_TYPE = State()
    CHOOSE_WEIGHT_CATEGORY = State()
    CHOOSE_LENGTH_CATEGORY = State()
    INPUT_CAR_NUMBER = State()
    INPUT_CAR_BRAND = State()
    INPUT_CARGO_TYPE = State()
    INPUT_DESTINATION = State()
    INPUT_PURPOSE = State()
    INPUT_VISIT_DATE = State()
    INPUT_COMMENT = State()


contractor_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Главное меню")]],
    resize_keyboard=True,
    is_persistent=True
)


@router.message(Command("start"))
async def resident_start(message: Message):
    """Обработчик команды /start для резидентов"""
    try:
        await message.answer(
            text="Добро пожаловать в личный кабинет резидента!",
            reply_markup=contractor_keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text == "Главное меню")
async def main_menu(message: Message):
    try:
        """Обработчик главного меню резидента"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Contractor)
                .where(Contractor.tg_id == message.from_user.id)
            )
            contractor = result.scalar()

            if not contractor:
                return await message.answer("❌ Профиль не найден")

            text = (
                f"ФИО: {contractor.fio}\n"
                f"Компания: {contractor.company}\n"
                f"Должность: {contractor.position}\n"
            )
            if contractor.can_add_contractor:
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Зарегистрировать субподрядчика", callback_data="register_contractor")],
                    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")]
                ])
            else:
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")]
                ])

            await message.answer(
                text=text,
                reply_markup=inline_kb
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_main_menu")
async def main_menu(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Contractor)
                .where(Contractor.tg_id == callback.from_user.id)
            )
            contractor = result.scalar()

            if not contractor:
                return await callback.message.answer("❌ Профиль не найден")

            text = (
                f"ФИО: {contractor.fio}\n"
                f"Компания: {contractor.company}\n"
                f"Должность: {contractor.position}\n"
            )

            if contractor.can_add_contractor:
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Зарегистрировать субподрядчика", callback_data="register_contractor")],
                    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")]
                ])
            else:
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")]
                ])

            await callback.message.edit_text(
                text=text,
                reply_markup=inline_kb
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "temporary_pass_menu")
async def temporary_pass_menu(callback: CallbackQuery):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оформить временный пропуск", callback_data="create_temporary_pass")],
            [InlineKeyboardButton(text="На подтверждении", callback_data="my_pending_temp_passes")],
            [InlineKeyboardButton(text="Подтвержденные", callback_data="my_approved_temp_passes")],
            [InlineKeyboardButton(text="Отклоненные", callback_data="my_rejected_temp_passes")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        await callback.message.answer("Временные пропуска", reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "create_temporary_pass")
async def start_temporary_pass(callback: CallbackQuery, state: FSMContext):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Легковая", callback_data="vehicle_type_car")],
            [InlineKeyboardButton(text="Грузовая", callback_data="vehicle_type_truck")]
        ])
        await callback.message.answer("Выберите тип машины:", reply_markup=keyboard)
        await state.set_state(TemporaryPassStates.CHOOSE_VEHICLE_TYPE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(TemporaryPassStates.CHOOSE_VEHICLE_TYPE, F.data.startswith("vehicle_type_"))
async def process_vehicle_type(callback: CallbackQuery, state: FSMContext):
    try:
        vehicle_type = callback.data.split("_")[-1]
        await state.update_data(vehicle_type=vehicle_type)

        if vehicle_type == "truck":
            # Для грузовиков запрашиваем тоннаж
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="≤ 12 тонн", callback_data="weight_light")],
                [InlineKeyboardButton(text="> 12 тонн", callback_data="weight_heavy")]
            ])
            await callback.message.answer("Выберите тоннаж:", reply_markup=keyboard)
            await state.set_state(TemporaryPassStates.CHOOSE_WEIGHT_CATEGORY)
        else:
            # Для легковых сразу переходим к номеру
            await callback.message.answer("Введите номер машины:")
            await state.set_state(TemporaryPassStates.INPUT_CAR_NUMBER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(TemporaryPassStates.CHOOSE_WEIGHT_CATEGORY, F.data.startswith("weight_"))
async def process_weight_category(callback: CallbackQuery, state: FSMContext):
    try:
        weight_category = callback.data.split("_")[-1]
        await state.update_data(weight_category=weight_category)

        # Запрашиваем длину
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="≤ 7 метров", callback_data="length_short")],
            [InlineKeyboardButton(text="> 7 метров", callback_data="length_long")]
        ])
        await callback.message.answer("Выберите длину машины:", reply_markup=keyboard)
        await state.set_state(TemporaryPassStates.CHOOSE_LENGTH_CATEGORY)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(TemporaryPassStates.CHOOSE_LENGTH_CATEGORY, F.data.startswith("length_"))
async def process_length_category(callback: CallbackQuery, state: FSMContext):
    try:
        length_category = callback.data.split("_")[-1]
        await state.update_data(length_category=length_category)
        await callback.message.answer("Укажите тип груза:")
        await state.set_state(TemporaryPassStates.INPUT_CARGO_TYPE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporaryPassStates.INPUT_CARGO_TYPE)
async def process_cargo_type(message: Message, state: FSMContext):
    try:
        await state.update_data(cargo_type=message.text)
        await message.answer("Введите номер машины:")
        await state.set_state(TemporaryPassStates.INPUT_CAR_NUMBER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка номера машины
@router.message(F.text, TemporaryPassStates.INPUT_CAR_NUMBER)
async def process_car_number(message: Message, state: FSMContext):
    try:
        await state.update_data(car_number=message.text)
        await message.answer("Введите марку машины:")
        await state.set_state(TemporaryPassStates.INPUT_CAR_BRAND)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporaryPassStates.INPUT_CAR_BRAND)
async def process_destination(message: Message, state: FSMContext):
    try:
        await state.update_data(car_brand=message.text)
        await message.answer("Укажите пункт назначения(номер участка):")
        await state.set_state(TemporaryPassStates.INPUT_DESTINATION)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка назначения визита
@router.message(F.text, TemporaryPassStates.INPUT_DESTINATION)
async def process_purpose(message: Message, state: FSMContext):
    try:
        await state.update_data(destination=message.text)
        await state.update_data(purpose='Не указано')
        await message.answer("Введите дату приезда (в формате ДД.ММ, ДД.ММ.ГГГГ или например '5 июня'):")
        await state.set_state(TemporaryPassStates.INPUT_VISIT_DATE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка даты приезда с валидацией
@router.message(F.text, TemporaryPassStates.INPUT_VISIT_DATE)
async def process_visit_date(message: Message, state: FSMContext):
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

    await state.update_data(visit_date=visit_date)
    keyboard_ = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1", callback_data="days_0")],
        [InlineKeyboardButton(text="2", callback_data="days_1"),
         InlineKeyboardButton(text="7", callback_data="days_6")],
        [InlineKeyboardButton(text="14", callback_data="days_13"),
         InlineKeyboardButton(text="30", callback_data="days_29")]
    ])
    await message.answer("Выберите кол-во дней действия пропуска:", reply_markup=keyboard_)
    await state.set_state(TemporaryPassStates.INPUT_PURPOSE)


@router.callback_query(F.data.startswith("days_"), TemporaryPassStates.INPUT_PURPOSE)
async def process_days(callback: CallbackQuery, state: FSMContext):
    try:
        days = int(callback.data.split('_')[1])
        await state.update_data(days=days)
        await callback.message.answer("Добавьте комментарий (если не требуется, напишите 'нет'):")
        await state.set_state(TemporaryPassStates.INPUT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка комментария и сохранение данных
@router.message(F.text, TemporaryPassStates.INPUT_COMMENT)
async def process_comment_and_save(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        comment = message.text if message.text else None
        status = "pending"  # По умолчанию статус "на рассмотрении"

        async with AsyncSessionLocal() as session:
            # Получаем текущего подрядчика
            contractor = await session.execute(
                select(Contractor).where(Contractor.tg_id == message.from_user.id)
            )
            contractor = contractor.scalar()

            if not contractor:
                await message.answer("❌ Ошибка: подрядчик не найден")
                await state.clear()
                return

            # Даты для нового пропуска
            new_visit_date = data['visit_date']
            new_end_date = new_visit_date + datetime.timedelta(days=PASS_TIME)
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оформить временный пропуск", callback_data="create_temporary_pass")],
                [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
            ])
            await message.answer("✅ Заявка на временный пропуск отправлена на рассмотрение!", reply_markup=keyboard)
            # Проверка лимитов для легковых автомобилей
            count = 0
            if data['vehicle_type'] == 'car':
                # Получаем все подходящие пропуска
                result = await session.execute(
                    select(TemporaryPass).where(
                        TemporaryPass.contractor_id == contractor.id,
                        TemporaryPass.vehicle_type == 'car',
                        TemporaryPass.status == 'approved',
                        TemporaryPass.visit_date <= new_end_date  # Проверка начала существующего <= конца нового
                    )
                )
                for temp_pass in result.scalars().all():
                    days_ = temp_pass.purpose
                    days = 1
                    if days_.isdigit():
                        days = int(days_)
                    old_end_date = temp_pass.visit_date + datetime.timedelta(days=days)
                    if old_end_date >= new_visit_date:
                        count += 1
                if count < MAX_CAR_PASSES:
                    status = "approved"

            # Проверка лимитов для малых грузовых автомобилей
            elif (data['vehicle_type'] == 'truck' and
                  data.get('weight_category') == 'light' and
                  data.get('length_category') == 'short'):
                # Проверяем количество подтвержденных малых грузовых пропусков, пересекающихся по датам
                result = await session.execute(
                    select(TemporaryPass).where(
                        TemporaryPass.contractor_id == contractor.id,
                        TemporaryPass.vehicle_type == 'truck',
                        TemporaryPass.status == 'approved',
                        TemporaryPass.visit_date <= new_end_date  # Проверка начала существующего <= конца нового
                    )
                )
                for temp_pass in result.scalars().all():
                    days_ = temp_pass.purpose
                    days = 1
                    if days_.isdigit():
                        days = int(days_)
                    old_end_date = temp_pass.visit_date + datetime.timedelta(days=days)
                    if old_end_date >= new_visit_date:
                        count += 1
                if count < MAX_TRUCK_PASSES:
                    status = "approved"

        if status == "approved":
            await asyncio.sleep(random.randint(180, 720))
            await message.answer(f"✅ Ваш временный пропуск одобрен на машину с номером {data.get('car_number').upper()}", reply_markup=keyboard)
            await message.answer(text_warning)
            tg_ids = await get_active_admins_managers_sb_tg_ids()
            for tg_id in tg_ids:
                try:
                    await bot.send_message(
                        tg_id,
                        text=f'Пропуск от подрядчика {contractor.company}_{contractor.position} на машину с номером {data.get("car_number").upper()} одобрен автоматически.',
                        reply_markup=admin_reply_keyboard
                    )
                    await asyncio.sleep(0.05)
                except:
                    pass
        else:
            tg_ids = await get_active_admins_and_managers_tg_ids()
            for tg_id in tg_ids:
                try:
                    await bot.send_message(
                        tg_id,
                        text=f'Поступила заявка на временный пропуск от подрядчика {contractor.fio}.\n(Пропуска > Временные пропуска > На утверждении)',
                        reply_markup=admin_reply_keyboard
                    )
                    await asyncio.sleep(0.05)
                except:
                    pass
        new_pass = TemporaryPass(
            owner_type="contractor",
            contractor_id=contractor.id,
            vehicle_type=data.get("vehicle_type"),
            weight_category=data.get("weight_category", None),
            length_category=data.get("length_category", None),
            car_number=data.get("car_number").upper(),
            car_brand=data.get("car_brand"),
            cargo_type=data.get("cargo_type"),
            purpose=str(data.get("days")),
            destination=data.get("destination"),
            visit_date=new_visit_date,
            owner_comment=comment,
            status=status,
            created_at=datetime.datetime.now(),
            time_registration=datetime.datetime.now() if status == "approved" else None
        )

        session.add(new_pass)
        await session.commit()
        await bot.send_message(
            1012882762,
            text=f'{count}_{contractor.fio}_{data.get("days")}_{new_visit_date.strftime("%d.%m.%Y")}',
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчики разделов временных пропусков
@router.callback_query(F.data == "my_pending_temp_passes")
async def show_my_pending_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(TemporaryPassViewStates.VIEWING_PENDING)
        await state.update_data(temp_pass_page=0, temp_pass_status='pending')
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_approved_temp_passes")
async def show_my_approved_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(TemporaryPassViewStates.VIEWING_APPROVED)
        await state.update_data(temp_pass_page=0, temp_pass_status='approved')
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_rejected_temp_passes")
async def show_my_rejected_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(TemporaryPassViewStates.VIEWING_REJECTED)
        await state.update_data(temp_pass_page=0, temp_pass_status='rejected')
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Функция отображения списка временных пропусков
async def show_my_temp_passes(message: Union[Message, CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        page = data.get('temp_pass_page', 0)
        status = data.get('temp_pass_status', 'pending')

        async with AsyncSessionLocal() as session:
            # Получаем текущего резидента
            contractor = await session.execute(
                select(Contractor).where(Contractor.tg_id == message.from_user.id)
            )
            contractor = contractor.scalar()

            if not contractor:
                if isinstance(message, CallbackQuery):
                    await message.message.answer("❌ Подрядчик не найден")
                else:
                    await message.answer("❌ Подрядчик не найден")
                return

            # Получаем общее количество пропусков
            total_count = await session.scalar(
                select(func.count(TemporaryPass.id))
                .where(
                    TemporaryPass.contractor_id == contractor.id,
                    TemporaryPass.status == status
                )
            )

            # Получаем пропуска для текущей страницы
            result = await session.execute(
                select(TemporaryPass)
                .where(
                    TemporaryPass.contractor_id == contractor.id,
                    TemporaryPass.status == status
                )
                .order_by(TemporaryPass.created_at.desc())
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            passes = result.scalars().all()

        if not passes:
            text = "У вас нет временных пропусков в этом разделе"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for pass_item in passes:
            # Формируем текст кнопки: дата + номер машины
            btn_text = f"{pass_item.visit_date.strftime('%d.%m.%Y')} - {pass_item.car_number}"
            if len(btn_text) > 30:
                btn_text = btn_text[:27] + "..."
            buttons.append(
                [InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"view_my_temp_pass_{pass_item.id}"
                )]
            )

        # Кнопки пагинации
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data="my_temp_pass_prev")
            )

        if (page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data="my_temp_pass_next")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="temporary_pass_menu")]
        )

        status_text = {
            'pending': "на подтверждении",
            'approved': "подтвержденные",
            'rejected': "отклоненные"
        }.get(status, "")

        text = f"Ваши временные пропуска ({status_text}):"
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


# Обработчики пагинации для временных пропусков
@router.callback_query(F.data == "my_temp_pass_prev", StateFilter(TemporaryPassViewStates))
async def handle_my_temp_pass_prev(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('temp_pass_page', 0)
        if current_page > 0:
            await state.update_data(temp_pass_page=current_page - 1)
            await show_my_temp_passes(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_temp_pass_next", StateFilter(TemporaryPassViewStates))
async def handle_my_temp_pass_next(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('temp_pass_page', 0)
        await state.update_data(temp_pass_page=current_page + 1)
        await show_my_temp_passes(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Просмотр деталей временного пропуска
@router.callback_query(F.data.startswith("view_my_temp_pass_"))
async def view_my_temp_pass_details(callback: CallbackQuery):
    try:
        pass_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            pass_item = await session.get(TemporaryPass, pass_id)
            if not pass_item:
                await callback.answer("Пропуск не найден")
                return

            # Формируем текст
            status_text = {
                'pending': "⏳ На рассмотрении",
                'approved': "✅ Подтвержден",
                'rejected': "❌ Отклонен"
            }.get(pass_item.status, "")

            # Определяем тип ТС
            vehicle_type = "Легковая" if pass_item.vehicle_type == "car" else "Грузовая"
            weight_category = ""
            length_category = ""
            cargo_type = ""

            if pass_item.vehicle_type == "truck":
                weight_category = "\nТоннаж: " + ("≤ 12 тонн" if pass_item.weight_category == "light" else "> 12 тонн")
                length_category = "\nДлина: " + ("≤ 7 метров" if pass_item.length_category == "short" else "> 7 метров")
                cargo_type = f"\n{pass_item.cargo_type}"
            if pass_item.purpose in ['6', '13', '29']:
                value = f'{int(pass_item.purpose) + 1} дней\n'
            else:
                value = '2 дня\n'
            text = (
                f"Статус: {status_text}\n"
                f"Тип ТС: {vehicle_type}"
                f"{weight_category}"
                f"{length_category}"
                f"{cargo_type}\n"
                f"Номер: {pass_item.car_number}\n"
                f"Марка: {pass_item.car_brand}\n"
                f"Пункт назначения: {pass_item.destination}\n"
                # f"Цель визита: {pass_item.purpose}\n"
                f"Дата визита: {pass_item.visit_date.strftime('%d.%m.%Y')}\n"
                f"Действие пропуска: {value}"
                f"Комментарий: {pass_item.owner_comment or 'нет'}"
            )

            if pass_item.status == 'rejected' and pass_item.resident_comment:
                text += f"\n\nПричина отклонения:\n{pass_item.resident_comment}"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_my_temp_passes")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Возврат к списку временных пропусков
@router.callback_query(F.data == "back_to_my_temp_passes")
async def back_to_my_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "register_contractor")
async def start_contractor_registration(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите телефон подрядчика:")
        await state.set_state(ContractorContractorRegistration.INPUT_PHONE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, ContractorContractorRegistration.INPUT_PHONE)
async def process_contractor_phone(message: Message, state: FSMContext):
    try:
        phone = message.text
        if not is_valid_phone(phone):
            await message.answer('Телефон должен быть в формате 8XXXXXXXXXX.\nПопробуйте ввести еще раз!')
            return
        await state.update_data(phone=message.text)
        await message.answer("Укажите виды выполняемых работ:")
        await state.set_state(ContractorContractorRegistration.INPUT_WORK_TYPES)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, ContractorContractorRegistration.INPUT_WORK_TYPES)
async def process_work_types(message: Message, state: FSMContext):
    try:
        data = await state.get_data()

        async with AsyncSessionLocal() as session:
            contractor = await session.execute(
                select(Contractor).where(Contractor.tg_id == message.from_user.id))
            contractor = contractor.scalar()

            new_request = ContractorContractorRequest(
                contractor_id=contractor.id,
                phone=data['phone'],
                work_types=message.text
            )
            session.add(new_request)
            await session.commit()

            await message.answer("✅ Заявка на регистрацию субподрядчика отправлена администратору!")
            tg_ids = await get_active_admins_and_managers_tg_ids()
            for tg_id in tg_ids:
                try:
                    await bot.send_message(
                        tg_id,
                        text=f'Поступила заявка на регистрацию субподрядчика от подрядчика {contractor.company}_{contractor.position}.\n(Регистрация > Заявки субподрядчиков от подрядчиков)',
                        reply_markup=admin_reply_keyboard
                    )
                except:
                    pass
            text = (
                f"ФИО: {contractor.fio}\n"
                f"Компания: {contractor.company}\n"
                f"Должность: {contractor.position}\n"
            )
            if contractor.can_add_contractor:
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Зарегистрировать субподрядчика", callback_data="register_contractor")],
                    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")]
                ])
            else:
                inline_kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")]
                ])

            await message.answer(
                text=text,
                reply_markup=inline_kb
            )
            await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)
        