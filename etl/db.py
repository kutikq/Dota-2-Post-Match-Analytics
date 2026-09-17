import os
import logging
from typing import Any
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy import create_engine, text
import requests
import json
from pathlib import Path

#Глобальные переменные
load_dotenv()   #загружаем данные из окружения для авториации

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

# вспомогательнаяя функция для конвертации в float формат, нужна для процентилей от бенчмарков
def safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None

# обощающая функцимя передачи данных в таблицы БД
def insert_parsed_data(table: str, data: dict) -> bool:
    columns = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())
    insert_query = text(f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON CONFLICT DO NOTHING")
    try:
        with engine.connect() as conn:
            conn.execute(insert_query, data)
            conn.commit()
            logging.info("Данные записаны в таблицу %s", table)
            return True
    except Exception as err:
        logging.error("Ошибка при записи в таблицу %s: %s", table, err)
        return False

# сайт переодически не работает чтобы не было проблем с переносом введем функция для чтения из локального файла
def fetch_and_save_heroes() -> bool:
    local_file = Path("data/heroes.json")

    try:
        response = requests.get(f"{OPENDOTA_URL}/heroes", timeout=60)
        response.raise_for_status()
        heroes = response.json()
        with open(local_file, "w") as f:
            json.dump(heroes, f)
        logging.info("Герои загружены из API")
    except Exception as err:
        logging.warning("API недоступен: %s — читаю локальный файл", err)
        if local_file.exists():
            with open(local_file) as f:
                heroes = json.load(f)
            logging.info("Герои загружены из локального файла")
        else:
            logging.error("Локальный файл героев не найден")
            return False

    for hero in heroes:
        data = {
            "hero_id":        hero["id"],
            "name":           hero["name"],
            "localized_name": hero["localized_name"],
            "primary_attr":   hero.get("primary_attr"),
            "attack_type":    hero.get("attack_type"),
            "roles":          hero.get("roles", []),
        }
        insert_parsed_data("heroes", data)

    logging.info("Герои сохранены: %d", len(heroes))
    return True


MATCH_FIELDS = {
    "match_id", "start_time", "duration", "radiant_win",
    "game_mode", "lobby_type", "patch", "first_blood_time",
    "radiant_score", "dire_score"
}

PLAYER_FIELDS = {
    "account_id", "personaname", "rank_tier", "mmr_estimate"
}

MATCH_PLAYER_FIELDS = {
    "match_id", "player_slot", "account_id", "hero_id",
    "is_radiant", "is_tracked", "win", "leaver_status",
    "rank_tier", "party_size",
    "kills", "deaths", "assists",
    "gold_per_min", "xp_per_min", "net_worth",
    "last_hits", "denies", "level",
    "hero_damage", "tower_damage", "hero_healing",
    "obs_placed", "sen_placed", "camps_stacked",
    "stuns", "rune_pickups", "roshans_killed",
    "firstblood_claimed", "teamfight_participation",
    "item_0", "item_1", "item_2", "item_3", "item_4", "item_5",
    "backpack_0", "backpack_1", "backpack_2",
    "bench_gpm_pct", "bench_xpm_pct", "bench_kills_pct",
    "bench_lh_pct", "bench_hero_damage_pct",
    "bench_hero_healing_pct", "bench_tower_damage_pct",
    "bench_stuns_pct"
}

PLAYER_TIMELINE_FIELDS = {
    "match_id", "player_slot", "minute",
    "networth_t", "gold_t", "xp_t", "lh_t", "dn_t"
}

TEAM_TIMELINE_FIELDS = {
    "match_id", "minute",
    "radiant_gold_adv", "radiant_xp_adv"
}


def save_match(match_data: dict) -> bool:
    data = {k: match_data.get(k) for k in MATCH_FIELDS}
    data["start_time"] = datetime.fromtimestamp(match_data["start_time"])
    return insert_parsed_data("matches", data)


def save_player(player_data: dict) -> bool:
    # анонимные игроки без account_id не сохраняются
    if not player_data.get("account_id"):
        return False
    data = {k: player_data.get(k) for k in PLAYER_FIELDS}
    return insert_parsed_data("players", data)


def save_match_players(match_data: dict, tracked_account_id: int = ACCOUNT_ID) -> bool:
    success = True
    for player in match_data.get("players", []):
        bench = player.get("benchmarks") or {}
        data = {k: player.get(k) for k in MATCH_PLAYER_FIELDS}

        # Поля, которых нет напрямую в player - добавляем вручную
        data["match_id"]    = match_data["match_id"]
        data["is_radiant"]  = player.get("isRadiant", False)
        data["is_tracked"]  = player.get("account_id") == int(tracked_account_id or 0)
        data["win"]         = bool(player.get("win"))
        data["firstblood_claimed"] = bool(player.get("firstblood_claimed", False))
        
        # используем вспомогательную функцию чтобы бенчмарки нормально передавалис в БД
        data["bench_gpm_pct"]          = safe_float((bench.get("gold_per_min") or {}).get("pct"))
        data["bench_xpm_pct"]          = safe_float((bench.get("xp_per_min") or {}).get("pct"))
        data["bench_kills_pct"]        = safe_float((bench.get("kills_per_min") or {}).get("pct"))
        data["bench_lh_pct"]           = safe_float((bench.get("last_hits_per_min") or {}).get("pct"))
        data["bench_hero_damage_pct"]  = safe_float((bench.get("hero_damage_per_min") or {}).get("pct"))
        data["bench_hero_healing_pct"] = safe_float((bench.get("hero_healing_per_min") or {}).get("pct"))
        data["bench_tower_damage_pct"] = safe_float((bench.get("tower_damage") or {}).get("pct"))
        data["bench_stuns_pct"]        = safe_float((bench.get("stuns_per_min") or {}).get("pct"))

        if not insert_parsed_data("match_players", data):
            success = False
    return success


def save_player_timelines(match_data: dict) -> bool:
    success = True
    for player in match_data.get("players", []):
        gold_t     = player.get("gold_t") or []
        xp_t       = player.get("xp_t") or []
        lh_t       = player.get("lh_t") or []
        dn_t       = player.get("dn_t") or []
        networth_t = player.get("networth_t") or []

        for minute, _ in enumerate(gold_t):
            data = {
                "match_id":   match_data["match_id"],
                "player_slot": player["player_slot"],
                "minute":     minute,
                "gold_t":     gold_t[minute] if minute < len(gold_t) else None,
                "xp_t":       xp_t[minute]   if minute < len(xp_t)   else None,
                "lh_t":       lh_t[minute]   if minute < len(lh_t)   else None,
                "dn_t":       dn_t[minute]   if minute < len(dn_t)   else None,
                "networth_t": networth_t[minute] if minute < len(networth_t) else None,
            }
            if not insert_parsed_data("player_timelines", data):
                success = False
    return success


def save_team_timelines(match_data: dict) -> bool:
    success = True
    gold_adv = match_data.get("radiant_gold_adv") or []
    xp_adv   = match_data.get("radiant_xp_adv") or []

    for minute, _ in enumerate(gold_adv):
        data = {
            "match_id":         match_data["match_id"],
            "minute":           minute,
            "radiant_gold_adv": gold_adv[minute] if minute < len(gold_adv) else None,
            "radiant_xp_adv":   xp_adv[minute]   if minute < len(xp_adv)   else None,
        }
        if not insert_parsed_data("team_timelines", data):
            success = False
    return success


def save_all(match_data: dict, tracked_account_id: int = ACCOUNT_ID) -> bool:
    save_match(match_data)  # ← убрали if not
    for player in match_data.get("players", []):
        save_player(player)
    save_match_players(match_data, tracked_account_id)
    save_player_timelines(match_data)
    save_team_timelines(match_data)
    return True

