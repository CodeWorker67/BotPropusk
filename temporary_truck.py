"""Категории грузового временного пропуска (новый сценарий; purpose — ключ длительности как у легковых)."""

from __future__ import annotations

import html as html_lib
from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    SPECIAL_PASS_PRICE_RUBLES,
    SPECIAL_PASS_RESIDENT_PHONES_RAW,
    SPECIAL_PASS_TG_USER_IDS,
)

TEMP_PASS_VEHICLE_TYPE_PROMPT = (
    "❗️❗️❗️Внимание❗️❗️❗️\n"
    "Газели и фургоны с грузом до 3,5 тонн оформляются как легковая машина.\n"
    "Выберите тип машины:"
)

TRUCK_CATEGORY_LABELS: list[str] = [
    "Грузы до 5т",
    "Грузы до 10т",
    "Самосвал до 10м3",
    "Автокран до 5т",
    "Автокран до 10т",
    "Автокран до 25т",
    "Автокран до 40т",
    "Бетон до 5м3",
    "Бетон до 8м3",
    "Автобетононасос",
    "Спецтехника",
]

DCT_PRICE: dict[str, int] = {
    "Грузы до 5т": 1200,
    "Грузы до 10т": 1700,
    "Самосвал до 10м3": 1200,
    "Автокран до 5т": 700,
    "Автокран до 10т": 1200,
    "Автокран до 25т": 1700,
    "Автокран до 40т": 2500,
    "Бетон до 5м3": 1200,
    "Бетон до 8м3": 2300,
    "Автобетононасос": 1700,
    "Спецтехника": 700,
}

PAYLOAD_PREFIX_RC = "truck_cat"
PAYLOAD_PREFIX_SELF = "self_truck_cat"


def _normalize_ru_phone_digits(raw: str | None) -> str | None:
    if not raw:
        return None
    d = "".join(c for c in raw if c.isdigit())
    if len(d) == 11 and d[0] == "7":
        return "8" + d[1:]
    if len(d) == 10:
        return "8" + d
    return d if d else None


def _parse_special_resident_phones(raw: str) -> frozenset[str]:
    out: set[str] = set()
    for part in raw.split(","):
        p = _normalize_ru_phone_digits(part.strip())
        if p:
            out.add(p)
    return frozenset(out)


SPECIAL_PASS_RESIDENT_PHONES: frozenset[str] = _parse_special_resident_phones(
    SPECIAL_PASS_RESIDENT_PHONES_RAW
)


def truck_pass_price_rubles(
    *,
    payer_tg_user_id: int | None = None,
    payer_phone: str | None = None,
    weight_category: str,
) -> int | None:
    base = DCT_PRICE.get(weight_category)
    if base is None:
        return None
    pn = _normalize_ru_phone_digits(payer_phone)
    if pn and pn in SPECIAL_PASS_RESIDENT_PHONES:
        return SPECIAL_PASS_PRICE_RUBLES
    if payer_tg_user_id is not None and payer_tg_user_id in SPECIAL_PASS_TG_USER_IDS:
        return SPECIAL_PASS_PRICE_RUBLES
    return base


def truck_category_markup(prefix: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i, label in enumerate(TRUCK_CATEGORY_LABELS, start=1):
        rows.append(
            [InlineKeyboardButton(text=f"{i}. {label}", callback_data=f"{prefix}_{i}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_from_truck_callback_data(data: str, prefix: str) -> str | None:
    if not data.startswith(f"{prefix}_"):
        return None
    try:
        idx = int(data.rsplit("_", 1)[-1])
    except ValueError:
        return None
    if 1 <= idx <= len(TRUCK_CATEGORY_LABELS):
        return TRUCK_CATEGORY_LABELS[idx - 1]
    return None


def is_new_truck_pass(tp) -> bool:
    if tp.vehicle_type != "truck":
        return False
    wc = (tp.weight_category or "").strip()
    if wc in TRUCK_CATEGORY_LABELS:
        return True
    return (tp.purpose or "") == "0"


def temp_pass_duration_label(purpose: str | None) -> str:
    p = purpose or ""
    if p in ("6", "13", "29"):
        return f"{int(p) + 1} дней\n"
    if p == "1":
        return "2 дня\n"
    return "1 день\n"


def new_truck_vehicle_block_html(tp) -> str:
    cat = html_lib.escape(str(tp.weight_category or ""))
    brand = html_lib.escape(str(tp.car_brand or ""))
    num = html_lib.escape(str(tp.car_number or ""))
    vd = tp.visit_date.strftime("%d.%m.%Y") if tp.visit_date else ""
    oc = html_lib.escape(str(tp.owner_comment or "нет"))
    sb = html_lib.escape(str(tp.security_comment or "нет"))
    return (
        f"Категория: {cat}\n"
        f"Марка: {brand}\n"
        f"Номер: {num}\n"
        f"Дата визита: {vd}\n"
        f"Комментарий владельца: {oc}\n"
        f"📝 Комментарий для СБ: {sb}\n"
    )


def new_truck_price_line_html(
    tp,
    payer_tg_user_id: int | None = None,
    payer_phone: str | None = None,
) -> str:
    cat = tp.weight_category or ""
    price = truck_pass_price_rubles(
        payer_tg_user_id=payer_tg_user_id,
        payer_phone=payer_phone,
        weight_category=cat,
    )
    if price is None:
        return ""
    return f"Тариф: {price} ₽\n"


def security_new_truck_core_html(tp) -> str:
    return f"🚗 Тип ТС: Грузовой\n{new_truck_vehicle_block_html(tp)}"


def _days_from_purpose(purpose) -> int:
    d = str(purpose or "")
    if d.isdigit():
        return int(d)
    return 1


def temp_pass_last_valid_date(visit_date: date, purpose: str | None) -> date:
    """Последний календарный день действия (как в handlers_security для approved)."""
    return visit_date + timedelta(days=_days_from_purpose(purpose))


def approved_temp_search_card_html(
    temp_pass,
    header_html: str,
    *,
    include_destination: bool = False,
) -> str:
    """Карточка действующего временного пропуска (поиск по номеру / цифрам / участку)."""
    if is_new_truck_pass(temp_pass):
        return header_html + security_new_truck_core_html(temp_pass)

    days = _days_from_purpose(temp_pass.purpose)
    p = str(temp_pass.purpose or "")
    if p in ("6", "13", "29"):
        value = f"{int(p) + 1} дней\n"
    elif p == "1":
        value = "2 дня\n"
    else:
        value = "1 день\n"

    end_d = temp_pass.visit_date + timedelta(days=days)
    dest_line = ""
    if include_destination:
        dest_line = f"🏠 Место назначения: {html_lib.escape(str(temp_pass.destination or ''))}\n"

    return (
        header_html
        + f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
        + f"🔢 Номер: {html_lib.escape(str(temp_pass.car_number or ''))}\n"
        + f"🚙 Марка: {html_lib.escape(str(temp_pass.car_brand or ''))}\n"
        + f"📦 Тип груза: {html_lib.escape(str(temp_pass.cargo_type or ''))}\n"
        + dest_line
        + f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
        + f"{end_d.strftime('%d.%m.%Y')}\n"
        + f"Действие пропуска: {value}"
        + f"💬 Комментарий владельца: {html_lib.escape(str(temp_pass.owner_comment or 'нет'))}\n"
        + f"📝 Комментарий для СБ: {html_lib.escape(str(temp_pass.security_comment or 'нет'))}"
    )
