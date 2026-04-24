"""Текст уведомлений СБ / менеджерам / админам об автоодобренных временных пропусках."""

from __future__ import annotations

from datetime import date

from temporary_truck import TRUCK_CATEGORY_LABELS, temp_pass_last_valid_date


def build_auto_approved_staff_notice(
    *,
    header_line: str,
    vehicle_type: str | None,
    weight_category: str | None = None,
    length_category: str | None = None,
    cargo_type: str | None = None,
    car_brand: str | None = None,
    car_model: str | None = None,
    car_number: str | None = None,
    visit_date: date | None = None,
    purpose: str | None = None,
    payment_rubles: int | None = None,
) -> str:
    """Собирает многострочное сообщение; пустые поля не добавляются."""
    lines: list[str] = [header_line.rstrip()]

    cat = _category_line(vehicle_type, weight_category, length_category)
    if cat:
        lines.append(f"Категория ТС — {cat}")

    vtype = _vehicle_type_line(vehicle_type, cargo_type)
    if vtype:
        lines.append(f"Тип ТС — {vtype}")

    if payment_rubles is not None:
        lines.append(f"Оплата — {payment_rubles} руб")

    model = (car_model or "").strip()
    if model:
        lines.append(f"Модель — {model}")

    brand = (car_brand or "").strip()
    if brand:
        lines.append(f"Марка — {brand}")

    number = (car_number or "").strip()
    if number:
        lines.append(f"Номер — {number.upper()}")

    date_line = _visit_or_period_line(visit_date, purpose)
    if date_line:
        lines.append(date_line)

    return "\n".join(lines)


def _category_line(
    vehicle_type: str | None,
    weight_category: str | None,
    length_category: str | None,
) -> str | None:
    if vehicle_type != "truck":
        return None
    wc = (weight_category or "").strip()
    if wc in TRUCK_CATEGORY_LABELS:
        return wc
    parts: list[str] = []
    if wc == "light":
        parts.append("тоннаж ≤ 12 т")
    elif wc == "heavy":
        parts.append("тоннаж > 12 т")
    lc = (length_category or "").strip()
    if lc == "short":
        parts.append("длина ≤ 7 м")
    elif lc == "long":
        parts.append("длина > 7 м")
    if not parts:
        return None
    return ", ".join(parts)


def _vehicle_type_line(vehicle_type: str | None, cargo_type: str | None) -> str | None:
    """Для легковых строку не показываем (по требованию)."""
    if vehicle_type != "truck":
        return None
    cargo = (cargo_type or "").strip()
    if cargo:
        return f"Грузовой ({cargo})"
    return "Грузовой"


def _visit_or_period_line(visit_date: date | None, purpose: str | None) -> str | None:
    if visit_date is None:
        return None
    p = str(purpose or "").strip()
    if not p.isdigit():
        return f"Дата приезда — {visit_date.strftime('%d.%m.%Y')}"
    last = temp_pass_last_valid_date(visit_date, p)
    if last <= visit_date:
        return f"Дата приезда — {visit_date.strftime('%d.%m.%Y')}"
    return (
        f"Период действия — {visit_date.strftime('%d.%m.%Y')} — {last.strftime('%d.%m.%Y')}"
    )
