import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()


def get_optional_int_env(name: str):
    val = os.getenv(name)
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


# ============================================
# Глобальные параметры
# ============================================

ALERT_CHAT = os.getenv("ALERT_CHAT", "@kz_monitor_alerts")
DATABASE_NAME = os.getenv("DATABASE_NAME", "kz_drug_shops.db")

CHECK_INTERVAL = get_optional_int_env("CHECK_INTERVAL") or 3600
MAX_PARTICIPANTS = get_optional_int_env("MAX_PARTICIPANTS") or 100

# ЧТЕНИЕ ВСЕХ АККАУНТОВ ИЗ .env
# ============================================

def load_accounts_from_env():
    accounts = {}

    for key, value in os.environ.items():
        match = re.match(r"ACCOUNT_(\d+)_(SESSION|PHONE|API_ID|API_HASH)$", key)
        if match:
            num, field = match.groups()
            num = int(num)

            if num not in accounts:
                accounts[num] = {}

            # Приводим API_ID к int
            if field == "API_ID":
                try:
                    value = int(value)
                except:
                    raise ValueError(f"API_ID аккаунта {num} должен быть числом")

            accounts[num][field] = value

    # Конвертируем словарь {1:{...},2:{...}} → список [{...},{...}]
    result = []
    for num in sorted(accounts.keys()):
        acc = accounts[num]
        required_fields = ("SESSION", "PHONE", "API_ID", "API_HASH")
        for f in required_fields:
            if f not in acc:
                raise ValueError(f"В аккаунте #{num} не хватает поля {f}")
        result.append(acc)

    if not result:
        raise ValueError("В .env не найдено ни одного аккаунта ACCOUNT_X_...")

    return result


ACCOUNTS = load_accounts_from_env()


# ============================================
# ЛОГИРОВАНИЕ
# ============================================

class UnicodeSafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            msg = self.format(record).encode("ascii", "ignore").decode("ascii")
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("monitor.log", encoding="utf-8"),
        UnicodeSafeStreamHandler(),
    ],
)

print("✅ All configuration loaded from .env successfully")