import os
import time
import json
import logging
from pathlib import Path
from typing import Any
import requests
from dotenv import load_dotenv

#загружаем данные из окружения для авториации
load_dotenv()

# для отладки работы отображение логов
logging.basicConfig(level=logging.INFO)


#Глобальные переменные для парсинга
OPENDOTA_URL = "https://api.opendota.com/api"
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY")  # если парсить большие данные можно авторизоваться и проводить большие загрузки(платтно)
ACCOUNT_ID = os.getenv("ACCOUNT_ID")    #id пользователя которого ьудем парсить
REQUEST_DELAY = 1.1 #у OpenDota лимит на 60 запросов в минуту
MATCHES_LIMIT = 10
LOBBY_TYPE_RANKED = 7   #пока что реализуем только для ренйтинговых матчей

# Директории для хранения raw-данных
RAW_DIR = Path("data/raw")
HEROES_FILE = RAW_DIR / "heroes.json"
RAW_MATCHES_DIR = Path("data/raw/matches")  #будем сохранять данные о матчах для бэкапа и сокращения кол-ва запросов

def _get_params(extra_params: dict | None = None) -> dict:
    params = extra_params or {}
    if OPENDOTA_API_KEY:
        params["api_key"] = OPENDOTA_API_KEY
    return params

#скачиваем данные о героях(через локальный файл если есть, тю.к. запросы переодически недлоступны)
def fetch_and_save_heroes() -> bool:
    if HEROES_FILE.exists():
        logging.info("Справочник героев уже существует локально: %s", HEROES_FILE)
        return True

    url = f"{OPENDOTA_URL}/heroes"
    try:
        response = requests.get(url, params=_get_params(), timeout=60)
        response.raise_for_status()
        heroes_data = response.json()
        
        with open(HEROES_FILE, "w", encoding="utf-8") as f:
            json.dump(heroes_data, f, ensure_ascii=False, indent=2)
            
        logging.info("Справочник героев успешно сохранен в %s", HEROES_FILE)
        return True
    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при скачивании героев: %s", err)
        return False


# Спарсив матч, можем получить раскладку по таймингам, например gold_t в котором будет расписан золото по минутам
# поэтому будем проверять его для подтверждения парсинга
def is_parsed(match: dict[str, Any]) -> bool:
    players = match.get("players") or []
    if not players:
        return False
    
    has_gold_t = players[0].get("gold_t") is not None
    bench = players[0].get("benchmarks") or {}
    has_benchmarks = bool(bench.get("gold_per_min"))
    
    return has_gold_t and has_benchmarks

#скачиваем данные матче(в нём хранятся все нужные нам вкладки)
def get_match_details(match_id: int) -> dict[str, Any]:
    url = f"{OPENDOTA_URL}/matches/{match_id}"
    try:
        response = requests.get(url, params=_get_params(), timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при запросе матча %s: %s", match_id, err)
        return {}

# Запрашиваем парсинг реплея на серверах OpenDota
def request_match_parse(match_id: int, retries: int = 3, wait: int = 60) -> dict[str, Any]:
    url = f"{OPENDOTA_URL}/request/{match_id}"
    try:
        requests.post(url, params=_get_params(), timeout=60)
        logging.info("Запрошен парсинг матча %s", match_id)
    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при запросе парсинга: %s", err)
        return {}

    # Ждём и проверяем до retries раз
    for attempt in range(1, retries + 1):
        logging.info("Ожидание парсинга матча %s (попытка %d/%d)...", match_id, attempt, retries)
        time.sleep(wait)

        details = get_match_details(match_id)
        if is_parsed(details):
            logging.info("Матч %s успешно запаршен", match_id)
            return details
        
        logging.warning("Матч %s ещё не готов", match_id)

    logging.warning("Матч %s не запаршен за %d попыток, пропускаю", match_id, retries)
    return {}

#сохраним данные о матче
def save_raw_json(data: dict, filepath: Path) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

#скачиваем данные о матчах игрока
def fetch_and_save_player_matches(account_id: int = ACCOUNT_ID, limit: int = MATCHES_LIMIT) -> list[Path]:
    url = f"{OPENDOTA_URL}/players/{account_id}/matches"
    params = _get_params({"limit": limit, "lobby_type": LOBBY_TYPE_RANKED})
    
    try:
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        matches_list = response.json()
    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при запросе к матчам игрока: %s", err)
        return []

    saved_files = []
    for m in matches_list:
        match_id = m["match_id"]
        filepath = RAW_MATCHES_DIR / f"{match_id}.json"
        
        if filepath.exists():
            logging.info("Матч %s уже сохранен локально", match_id)
            saved_files.append(filepath)
            continue

        logging.info("Матч %s: получаю детали...", match_id)
        details = get_match_details(match_id)
        time.sleep(REQUEST_DELAY)

        if not is_parsed(details):
            logging.warning("Матч %s не запаршен, запрашиваю парсинг...", match_id)
            details = request_match_parse(match_id)
            if not details:
                continue

        save_raw_json(details, filepath)
        saved_files.append(filepath)

    return saved_files

#функция для запуска 
def run_extract():
    if not ACCOUNT_ID:
        raise SystemExit("ACCOUNT_ID не задан в .env файле")

    logging.info("ETL этап 1: извлечение данных")
    
    # шаг 1: Загрузка справочника героев
    if not fetch_and_save_heroes():
        raise SystemExit("Ошибка загрузки героев")

    # Шаг 2: Скачивание личных игр одного игрока
    account_id = int(ACCOUNT_ID)
    logging.info(f"Скачивание матчей для account_id={account_id}")
    saved_files = fetch_and_save_player_matches(account_id=account_id, limit=MATCHES_LIMIT)
    logging.info(f"Успешно обработано и сохранено файлов: {len(saved_files)}")


if __name__ == "__main__":
    run_extract()