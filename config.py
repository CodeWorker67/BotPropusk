from dotenv import load_dotenv
import os
from typing import Optional

load_dotenv()

TG_TOKEN = os.environ.get("TG_TOKEN")
PAGE_SIZE = int(os.environ.get("PAGE_SIZE"))
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS").split()}
MAX_TRUCK_PASSES = int(os.environ.get("MAX_TRUCK_PASSES", "0"))
# Картинка с типами ТС при выборе грузовой категории (можно переопределить в .env)
_DEFAULT_TRUCK_CAT_PHOTO = (
    "AgACAgIAAxkBAAEB6o1p4Jgp576n4Wu2R2zlHwWJwNSDDQACohNrG7QlAAFL9OZ90Vt4Ri8BAAMCAANzAAM7BA"
)
TRUCK_CATEGORIES_PHOTO_FILE_ID: Optional[str] = (
    (os.environ.get("TRUCK_CATEGORIES_PHOTO_FILE_ID") or "").strip() or _DEFAULT_TRUCK_CAT_PHOTO
)
MAX_CAR_PASSES = int(os.environ.get("MAX_CAR_PASSES"))
PASS_TIME = int(os.environ.get("PASS_TIME"))
FUTURE_LIMIT = int(os.environ.get("FUTURE_LIMIT"))
RAZRAB = int(os.environ.get("RAZRAB"))
# ЮKassa (магазин): SHOP_ID и SECRET_KEY из .env
YUKASSA_SHOP_ID: Optional[str] = os.environ.get("SHOP_ID") or os.environ.get("YUKASSA_SHOP_ID")
YUKASSA_SECRET_KEY: Optional[str] = os.environ.get("SECRET_KEY") or os.environ.get("YUKASSA_SECRET_KEY")
YUKASSA_RETURN_URL: str = os.environ.get(
    "YUKASSA_RETURN_URL",
    "https://yookassa.ru",
).strip() or "https://yookassa.ru"

# Чек в запросе создания платежа (54-ФЗ): код ставки НДС по справочнику ЮKassa (1 — без НДС и т.д.)
YUKASSA_RECEIPT_VAT_CODE: int = int(os.environ.get("YUKASSA_RECEIPT_VAT_CODE", "1"))
# Код системы налогообложения (1–6); задайте, если касса/личный кабинет требуют receipt.tax_system_code
_raw_tax_sys = os.environ.get("YUKASSA_RECEIPT_TAX_SYSTEM_CODE", "").strip()
YUKASSA_RECEIPT_TAX_SYSTEM_CODE: Optional[int] = int(_raw_tax_sys) if _raw_tax_sys.isdigit() else None

# Тестовая цена грузового пропуска для выбранных Telegram user id (как SPECIAL_PASS_MAX_USER_IDS в Eli)
_raw_spec_tg = os.environ.get("SPECIAL_PASS_TG_USER_IDS", "").strip()
SPECIAL_PASS_TG_USER_IDS: frozenset[int] = frozenset(
    int(x.strip()) for x in _raw_spec_tg.split(",") if x.strip().isdigit()
)
SPECIAL_PASS_PRICE_RUBLES: int = int(os.environ.get("SPECIAL_PASS_PRICE_RUBLES", "10"))
# Телефоны резидентов (нормализуются до 8XXXXXXXXXX), для них тариф грузового пропуска = SPECIAL_PASS_PRICE_RUBLES
SPECIAL_PASS_RESIDENT_PHONES_RAW: str = os.environ.get(
    "SPECIAL_PASS_RESIDENT_PHONES", "89655770768"
).strip()