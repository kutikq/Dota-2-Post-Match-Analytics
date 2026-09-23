import logging


from etl.config import MATCHES_LIMIT,ACCOUNT_ID
from etl.extract import run_extract
from etl.transform import transform_heroes, run_transform_file
from etl.load import load_heroes, load_match_bundle, get_existing_match_ids

def run_etl(account_id: int | None = None, limit: int = MATCHES_LIMIT) -> int:
    # Extract
    saved_files = run_extract(account_id=account_id, limit=limit)

    # Справочник героев 
    heroes = transform_heroes()
    load_heroes(heroes)
    logging.info("Справочник героев загружен: %d записей", len(heroes))

    # Transform + Load только тех матчей, которых нет в БД
    existing_ids = get_existing_match_ids()
    logging.info("Матчей в БД: %d", len(existing_ids))

    loaded = 0
    for filepath in saved_files:
        match_id = int(filepath.stem)

        if match_id in existing_ids:
            continue

        bundle = run_transform_file(filepath)
        if not bundle:
            logging.warning("Матч %s не удалось трансформировать, пропускаю", match_id)
            continue

        load_match_bundle(bundle)
        loaded += 1
        logging.info("Матч %s загружен", match_id)

    logging.info("ETL завершён. Новых матчей загружено: %d", loaded)
    return loaded


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    run_etl()