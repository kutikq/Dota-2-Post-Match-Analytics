import logging
import os

from dotenv import load_dotenv

from etl.extract import fetch_and_save_heroes, fetch_and_save_player_matches, MATCHES_LIMIT
from etl.transform import transform_heroes, run_transform_file, RAW_MATCHES_DIR
from etl.load import load_heroes, load_match_bundle, get_existing_match_ids, heroes_already_loaded

# Глобальные переменные и загрузка контекста
load_dotenv()
logging.basicConfig(level=logging.INFO)

ACCOUNT_ID = os.getenv("ACCOUNT_ID")


def run():
    if not ACCOUNT_ID:
        raise SystemExit("ACCOUNT_ID не задан в .env файле")

    account_id = int(ACCOUNT_ID)

    # EXTRACT 
    logging.info("ETL: extract")
    if not fetch_and_save_heroes():
        raise SystemExit("Не удалось загрузить героев — прерываю")

    fetch_and_save_player_matches(account_id=account_id, limit=MATCHES_LIMIT)

    # 2. загрузка героев (только если их ещё нет в БД)
    if heroes_already_loaded():
        logging.info("Герои уже загружены в БД, пропускаю")
    else:
        logging.info("ETL: load heroes")
        heroes = transform_heroes()
        load_heroes(heroes)
        logging.info("Героев загружено: %d", len(heroes))

    # 3. TRANSFORM + LOAD матчей, пропуская уже загруженные
    logging.info("=== ETL: load matches ===")
    existing_ids = get_existing_match_ids()
    files = list(RAW_MATCHES_DIR.glob("*.json"))

    new_count = 0
    for file in files:
        match_id = int(file.stem)
        if match_id in existing_ids:
            logging.info("Матч %s уже в БД, пропускаю", match_id)
            continue

        bundle = run_transform_file(file)
        if bundle:
            load_match_bundle(bundle)
            new_count += 1
            logging.info("Матч %s загружен", match_id)

    logging.info("Готово. Новых матчей загружено: %d из %d файлов", new_count, len(files))


if __name__ == "__main__":
    run()