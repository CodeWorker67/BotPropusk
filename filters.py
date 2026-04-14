from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from typing import Union
from sqlalchemy import select

from config import ADMIN_IDS
from db.models import (
    AsyncSessionLocal,
    Manager,
    Security,
    Resident,
    Contractor
)


class IsAdmin(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        return event.from_user.id in ADMIN_IDS


class IsAdminOrManager(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id

        # Проверка на администратора
        if user_id in ADMIN_IDS:
            return True

        # Проверка на менеджера
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Manager)
                .where(
                    Manager.tg_id == user_id,
                    Manager.status == True
                )
            )
            return result.scalar() is not None


class IsManager(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Manager)
                .where(
                    Manager.tg_id == user_id,
                    Manager.status == True
                )
            )
            return result.scalar() is not None


class IsSecurity(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Security)
                .where(
                    Security.tg_id == user_id,
                    Security.status == True
                )
            )
            return result.scalar() is not None


class IsResident(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Resident)
                .where(
                    Resident.tg_id == user_id,
                    Resident.status == True
                )
            )
            return result.scalar() is not None


class IsContractor(BaseFilter):
    async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
        user_id = event.from_user.id
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Contractor)
                .where(
                    Contractor.tg_id == user_id,
                    Contractor.status == True
                )
            )
            return result.scalar() is not None