# handlers_admin_self_pass.py
import asyncio

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import datetime

from sqlalchemy import select

from bot import bot
from config import ADMIN_IDS, RAZRAB, TRUCK_CATEGORIES_PHOTO_FILE_ID
from db.models import AsyncSessionLocal, TemporaryPass, Manager, PermanentPass
from date_parser import parse_date
from db.util import get_active_admins_managers_sb_tg_ids
from handlers.handlers_admin_permanent_pass import get_passes_menu
from handlers.handlers_admin_user_management import admin_reply_keyboard
from temporary_truck import (
    PAYLOAD_PREFIX_SELF,
    category_from_truck_callback_data,
    truck_category_markup,
)


router = Router()


class TemporarySelfPassStates(StatesGroup):
    CHOOSE_VEHICLE_TYPE = State()
    TRUCK_CHOOSE_CATEGORY = State()
    TRUCK_INPUT_BRAND = State()
    TRUCK_INPUT_NUMBER = State()
    TRUCK_INPUT_COMMENT = State()
    TRUCK_INPUT_VISIT_DATE = State()
    CHOOSE_WEIGHT_CATEGORY = State()
    CHOOSE_LENGTH_CATEGORY = State()
    INPUT_CAR_NUMBER = State()
    INPUT_CAR_BRAND = State()
    INPUT_CARGO_TYPE = State()
    INPUT_DESTINATION = State()
    INPUT_PURPOSE = State()
    INPUT_VISIT_DATE = State()
    INPUT_COMMENT = State()


class PermanentSelfPassStates(StatesGroup):
    INPUT_CAR_BRAND = State()
    INPUT_CAR_MODEL = State()
    INPUT_CAR_NUMBER = State()
    INPUT_DESTINATION = State()
    INPUT_CAR_OWNER = State()


async def get_owner_info(user_id: int) -> str:
    """Определяет информацию о владельце пропуска (админ/менеджер)"""
    if user_id in ADMIN_IDS:
        return f"Администратор"

    async with AsyncSessionLocal() as session:
        manager = await session.scalar(
            select(Manager)
            .where(Manager.tg_id == user_id, Manager.status == True)
        )
        if manager and manager.fio:
            return f"Менеджер {manager.fio}"

    return "Сотрудник"


@router.callback_query(F.data == "issue_self_pass")
async def start_self_pass(callback: CallbackQuery, state: FSMContext):
    """Начало оформления временного пропуска для себя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Легковая", callback_data="self_vehicle_type_car")],
        [InlineKeyboardButton(text="Грузовая", callback_data="self_vehicle_type_truck")]
    ])
    await callback.message.edit_text("Выберите тип машины:", reply_markup=keyboard)
    await state.set_state(TemporarySelfPassStates.CHOOSE_VEHICLE_TYPE)


@router.callback_query(
    TemporarySelfPassStates.CHOOSE_VEHICLE_TYPE,
    F.data.startswith("self_vehicle_type_")
)
async def process_self_vehicle_type(callback: CallbackQuery, state: FSMContext):
    """Обработка типа транспортного средства"""
    vehicle_type = callback.data.split("_")[-1]
    await state.update_data(vehicle_type=vehicle_type)

    if vehicle_type == "truck":
        kb = truck_category_markup(PAYLOAD_PREFIX_SELF)
        cap = "Выберите тип машины:"
        if TRUCK_CATEGORIES_PHOTO_FILE_ID:
            await callback.message.answer_photo(
                photo=TRUCK_CATEGORIES_PHOTO_FILE_ID,
                caption=cap,
                reply_markup=kb,
            )
        else:
            await callback.message.answer(cap, reply_markup=kb)
        await state.set_state(TemporarySelfPassStates.TRUCK_CHOOSE_CATEGORY)
    else:
        await callback.message.answer("Введите номер машины:")
        await state.set_state(TemporarySelfPassStates.INPUT_CAR_NUMBER)


@router.callback_query(
    TemporarySelfPassStates.TRUCK_CHOOSE_CATEGORY,
    F.data.startswith(f"{PAYLOAD_PREFIX_SELF}_"),
)
async def process_self_truck_category(callback: CallbackQuery, state: FSMContext):
    label = category_from_truck_callback_data(callback.data or "", PAYLOAD_PREFIX_SELF)
    if not label:
        await callback.answer()
        return
    await state.update_data(weight_category=label)
    await callback.message.answer("Введите марку машины:")
    await state.set_state(TemporarySelfPassStates.TRUCK_INPUT_BRAND)
    await callback.answer()


@router.message(F.text, TemporarySelfPassStates.TRUCK_INPUT_BRAND)
async def process_self_truck_brand(message: Message, state: FSMContext):
    await state.update_data(car_brand=message.text)
    await message.answer("Введите номер машины:")
    await state.set_state(TemporarySelfPassStates.TRUCK_INPUT_NUMBER)


@router.message(F.text, TemporarySelfPassStates.TRUCK_INPUT_NUMBER)
async def process_self_truck_number(message: Message, state: FSMContext):
    await state.update_data(car_number=message.text)
    await message.answer("Добавьте комментарий (если не требуется, напишите 'нет'):")
    await state.set_state(TemporarySelfPassStates.TRUCK_INPUT_COMMENT)


@router.message(F.text, TemporarySelfPassStates.TRUCK_INPUT_COMMENT)
async def process_self_truck_comment(message: Message, state: FSMContext):
    t = (message.text or "").strip()
    comment = None if t.lower() == "нет" else t
    await state.update_data(owner_comment=comment)
    await message.answer(
        "Введите дату приезда (в формате ДД.ММ, ДД.ММ.ГГГГ или '5 июня'):",
    )
    await state.set_state(TemporarySelfPassStates.TRUCK_INPUT_VISIT_DATE)


@router.message(F.text, TemporarySelfPassStates.TRUCK_INPUT_VISIT_DATE)
async def process_self_truck_visit_date(message: Message, state: FSMContext):
    try:
        user_input = (message.text or "").strip()
        visit_date = parse_date(user_input)
        now = datetime.datetime.now().date()

        if not visit_date:
            await message.answer("❌ Неверный формат даты! Введите снова:")
            return

        if visit_date < now:
            await message.answer("❌ Дата не может быть меньше текущей! Введите снова:")
            return

        max_date = now + datetime.timedelta(days=31)
        if visit_date > max_date:
            await message.answer("❌ Пропуск нельзя заказать на месяц вперед! Введите снова:")
            return

        data = await state.get_data()
        owner_info = await get_owner_info(message.from_user.id)
        comment = data.get("owner_comment")

        async with AsyncSessionLocal() as session:
            new_pass = TemporaryPass(
                owner_type="staff",
                vehicle_type="truck",
                weight_category=data.get("weight_category"),
                length_category=None,
                car_number=data["car_number"].upper(),
                car_brand=data["car_brand"],
                cargo_type=None,
                purpose="0",
                destination=None,
                visit_date=visit_date,
                owner_comment=comment,
                security_comment=f"Выписал {owner_info}",
                status="approved",
                created_at=datetime.datetime.now(),
                time_registration=datetime.datetime.now(),
            )
            session.add(new_pass)
            await session.commit()

        await message.answer(
            f"✅ Временный пропуск на машину {data['car_number'].upper()} оформлен!",
            reply_markup=get_passes_menu(),
        )
        tg_ids = await get_active_admins_managers_sb_tg_ids()
        for tg_id in tg_ids:
            try:
                await bot.send_message(
                    tg_id,
                    text=(
                        f"Пропуск от {owner_info} на машину с номером {data['car_number'].upper()} "
                        f"одобрен автоматически.\n(Пропуска > Временные пропуска > Подтвержденные)"
                    ),
                    reply_markup=admin_reply_keyboard,
                )
                await asyncio.sleep(0.05)
            except Exception:
                pass
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при оформлении пропуска: {str(e)}")
        await state.clear()


@router.callback_query(
    TemporarySelfPassStates.CHOOSE_WEIGHT_CATEGORY,
    F.data.startswith("self_weight_")
)
async def process_self_weight_category(callback: CallbackQuery, state: FSMContext):
    """Обработка весовой категории для грузовиков"""
    weight_category = callback.data.split("_")[-1]
    await state.update_data(weight_category=weight_category)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="≤ 7 метров", callback_data="self_length_short")],
        [InlineKeyboardButton(text="> 7 метров", callback_data="self_length_long")]
    ])
    await callback.message.answer("Выберите длину машины:", reply_markup=keyboard)
    await state.set_state(TemporarySelfPassStates.CHOOSE_LENGTH_CATEGORY)


@router.callback_query(TemporarySelfPassStates.CHOOSE_LENGTH_CATEGORY, F.data.startswith("self_length_"))
async def process_length_category(callback: CallbackQuery, state: FSMContext):
    try:
        length_category = callback.data.split("_")[-1]
        await state.update_data(length_category=length_category)
        await callback.message.answer("Укажите тип груза:")
        await state.set_state(TemporarySelfPassStates.INPUT_CARGO_TYPE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporarySelfPassStates.INPUT_CARGO_TYPE)
async def process_cargo_type(message: Message, state: FSMContext):
    try:
        await state.update_data(cargo_type=message.text)
        await message.answer("Введите номер машины:")
        await state.set_state(TemporarySelfPassStates.INPUT_CAR_NUMBER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка номера машины
@router.message(F.text, TemporarySelfPassStates.INPUT_CAR_NUMBER)
async def process_car_number(message: Message, state: FSMContext):
    try:
        await state.update_data(car_number=message.text)
        await message.answer("Введите марку машины:")
        await state.set_state(TemporarySelfPassStates.INPUT_CAR_BRAND)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporarySelfPassStates.INPUT_CAR_BRAND)
async def process_car_brand(message: Message, state: FSMContext):
    try:
        await state.update_data(car_brand=message.text)
        await message.answer("Укажите пункт назначения(номер участка):")
        await state.set_state(TemporarySelfPassStates.INPUT_DESTINATION)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporarySelfPassStates.INPUT_DESTINATION)
async def process_self_purpose(message: Message, state: FSMContext):
    """Обработка цели визита"""
    await state.update_data(destination=message.text)
    await state.update_data(purpose='Не указано')
    await message.answer("Введите дату приезда (в формате ДД.ММ, ДД.ММ.ГГГГ или '5 июня'):")
    await state.set_state(TemporarySelfPassStates.INPUT_VISIT_DATE)


@router.message(F.text, TemporarySelfPassStates.INPUT_VISIT_DATE)
async def process_self_visit_date(message: Message, state: FSMContext):
    """Валидация и обработка даты визита"""
    user_input = message.text.strip()
    visit_date = parse_date(user_input)
    now = datetime.datetime.now().date()

    if not visit_date:
        await message.answer("❌ Неверный формат даты! Введите снова:")
        return

    if visit_date < now:
        await message.answer("❌ Дата не может быть меньше текущей! Введите снова:")
        return

    max_date = now + datetime.timedelta(days=31)
    if visit_date > max_date:
        await message.answer("❌ Пропуск нельзя заказать на месяц вперед! Введите снова:")
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
    await state.set_state(TemporarySelfPassStates.INPUT_PURPOSE)


@router.callback_query(F.data.startswith("days_"), TemporarySelfPassStates.INPUT_PURPOSE)
async def process_days(callback: CallbackQuery, state: FSMContext):
    try:
        days = int(callback.data.split('_')[1])
        await state.update_data(days=days)
        await callback.message.answer("Добавьте комментарий (если не требуется, напишите 'нет'):")
        await state.set_state(TemporarySelfPassStates.INPUT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, TemporarySelfPassStates.INPUT_COMMENT)
async def process_self_comment_and_save(message: Message, state: FSMContext):
    """Сохранение временного пропуска с автоматическим подтверждением"""
    try:
        data = await state.get_data()
        comment = message.text if message.text.lower() != "нет" else None

        # Определяем информацию о владельце
        owner_info = await get_owner_info(message.from_user.id)

        async with AsyncSessionLocal() as session:
            new_pass = TemporaryPass(
                owner_type="staff",
                vehicle_type=data["vehicle_type"],
                weight_category=data.get("weight_category"),
                length_category=data.get("length_category"),
                car_number=data["car_number"].upper(),
                car_brand=data["car_brand"],
                cargo_type=data.get("cargo_type"),
                purpose=str(data.get("days")),
                destination=data["destination"],
                visit_date=data["visit_date"],
                owner_comment=comment,
                security_comment=f"Выписал {owner_info}",
                status="approved",
                created_at=datetime.datetime.now(),
                time_registration=datetime.datetime.now()
            )
            session.add(new_pass)
            await session.commit()

        await message.answer(
            f"✅ Временный пропуск на машину {data['car_number'].upper()} оформлен!",
            reply_markup=get_passes_menu()
        )
        tg_ids = await get_active_admins_managers_sb_tg_ids()
        for tg_id in tg_ids:
            try:
                await bot.send_message(
                    tg_id,
                    text=f'Пропуск от {owner_info} на машину с номером {data["car_number"].upper()} одобрен автоматически.\n(Пропуска > Временные пропуска > Подтвержденные)',
                    reply_markup=admin_reply_keyboard
                )
                await asyncio.sleep(0.05)
            except:
                pass
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при оформлении пропуска: {str(e)}")
        await state.clear()


#Постоянные пропуска
@router.callback_query(F.data == "issue_permanent_self_pass")
async def start_permanent_self_pass(callback: CallbackQuery, state: FSMContext):
    """Начало оформления постоянного пропуска для себя"""
    await callback.message.answer("Введите марку машины:")
    await state.set_state(PermanentSelfPassStates.INPUT_CAR_BRAND)


@router.message(F.text, PermanentSelfPassStates.INPUT_CAR_BRAND)
async def process_self_car_brand(message: Message, state: FSMContext):
    await state.update_data(car_brand=message.text)
    await message.answer("Введите модель машины:")
    await state.set_state(PermanentSelfPassStates.INPUT_CAR_MODEL)


@router.message(F.text, PermanentSelfPassStates.INPUT_CAR_MODEL)
async def process_self_car_model(message: Message, state: FSMContext):
    await state.update_data(car_model=message.text)
    await message.answer("Введите номер машины:")
    await state.set_state(PermanentSelfPassStates.INPUT_CAR_NUMBER)


@router.message(F.text, PermanentSelfPassStates.INPUT_CAR_NUMBER)
async def process_self_car_number(message: Message, state: FSMContext):
    await state.update_data(car_number=message.text)
    await message.answer("Укажите пункт назначения(номер участка):")
    await state.set_state(PermanentSelfPassStates.INPUT_DESTINATION)


@router.message(F.text, PermanentSelfPassStates.INPUT_DESTINATION)
async def process_self_destination(message: Message, state: FSMContext):
    await state.update_data(destination=message.text)
    await message.answer("Укажите владельца автомобиля:")
    await state.set_state(PermanentSelfPassStates.INPUT_CAR_OWNER)


@router.message(F.text, PermanentSelfPassStates.INPUT_CAR_OWNER)
async def process_self_car_owner(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        owner_info = await get_owner_info(message.from_user.id)

        async with AsyncSessionLocal() as session:
            new_pass = PermanentPass(
                car_brand=data['car_brand'],
                car_model=data['car_model'],
                car_number=data['car_number'].upper(),
                destination=data['destination'],
                car_owner=message.text,
                status='approved',
                security_comment=f"Выписал {owner_info}",
                created_at=datetime.datetime.now(),
                time_registration=datetime.datetime.now()
            )
            session.add(new_pass)
            await session.commit()

        # Уведомление админов и менеджеров
        tg_ids = await get_active_admins_managers_sb_tg_ids()
        for tg_id in tg_ids:
            try:
                await bot.send_message(
                    tg_id,
                    text=f'Постоянный пропуск от {owner_info} на машину {data["car_number"].upper()} одобрен автоматически.',
                    reply_markup=admin_reply_keyboard
                )
                await asyncio.sleep(0.05)
            except:
                pass
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при оформлении пропуска: {str(e)}")
        await state.clear()
