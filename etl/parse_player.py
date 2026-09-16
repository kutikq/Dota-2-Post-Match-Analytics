import os
import time
import logging
import requests
from typing import Any
from dotenv import load_dotenv
from db import save_all, fetch_and_save_heroes
import json
from pathlib import Path

CACHE_FILE = Path("etl/cache_matches.json")

#Глобальные переменные для парсинга
load_dotenv()   #загружаем данные из окружения для авториации

logging.basicConfig(level=logging.INFO)

OPENDOTA_URL = "https://api.opendota.com/api"
OPENDOTA_API_KEY = os.getenv("OPENDOTA_API_KEY")  # если парсить большие данные можно авторизоваться и проводить большие загрузки(платтно)
ACCOUNT_ID = os.getenv("ACCOUNT_ID")    #id пользователя которого ьудем парсить
REQUEST_DELAY = 1.1 #у OpenDota лимит на 60 запросов в минуту
MATCHES_LIMIT = 10
LOBBY_TYPE_RANKED = 7   #пока что реализуем только для ренйтинговых матчей

def get_player_matches(account_id: int = ACCOUNT_ID, limit: int = MATCHES_LIMIT) -> list[dict[str, Any]]:
    url = f"{OPENDOTA_URL}/players/{account_id}/matches"
    param = {"limit": limit, "lobby_type": LOBBY_TYPE_RANKED}
    if OPENDOTA_API_KEY:
        param["api_key"] = OPENDOTA_API_KEY
    try:
        response = requests.get(url, params=param, timeout=60)
        response.raise_for_status()  #ошибка при статусе
        
        return response.json()

    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при запросе к матчам игрока: %s", err)
        return []

def get_match_details(match_id: int) -> dict[str, Any]:
    url = f"{OPENDOTA_URL}/matches/{match_id}"
    param = {}
    if OPENDOTA_API_KEY:
        param["api_key"] = OPENDOTA_API_KEY
    try:
        response = requests.get(url, params=param,  timeout=60)
        response.raise_for_status()  
        
        return response.json()

    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при запросе парсинга матча: %s", err)
        return {}

# Спарсив матч, можем получить раскладку по таймингам, например gold_t в котором будет расписан золото по минутам
# поэтому будем проверять его для подтверждения парсинга
def is_parsed(match: dict[str, Any]) -> bool:
    players = match.get("players") or []
    return bool(players) and players[0].get("gold_t") is not None

# Запрашиваем парсинг реплея на серверах OpenDota
def request_match_parse(match_id: int, retries: int = 3, wait: int = 60) -> dict[str, Any]:
    url = f"{OPENDOTA_URL}/request/{match_id}"
    params = {}
    if OPENDOTA_API_KEY:
        params["api_key"] = OPENDOTA_API_KEY
    
    try:
        requests.post(url, params=params, timeout=60)
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

# Сама функция парсинга матчей по игроку
def fetch_player_matches(account_id: int) -> list[dict[str, Any]]:
    logging.info("Получаю список матчей для account_id=%s", account_id)
    matches = get_player_matches(account_id)
    logging.info("Найдено матчей: %d", len(matches))

    parsed_matches = []

    for m in matches:
        match_id = m["match_id"]
        logging.info("Матч %s: получаю детали...", match_id)
        details = get_match_details(match_id)
        time.sleep(REQUEST_DELAY)

        if not is_parsed(details):
            logging.warning("Матч %s не запаршен, запрашиваю парсинг...", match_id)
            details = request_match_parse(match_id)
            if not details:
                continue

        parsed_matches.append(details)

    logging.info("Запаршенных матчей: %d из %d", len(parsed_matches), len(matches))
    return parsed_matches

def main():
    if not ACCOUNT_ID:
        raise SystemExit("ACCOUNT_ID не задан")

    account_id = int(ACCOUNT_ID)

    if not fetch_and_save_heroes():
        raise SystemExit("Не удалось загрузить героев — прерываю")

    if CACHE_FILE.exists():
        logging.info("Загружаю матчи из кэша...")
        with open(CACHE_FILE) as f:
            matches = json.load(f)
    else:
        logging.info("Запуск парсинга для account_id=%s", account_id)
        matches = fetch_player_matches(account_id)
        with open(CACHE_FILE, "w") as f:
            json.dump(matches, f)

    logging.info("Готово. Запаршено матчей: %d", len(matches))

    for match in matches:
        logging.info(
            "match_id=%s duration=%s radiant_win=%s",
            match["match_id"],
            match["duration"],
            match["radiant_win"],
        )
        save_all(match, account_id)


if __name__ == "__main__":
    main()