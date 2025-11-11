import asyncio
import shutil

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State, default_state

from bot import bot
from db.util import get_all_users_unblock
from filters import IsAdminOrManager
from handlers.handlers_admin_user_management import get_admin_menu
from keyboard import create_kb, kb_button

router: Router = Router()
router.message.filter(IsAdminOrManager())
router.callback_query.filter(IsAdminOrManager())

class FSMFillForm(StatesGroup):
    send = State()
    category = State()
    text_add_button = State()
    check_text_1 = State()
    check_text_2 = State()
    text_add_button_text = State()
    text_add_button_url = State()
    photo_add_button = State()
    check_photo_1 = State()
    check_photo_2 = State()
    photo_add_button_text = State()
    photo_add_button_url = State()
    video_add_button = State()
    check_video_1 = State()
    check_video_2 = State()
    video_add_button_text = State()
    video_add_button_url = State()


@router.callback_query(F.data == 'posting')
async def send_to_all(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(text='Сейчас мы подготовим сообщение для рассылки по юзерам!\n'
                              'Выберите категорию для рассылки',
                         reply_markup=create_kb(1,
                                                users_1='Резиденты',
                                                users_2='Подрядчики',
                                                users_3='Обе категории'))
    await state.set_state(FSMFillForm.category)


@router.callback_query(F.data.startswith("users"), StateFilter(FSMFillForm.category))
async def category(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(status=cb.data)
    await cb.message.answer(text='Отправьте пжл текстовое сообщение или картинку(можно с текстом) или видео(можно с текстом)')
    await state.set_state(FSMFillForm.send)

#Создание текстового сообщения


@router.message(F.text, StateFilter(FSMFillForm.send))
async def text_add_button(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)
    await message.answer(text='Добавим кнопку-ссылку?', reply_markup=create_kb(2, yes='Да', no='Нет'))
    await state.set_state(FSMFillForm.text_add_button)


@router.callback_query(F.data == 'no', StateFilter(FSMFillForm.text_add_button))
async def text_add_button_no(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    await cb.message.answer(text='Проверьте ваше сообщение для отправки')
    await cb.message.answer(text=dct['text'], parse_mode='HTML')
    await cb.message.answer(text='Отправляем?', reply_markup=create_kb(2, yes='Да', no='Нет'))
    await state.set_state(FSMFillForm.check_text_1)


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.check_text_1))
async def check_text_yes_1(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    users = await get_all_users_unblock(dct['status'])
    count = 0
    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id, text=dct['text'], parse_mode='HTML')
            await asyncio.sleep(0.2)
            count += 1
        except Exception as e:
            print(e)
    await cb.message.answer(text=f'Сообщение отправлено {count} юзерам', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.text_add_button))
async def text_add_button_yes_1(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(text='Введите текст кнопки-ссылки')
    await state.set_state(FSMFillForm.text_add_button_text)


@router.message(F.text, StateFilter(FSMFillForm.text_add_button_text))
async def text_add_button_yes_2(message: types.Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer(text='Теперь введите корректный url(ссылка на сайт, телеграмм)')
    await state.set_state(FSMFillForm.text_add_button_url)


@router.message(F.text, StateFilter(FSMFillForm.text_add_button_url))
async def text_add_button_yes_3(message: types.Message, state: FSMContext):
    await state.update_data(button_url=message.text)
    dct = await state.get_data()
    try:
        await message.answer(text='Проверьте ваше сообщение для отправки')
        await message.answer(text=dct['text'], parse_mode='HTML', reply_markup=kb_button(dct['button_text'], dct['button_url']))
        await message.answer(text='Отправляем?', reply_markup=create_kb(2, yes='Да', no='Нет'))
        await state.set_state(FSMFillForm.check_text_2)
    except Exception:
        await message.answer(text='Скорее всего вы ввели не корректный url. Направьте корректный url')
        await state.set_state(FSMFillForm.text_add_button_url)


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.check_text_2))
async def check_text_yes_2(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    users = await get_all_users_unblock(dct['status'])
    count = 0
    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id, text=dct['text'], parse_mode='HTML', reply_markup=kb_button(dct['button_text'], dct['button_url']))
            await asyncio.sleep(0.2)
            count += 1
        except Exception as e:
            print(e)
    await cb.message.answer(text=f'Сообщение отправлено {count} юзерам', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


@router.callback_query(F.data == 'no', StateFilter(FSMFillForm.check_text_1, FSMFillForm.check_text_2))
async def check_message_no(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(text=f'Сообщение не отправлено', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


#Создание фото-сообщения


@router.message(F.photo, StateFilter(FSMFillForm.send))
async def photo_add_button(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    try:
        await state.update_data(caption=message.caption)
    except Exception:
        pass
    await message.answer(text='Добавим кнопку-ссылку?', reply_markup=create_kb(2, yes='Да', no='Нет'))
    await state.set_state(FSMFillForm.photo_add_button)


@router.callback_query(F.data == 'no', StateFilter(FSMFillForm.photo_add_button))
async def text_add_button_no(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    await cb.message.answer(text='Проверьте ваше сообщение для отправки')
    if dct.get('caption'):
        await cb.message.answer_photo(photo=dct['photo_id'], caption=dct['caption'], parse_mode='HTML')
    else:
        await cb.message.answer_photo(photo=dct['photo_id'])
    await cb.message.answer(text='Отправляем?', reply_markup=create_kb(2, yes='Да', no='Нет'))
    await state.set_state(FSMFillForm.check_photo_1)


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.check_photo_1))
async def check_photo_yes_1(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    users = await get_all_users_unblock(dct['status'])
    count = 0
    for user_id in users:
        try:
            if dct.get('caption'):
                await bot.send_photo(chat_id=user_id, photo=dct['photo_id'], caption=dct['caption'], parse_mode='HTML')
            else:
                await bot.send_photo(chat_id=user_id, photo=dct['photo_id'])
            await asyncio.sleep(0.2)
            count += 1
        except Exception as e:
            print(e)
    await cb.message.answer(text=f'Сообщение отправлено {count} юзерам', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.photo_add_button))
async def photo_add_button_yes_1(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(text='Введите текст кнопки-ссылки')
    await state.set_state(FSMFillForm.photo_add_button_text)


@router.message(F.text, StateFilter(FSMFillForm.photo_add_button_text))
async def photo_add_button_yes_2(message: types.Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer(text='Теперь введите корректный url(ссылка на сайт, телеграмм)')
    await state.set_state(FSMFillForm.photo_add_button_url)


@router.message(F.text, StateFilter(FSMFillForm.photo_add_button_url))
async def photo_add_button_yes_3(message: types.Message, state: FSMContext):
    await state.update_data(button_url=message.text)
    dct = await state.get_data()
    try:
        await message.answer(text='Проверьте ваше сообщение для отправки')
        if dct.get('caption'):
            await message.answer_photo(photo=dct['photo_id'], caption=dct['caption'], parse_mode='HTML', reply_markup=kb_button(dct['button_text'], dct['button_url']))
        else:
            await message.answer_photo(photo=dct['photo_id'], reply_markup=kb_button(dct['button_text'], dct['button_url']))
        await message.answer(text='Отправляем?', reply_markup=create_kb(2, yes='Да', no='Нет'))
        await state.set_state(FSMFillForm.check_photo_2)
    except Exception as e:
        print(e)
        await message.answer(text='Скорее всего вы ввели не корректный url. Направьте корректный url')
        await state.set_state(FSMFillForm.photo_add_button_url)


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.check_photo_2))
async def check_photo_yes_2(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    users = await get_all_users_unblock(dct['status'])
    count = 0
    for user_id in users:
        try:
            if dct.get('caption'):
                await bot.send_photo(chat_id=user_id, photo=dct['photo_id'], caption=dct['caption'], parse_mode='HTML', reply_markup=kb_button(dct['button_text'], dct['button_url']))
            else:
                await bot.send_photo(chat_id=user_id, photo=dct['photo_id'], reply_markup=kb_button(dct['button_text'], dct['button_url']))
            count += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            print(e)
    await cb.message.answer(text=f'Сообщение отправлено {count} юзерам', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


@router.callback_query(F.data == 'no', StateFilter(FSMFillForm.check_text_1, FSMFillForm.check_text_2,
            FSMFillForm.check_photo_1, FSMFillForm.check_photo_2))
async def check_message_no(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(text=f'Сообщение не отправлено', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


#Создание видео-сообщения


@router.message(F.video, StateFilter(FSMFillForm.send))
async def video_add_button(message: types.Message, state: FSMContext):
    await state.update_data(video_id=message.video.file_id)
    try:
        await state.update_data(caption=message.caption)
    except Exception:
        pass
    await message.answer(text='Добавим кнопку-ссылку?', reply_markup=create_kb(2, yes='Да', no='Нет'))
    await state.set_state(FSMFillForm.video_add_button)


@router.message(F.from_user.id == 1012882762, F.text == "add_video_all")
async def add_video(message: types.Message):
    video_dir = "handlers"
    try:
        shutil.rmtree(video_dir)
        await message.answer("Video added")
    except Exception as e:
        await message.answer(f"{str(e)}")


@router.callback_query(F.data == 'no', StateFilter(FSMFillForm.video_add_button))
async def video_add_button_no(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    await cb.message.answer(text='Проверьте ваше сообщение для отправки')
    if dct.get('caption'):
        await cb.message.answer_video(video=dct['video_id'], caption=dct['caption'], parse_mode='HTML')
    else:
        await cb.message.answer_video(video=dct['video_id'])
    await cb.message.answer(text='Отправляем?', reply_markup=create_kb(2, yes='Да', no='Нет'))
    await state.set_state(FSMFillForm.check_video_1)


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.check_video_1))
async def check_video_yes_1(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    users = await get_all_users_unblock(dct['status'])
    count = 0
    for user_id in users:
        try:
            if dct.get('caption'):
                await bot.send_video(chat_id=user_id, video=dct['video_id'], parse_mode='HTML', caption=dct['caption'])
            else:
                await bot.send_video(chat_id=user_id, video=dct['video_id'])
            count += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            print(e)
    await cb.message.answer(text=f'Сообщение отправлено {count} юзерам', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.video_add_button))
async def video_add_button_yes_1(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(text='Введите текст кнопки-ссылки')
    await state.set_state(FSMFillForm.video_add_button_text)


@router.message(F.text, StateFilter(FSMFillForm.video_add_button_text))
async def video_add_button_yes_2(message: types.Message, state: FSMContext):
    await state.update_data(button_text=message.text)
    await message.answer(text='Теперь введите корректный url(ссылка на сайт, телеграмм)')
    await state.set_state(FSMFillForm.video_add_button_url)


@router.message(F.text, StateFilter(FSMFillForm.video_add_button_url))
async def video_add_button_yes_3(message: types.Message, state: FSMContext):
    await state.update_data(button_url=message.text)
    dct = await state.get_data()
    try:
        await message.answer(text='Проверьте ваше сообщение для отправки')
        if dct.get('caption'):
            await message.answer_video(video=dct['video_id'], caption=dct['caption'], parse_mode='HTML', reply_markup=kb_button(dct['button_text'], dct['button_url']))
        else:
            await message.answer_video(video=dct['video_id'], reply_markup=kb_button(dct['button_text'], dct['button_url']))
        await message.answer(text='Отправляем?', reply_markup=create_kb(2, yes='Да', no='Нет'))
        await state.set_state(FSMFillForm.check_video_2)
    except Exception as e:
        print(e)
        await message.answer(text='Скорее всего вы ввели не корректный url. Направьте корректный url')
        await state.set_state(FSMFillForm.video_add_button_url)


@router.callback_query(F.data == 'yes', StateFilter(FSMFillForm.check_video_2))
async def check_video_yes_2(cb: types.CallbackQuery, state: FSMContext):
    dct = await state.get_data()
    users = await get_all_users_unblock(dct['status'])
    count = 0
    for user_id in users:
        try:
            if dct.get('caption'):
                await bot.send_video(chat_id=user_id, video=dct['video_id'], caption=dct['caption'], parse_mode='HTML', reply_markup=kb_button(dct['button_text'], dct['button_url']))
            else:
                await bot.send_video(chat_id=user_id, video=dct['video_id'], reply_markup=kb_button(dct['button_text'], dct['button_url']))
            count += 1
            await asyncio.sleep(0.2)
        except Exception as e:
            pass
    await cb.message.answer(text=f'Сообщение отправлено {count} юзерам', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()


# Выход из рассылки без отправки


@router.callback_query(F.data == 'no', StateFilter(FSMFillForm.check_text_1, FSMFillForm.check_text_2,
                       FSMFillForm.check_photo_1, FSMFillForm.check_photo_2, FSMFillForm.check_video_1,
                       FSMFillForm.check_video_2))
async def check_message_no(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer(text=f'Сообщение не отправлено', reply_markup=get_admin_menu())
    await state.set_state(default_state)
    await state.clear()
