import time
import json
import logging
from pathlib import Path
from typing import Any

import requests

from etl.config import (
    OPENDOTA_URL, OPENDOTA_API_KEY, ACCOUNT_ID,
    REQUEST_DELAY, MATCHES_LIMIT, LOBBY_TYPE_RANKED,
    RAW_MATCHES_DIR, HEROES_FILE,
)

# Справочник героев обновляем не чаще раза в месяц: Valve добавляет героев редко
# но матч с неизвестным hero_id упадёт на внешнем ключе heroes(hero_id)
HEROES_MAX_AGE_DAYS = 30

def _get_params(extra_params: dict | None = None) -> dict:
    params = extra_params or {}
    if OPENDOTA_API_KEY:
        params["api_key"] = OPENDOTA_API_KEY
    return params

def _heroes_file_is_fresh() -> bool:
    if not HEROES_FILE.exists():
        return False
    age_seconds = time.time() - HEROES_FILE.stat().st_mtime
    return age_seconds < HEROES_MAX_AGE_DAYS * 86400

#скачиваем данные о героях(через локальный файл если есть, тю.к. запросы переодически недлоступны)
#изменения: добалена функция для проверки актуальности файла
def fetch_and_save_heroes() -> bool:
    if _heroes_file_is_fresh():
            logging.info("Справочник героев актуален: %s", HEROES_FILE)
            return True

    url = f"{OPENDOTA_URL}/heroes"
    try:
        response = requests.get(url, params=_get_params(), timeout=60)
        response.raise_for_status()
        heroes_data = response.json()
    except requests.exceptions.RequestException as err:
        logging.error("Ошибка при скачивании героев: %s", err)
        if HEROES_FILE.exists():
            logging.warning("Использую устаревший локальный справочник героев")
            return True
        return False
    
    save_raw_json(heroes_data, HEROES_FILE)
    logging.info("Справочник героев обновлён: %s", HEROES_FILE)
    return True


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
def request_match_parse(match_id: int, retries: int = 3, wait: int = 45) -> dict[str, Any]:
    url = f"{OPENDOTA_URL}/request/{match_id}"
    try:
        requests.post(url, params=_get_params(), timeout=45)
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

#сохраним данные о матче, 
#изменения: теперь сохраняем во временный файл, чтобы при обрыве записи на диске не останется битого JSON
def save_raw_json(data: dict | list, filepath: Path) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
    
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    tmp_path.replace(filepath)

#скачиваем данные о матчах игрока
def fetch_and_save_player_matches(account_id: int = ACCOUNT_ID, limit: int = MATCHES_LIMIT) -> list[Path]:
    url = f"{OPENDOTA_URL}/players/{account_id}/matches"
    params = _get_params({"limit": limit, "lobby_type": LOBBY_TYPE_RANKED})
    
    try:
        response = requests.get(url, params=params, timeout=45)
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
#изменения: теперь возвращаем результат для праильного etl, поскольку AIRFlow должен иметь передавал возвращенное значение
def run_extract(account_id: int | None = None, limit: int = MATCHES_LIMIT) -> list[Path]:
    logging.info("ETL этап 1: извлечение данных")

    if OPENDOTA_API_KEY:
        logging.info("OpenDota: используется API-ключ")
    else:
        logging.info("OpenDota: работаем без ключа (60 req/min)")

    # шаг 1: Загрузка справочника героев
    if not fetch_and_save_heroes():
        raise SystemExit("Ошибка загрузки героев")

    # Шаг 2: Скачивание личных игр одного игрока
    account_id = account_id or ACCOUNT_ID
    logging.info("Скачивание матчей для account_id=%s", account_id)

    saved_files = fetch_and_save_player_matches(account_id=account_id, limit=limit)
    logging.info("Успешно обработано и сохранено файлов: %d", len(saved_files))

    return saved_files


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_extract()