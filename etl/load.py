import os
import logging
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from etl.transform import run_transform_file, transform_heroes
from pathlib import Path

# Глобальные переменные
load_dotenv()   # загружаем данные из окружения для авторизации

logging.basicConfig(level=logging.INFO)

OPENDOTA_URL = "https://api.opendota.com/api"
DRIVER = "postgresql+psycopg2"
HOST = os.getenv('POSTGRES_HOST')
PORT = os.getenv('POSTGRES_PORT')
USER = os.getenv('POSTGRES_USER')
PASS = os.getenv('POSTGRES_PASSWORD')
DB_NAME = os.getenv('POSTGRES_DB')
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

engine = create_engine(f"{DRIVER}://{USER}:{PASS}@{HOST}:{PORT}/{DB_NAME}")

# Универсальная функция вставки
def bulk_insert(conn, table: str, data: list[dict] | dict, conflict_target: str, do_update: bool = False):
    if not data:
        return

    rows = [data] if isinstance(data, dict) else data
    keys = list(rows[0].keys())

    cols = ", ".join(keys)
    placeholders = ", ".join(f":{k}" for k in keys)

    conflict_action = "DO NOTHING"
    if do_update:
        update_set = ", ".join([f"{k} = EXCLUDED.{k}" for k in keys if k != conflict_target])
        conflict_action = f"DO UPDATE SET {update_set}"

    query = text(f"""
        INSERT INTO {table} ({cols}) 
        VALUES ({placeholders}) 
        ON CONFLICT ({conflict_target}) {conflict_action}
    """)

    conn.execute(query, rows)


def load_heroes(heroes_data: list[dict]):
    if not heroes_data:
        return
    with engine.begin() as conn:
        bulk_insert(conn, "heroes", heroes_data, conflict_target="hero_id", do_update=True)


def load_match_bundle(bundle: dict):
    if not bundle:
        return

    # engine.begin() открывает транзакцию и автоматически делает commit в конце
    with engine.begin() as conn:
        bulk_insert(conn, "matches", bundle["match"], conflict_target="match_id")
        
        if bundle["global_players"]:
            bulk_insert(conn, "players", bundle["global_players"], conflict_target="account_id", do_update=True)
            
        if bundle["match_players"]:
            bulk_insert(conn, "match_players", bundle["match_players"], conflict_target="match_id, player_slot")
            
        if bundle["player_timelines"]:
            bulk_insert(conn, "player_timelines", bundle["player_timelines"], conflict_target="match_id, player_slot, minute")
            
        if bundle["team_timelines"]:
            bulk_insert(conn, "team_timelines", bundle["team_timelines"], conflict_target="match_id, minute")


if __name__ == "__main__":
    heroes = transform_heroes()
    load_heroes(heroes)
    logging.info("Героев загружено: %d", len(heroes))

    # потом матчи
    files = list(Path("data/raw/matches").glob("*.json"))
    for file in files:
        bundle = run_transform_file(file)
        if bundle:
            load_match_bundle(bundle)
            logging.info("Матч %s загружен", bundle["match"]["match_id"])