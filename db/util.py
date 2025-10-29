import datetime
import re

from sqlalchemy import select, insert, update

from config import ADMIN_IDS
from db.models import User, AsyncSessionLocal, Manager, Security


async def add_user_to_db(user_id, username, first_name, last_name, time_start):
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(select(User).where(User.id == user_id))
            if not result.scalars().first():
                session.add(User(
                    id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    time_start=time_start
                ))
                await session.commit()
        except Exception as e:
            print(e)
            await session.rollback()


async def update_user_blocked(id):
    async with AsyncSessionLocal() as session:
        try:
            stmt = update(User).where(User.id == id).values(is_active=False)
            session.execute(stmt)
            session.commit()
        except Exception as e:
            print(e)


async def update_user_unblocked(id):
    async with AsyncSessionLocal() as session:
        try:
            stmt = update(User).where(User.id == id).values(is_active=True)
            session.execute(stmt)
            session.commit()
        except Exception as e:
            print(e)


async def is_active(user_id: int) -> bool:
    """
    Проверяет активность пользователя по его Telegram ID
    Возвращает значение поля is_active (True/False)
    Если пользователь не найден - возвращает False
    """
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(User.is_active).where(User.id == int(user_id)))
            is_active = result.scalar_one_or_none()
            return bool(is_active)
        except Exception as e:
            print(f"Ошибка при проверке активности пользователя: {e}")
            return False


async def get_active_admins_and_managers_tg_ids() -> list[int]:
    """
    Получает список Telegram ID всех активных администраторов и менеджеров.

    Returns:
        list[int]: Список уникальных Telegram ID
    """
    async with AsyncSessionLocal() as session:

        # Запрос для менеджеров (статус True и заполненный tg_id)
        managers_query = select(Manager.tg_id).where(
            Manager.status == True,
            Manager.tg_id.isnot(None)
        )
        managers_result = await session.execute(managers_query)
        managers_ids = managers_result.scalars().all()

        # Объединение и удаление дубликатов
        all_ids = set(ADMIN_IDS) | set(managers_ids)
        return list(all_ids)


async def get_active_admins_managers_sb_tg_ids() -> list[int]:
    """
    Получает список Telegram ID всех активных администраторов и менеджеров.

    Returns:
        list[int]: Список уникальных Telegram ID
    """
    async with AsyncSessionLocal() as session:

        # Запрос для менеджеров (статус True и заполненный tg_id)
        managers_query = select(Manager.tg_id).where(
            Manager.status == True,
            Manager.tg_id.isnot(None)
        )
        managers_result = await session.execute(managers_query)
        managers_ids = managers_result.scalars().all()

        security_query = select(Security.tg_id).where(
            Security.status == True,
            Security.tg_id.isnot(None)
        )
        security_result = await session.execute(security_query)
        security_ids = security_result.scalars().all()

        # Объединение и удаление дубликатов
        all_ids = set(ADMIN_IDS) | set(managers_ids) | set(security_ids)
        return list(all_ids)

text_warning = '''
Уважаемые резиденты и подрядчики коттеджного поселка Ели Estate 🌲

🌲 резидент или подрядчик обязан встретить и сопроводить машину от ворот до пункта назначения. Иначе машина не заедет на территорию 

🌲грузовая машина выезжая с участка резидента, обязана вымыть свои колеса от грязи/песка/глины/земли. В противном случае, УК вправе выставить счет за загрязнение дороги

С уважением, УК Ели Estate 🌲
'''