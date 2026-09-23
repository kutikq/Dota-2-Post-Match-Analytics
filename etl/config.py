# конфигурация проекта: пути, переменные окружения, подключение к БД

# Импорты
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
import logging

#загружаем данные из окружения для авториации
load_dotenv()

# Директории для хранения raw-данных
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
RAW_MATCHES_DIR = RAW_DIR / "matches"
HEROES_FILE = RAW_DIR / "heroes.json"

RAW_MATCHES_DIR.mkdir(parents=True, exist_ok=True)

#Глобальные переменные для парсинга
OPENDOTA_URL = "https://api.opendota.com/api"
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY")  # если парсить большие данные можно авторизоваться и проводить большие загрузки(платтно)
REQUEST_DELAY = 1.1 #у OpenDota лимит на 60 запросов в минуту
MATCHES_LIMIT = 10
LOBBY_TYPE_RANKED = 7   #пока что реализуем только для рейтинговых матчей

# функция для провеки корректности .env файла
def load_env_vars(required: list[str], integers: list[str] | None = None) -> dict[str, str | int]:
    integers = integers or []
    values: dict[str, str | int] = {}
    errors: list[str] = []

    for name in required:
        raw = os.getenv(name)

        if not raw:
            errors.append(f"{name} — не задана")
            continue

        if name in integers:
            try:
                values[name] = int(raw)
            except ValueError:
                errors.append(f"{name} — ожидалось число, получено {raw!r}")
        else:
            values[name] = raw

    if errors:
        raise RuntimeError(
            "Проблемы с переменными окружения (.env):\n  " + "\n  ".join(errors)
        )

    return values

# глобальные переменные для создания обращений к серверу БД
ENV = load_env_vars(
    required=[ "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER",
               "POSTGRES_PASSWORD", "POSTGRES_DB", "ACCOUNT_ID",
    ],
    integers=["POSTGRES_PORT", "ACCOUNT_ID"],
)

DRIVER = "postgresql+psycopg2"
HOST     = ENV["POSTGRES_HOST"]
PORT     = ENV["POSTGRES_PORT"]
USER     = ENV["POSTGRES_USER"]
PASS     = ENV["POSTGRES_PASSWORD"]
DB_NAME  = ENV["POSTGRES_DB"]
ACCOUNT_ID = ENV["ACCOUNT_ID"]

DATABASE_URL = f"{DRIVER}://{USER}:{PASS}@{HOST}:{PORT}/{DB_NAME}"

# создание обращения к БД
engine = create_engine(DATABASE_URL, pool_pre_ping=True)