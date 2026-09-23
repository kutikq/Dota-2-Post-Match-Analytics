import json
import logging
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta

from etl.config import ACCOUNT_ID, HEROES_FILE, RAW_MATCHES_DIR

# Наборы полей (фильтры)
HERO_FIELDS = {"name", "localized_name", "primary_attr", "attack_type", "roles"}

MATCH_FIELDS = {
    "match_id", "duration", "radiant_win", "start_time",
    "game_mode", "patch", "lobby_type",
    "first_blood_time", "radiant_score", "dire_score"
}

PLAYER_FIELDS = {"account_id", "personaname", "rank_tier", "mmr_estimate"}

MATCH_PLAYER_FIELDS = {
    "account_id", "player_slot", "hero_id",
    "kills", "deaths", "assists",
    "gold_per_min", "xp_per_min", "net_worth",
    "last_hits", "denies", "level",
    "hero_damage", "tower_damage", "hero_healing",
    "item_0", "item_1", "item_2", "item_3", "item_4", "item_5",
    "backpack_0", "backpack_1", "backpack_2","item_neutral",
    "leaver_status", "rank_tier", "party_size",
    "obs_placed", "sen_placed", "camps_stacked",
    "stuns", "rune_pickups", "roshans_killed",
    "firstblood_claimed", "teamfight_participation"
}

# вспомогательнаяя функция для конвертации в float формат, нужна для процентилей от бенчмарков
def safe_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, dict):
        val = val.get("pct")
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


# таблица HEROES
def transform_heroes() -> list[dict[str, Any]]:
    if not HEROES_FILE.exists():
        logging.warning("Файл героев %s не найден", HEROES_FILE)
        return []
    
    with open(HEROES_FILE, "r", encoding="utf-8") as f:
        raw_heroes = json.load(f)
        
    heroes = []
    for h in raw_heroes:
        hero_dict = {k: h.get(k) for k in HERO_FIELDS}
        hero_dict["hero_id"] = h["id"]
        heroes.append(hero_dict)
    return heroes


# вспомогательные функции для матча
# Создаем часовой пояс Москвы
MSK_TZ = timezone(timedelta(hours=3))

def extract_match_info(match_data: dict[str, Any]) -> dict[str, Any]:
    info = {k: match_data.get(k) for k in MATCH_FIELDS}
    if info.get("start_time"):
        info["start_time"] = datetime.fromtimestamp(info["start_time"], tz=MSK_TZ)
    return info

# таблица PLAYERS
def extract_global_players(match_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {k: p.get(k) for k in PLAYER_FIELDS}
        for p in match_data.get("players", [])
        if p.get("account_id")
    ]

# таблица MATCH_PLAYERS
def extract_match_players(match_id: int, players_data: list[dict[str, Any]], radiant_win: bool) -> list[dict[str, Any]]:
    match_players = []

    for p in players_data:
        benchmarks = p.get("benchmarks") or {}
        player_entry = {k: p.get(k) for k in MATCH_PLAYER_FIELDS}
        
        # 1. Вычисляем is_radiant
        is_radiant = bool(p.get("isRadiant")) if p.get("isRadiant") is not None else p["player_slot"] < 128

        # 2. Вычисляем win (победил ли данный конкретный игрок)
        win = p.get("win")
        if win is None:
            win = (is_radiant == radiant_win)
        else:
            win = bool(win)

        # 3. Вычисляем is_tracked (наш ли это игрок)
        account_id = p.get("account_id")
        is_tracked = (account_id == ACCOUNT_ID) if account_id else False

        player_entry.update({
            "match_id": match_id,
            "is_radiant": is_radiant,
            "win": win,
            "is_tracked": is_tracked,
            "firstblood_claimed": bool(p.get("firstblood_claimed", False)),
            "bench_stuns_pct":    safe_float(benchmarks.get("stuns_per_min")),
            "bench_gpm_pct": safe_float(benchmarks.get("gold_per_min")),
            "bench_xpm_pct": safe_float(benchmarks.get("xp_per_min")),
            "bench_kills_pct": safe_float(benchmarks.get("kills_per_min")),
            "bench_lh_pct": safe_float(benchmarks.get("last_hits_per_min")),
            "bench_hero_damage_pct": safe_float(benchmarks.get("hero_damage_per_min")),
            "bench_hero_healing_pct": safe_float(benchmarks.get("hero_healing_per_min")),
            "bench_tower_damage_pct": safe_float(benchmarks.get("tower_damage")),
        })
        match_players.append(player_entry)
        
    return match_players

# таблица PLAYER_TIMELINES
def extract_player_timelines(match_id: int, players_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    timelines = []
    for p in players_data:
        gold_t = p.get("gold_t") or []
        xp_t = p.get("xp_t") or []
        lh_t = p.get("lh_t") or []
        dn_t = p.get("dn_t") or []
        networth_t = p.get("networth_t") or []

        for minute in range(len(gold_t)):
            timelines.append({
                "match_id": match_id,
                "player_slot": p["player_slot"],
                "minute": minute,
                "gold_t": gold_t[minute] if minute < len(gold_t) else None,
                "xp_t": xp_t[minute] if minute < len(xp_t) else None,
                "lh_t": lh_t[minute] if minute < len(lh_t) else None,
                "dn_t": dn_t[minute] if minute < len(dn_t) else None,
                "networth_t": networth_t[minute] if minute < len(networth_t) else None,
            })
    return timelines

# таблица TEAM_TIMELINES
def extract_team_timelines(match_id: int, match_data: dict[str, Any]) -> list[dict[str, Any]]:
    timelines = []
    gold_adv = match_data.get("radiant_gold_adv") or []
    xp_adv = match_data.get("radiant_xp_adv") or []

    for minute in range(len(gold_adv)):
        timelines.append({
            "match_id": match_id,
            "minute": minute,
            "radiant_gold_adv": gold_adv[minute] if minute < len(gold_adv) else None,
            "radiant_xp_adv": xp_adv[minute] if minute < len(xp_adv) else None,
        })
    return timelines


#главвная функция трансформации матча
def transform_match_all(match_data: dict[str, Any]) -> dict[str, Any]:
    match_id = match_data["match_id"]
    radiant_win = bool(match_data.get("radiant_win"))
    players_data = match_data.get("players", [])

    return {
        "match": extract_match_info(match_data),
        "global_players": extract_global_players(match_data),
        "match_players": extract_match_players(match_id, players_data, radiant_win),
        "player_timelines": extract_player_timelines(match_id, players_data),
        "team_timelines": extract_team_timelines(match_id, match_data),
    }

# вход для 1 файла матча
def run_transform_file(filepath: Path) -> dict[str, Any] | None:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        return transform_match_all(raw_data)
    except Exception as err:
        logging.error("Ошибка при трансформации файла %s: %s", filepath, err)
        return None

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    files = list(RAW_MATCHES_DIR.glob("*.json"))
    logging.info("Обработка %d файлов...", len(files))
    results = [run_transform_file(f) for f in files if f.is_file()]
    logging.info("Готово. Успешно трансформировано: %d", len(list(filter(None, results))))