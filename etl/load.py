from sqlalchemy import text
from etl.config import engine

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

# функция для ограничения загрузки уже имеющихся файлов
def get_existing_match_ids() -> set[int]:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT match_id FROM matches"))
        return {row[0] for row in result}

# не будем при каждой загрузке догружать героев
def heroes_already_loaded() -> bool:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM heroes"))
        return result.scalar() > 0