import asyncio
import datetime
import logging

from delete_temp_pass import scheduler
from handlers import handlers_admin_search, handlers_contractor, handlers_for_all, handlers_admin_registration, \
    handlers_admin_temporary_pass, handlers_admin_user_management, handlers_resident_appeal, handlers_admin_appeal, \
    handlers_resident, handlers_admin_permanent_pass, handlers_admin_self_pass, handlers_admin_statistic, \
    handlers_security, handlers_admin_manager_sending, handlers_truck_yookassa, handlers_admin_photo_info
from aiogram import Dispatcher

from bot import bot
from db.models import create_tables

logger = logging.getLogger(__name__)


async def main() -> None:
    await create_tables()
    logging.basicConfig(level=logging.INFO, format='%(filename)s:%(lineno)d %(levelname)-8s [%(asctime)s] - %(name)s - %(message)s')
    logging.info('Starting bot')

    dp = Dispatcher()
    dp.include_router(handlers_admin_photo_info.router)
    dp.include_router(handlers_truck_yookassa.router)
    dp.include_router(handlers_admin_user_management.router)
    dp.include_router(handlers_admin_registration.router)
    dp.include_router(handlers_admin_self_pass.router)
    dp.include_router(handlers_admin_appeal.router)
    dp.include_router(handlers_admin_search.router)
    dp.include_router(handlers_admin_statistic.router)
    dp.include_router(handlers_admin_permanent_pass.router)
    dp.include_router(handlers_admin_temporary_pass.router)
    dp.include_router(handlers_admin_manager_sending.router)
    dp.include_router(handlers_security.router)
    dp.include_router(handlers_contractor.router)
    dp.include_router(handlers_resident.router)
    dp.include_router(handlers_resident_appeal.router)
    dp.include_router(handlers_for_all.router)

    current_day = datetime.datetime.now().day
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler(current_day - 1))

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

