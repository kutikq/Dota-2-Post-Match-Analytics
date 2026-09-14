-- Справочник героев, заполняется один раз из /api/heroes
CREATE TABLE IF NOT EXISTS heroes (
    hero_id         INTEGER         PRIMARY KEY,
    name            VARCHAR(100)    NOT NULL,
    localized_name  VARCHAR(100),
    primary_attr    VARCHAR(5),
    attack_type     VARCHAR(10),
    roles           TEXT[]
);

-- Профили игроков, заполняется из /api/players/{account_id}
CREATE TABLE IF NOT EXISTS players (
    account_id      BIGINT          PRIMARY KEY,
    personaname     VARCHAR(255),
    rank_tier       INTEGER,
    mmr_estimate    INTEGER,
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

-- Общие данные матча, заполняется из /api/matches/{match_id}
CREATE TABLE IF NOT EXISTS matches (
    match_id            BIGINT      PRIMARY KEY,
    start_time          TIMESTAMPTZ NOT NULL,
    duration            INTEGER     NOT NULL,
    radiant_win         BOOLEAN     NOT NULL,
    game_mode           INTEGER,
    lobby_type          INTEGER,
    patch               INTEGER,
    first_blood_time    INTEGER,
    radiant_score       INTEGER,
    dire_score          INTEGER
);

-- Итоговая статистика каждого игрока в матче
-- PK составной: один игрок не может появиться в одном матче дважды
-- player_slot: 0–4 Radiant, 128–132 Dire
CREATE TABLE IF NOT EXISTS match_players (
    match_id                BIGINT      NOT NULL    REFERENCES matches(match_id),
    player_slot             INTEGER     NOT NULL,
    account_id              BIGINT                  REFERENCES players(account_id),
    hero_id                 INTEGER                 REFERENCES heroes(hero_id),
    is_radiant              BOOLEAN     NOT NULL,
    is_tracked              BOOLEAN     DEFAULT FALSE,

    win                     BOOLEAN     NOT NULL,
    leaver_status           INTEGER     DEFAULT 0,
    rank_tier               INTEGER,
    party_size              INTEGER,

    kills                   INTEGER,
    deaths                  INTEGER,
    assists                 INTEGER,

    gold_per_min            INTEGER,
    xp_per_min              INTEGER,
    net_worth               INTEGER,

    last_hits               INTEGER,
    denies                  INTEGER,
    level                   INTEGER,

    hero_damage             INTEGER,
    tower_damage            INTEGER,
    hero_healing            INTEGER,

    obs_placed              INTEGER,
    sen_placed              INTEGER,

    camps_stacked           INTEGER,
    stuns                   NUMERIC(10, 2),
    rune_pickups            INTEGER,
    roshans_killed          INTEGER,
    firstblood_claimed      BOOLEAN,
    teamfight_participation NUMERIC(4, 3),

    item_0      INTEGER     DEFAULT 0,
    item_1      INTEGER     DEFAULT 0,
    item_2      INTEGER     DEFAULT 0,
    item_3      INTEGER     DEFAULT 0,
    item_4      INTEGER     DEFAULT 0,
    item_5      INTEGER     DEFAULT 0,
    backpack_0  INTEGER     DEFAULT 0,
    backpack_1  INTEGER     DEFAULT 0,
    backpack_2  INTEGER     DEFAULT 0,

    bench_gpm_pct           NUMERIC(4, 3),
    bench_xpm_pct           NUMERIC(4, 3),
    bench_kills_pct         NUMERIC(4, 3),
    bench_lh_pct            NUMERIC(4, 3),
    bench_hero_damage_pct   NUMERIC(4, 3),
    bench_hero_healing_pct  NUMERIC(4, 3),
    bench_tower_damage_pct  NUMERIC(4, 3),
    bench_stuns_pct         NUMERIC(4, 3),

    PRIMARY KEY (match_id, player_slot)
);

-- Поминутная статистика игрока, массивы gold_t/xp_t/lh_t/dn_t/networth_t
-- разворачиваются в строки: одна строка = одна минута одного игрока
CREATE TABLE IF NOT EXISTS player_timelines (
    match_id        BIGINT      NOT NULL,
    player_slot     INTEGER     NOT NULL,
    minute          INTEGER     NOT NULL,
    networth_t      INTEGER,
    gold_t          INTEGER,
    xp_t            INTEGER,
    lh_t            INTEGER,
    dn_t            INTEGER,

    PRIMARY KEY (match_id, player_slot, minute),
    FOREIGN KEY (match_id, player_slot)
        REFERENCES match_players(match_id, player_slot)
);

-- Поминутное преимущество команд, из radiant_gold_adv[] и radiant_xp_adv[]
-- Значение > 0 означает что Radiant впереди
CREATE TABLE IF NOT EXISTS team_timelines (
    match_id            BIGINT      NOT NULL    REFERENCES matches(match_id),
    minute              INTEGER     NOT NULL,
    radiant_gold_adv    INTEGER,
    radiant_xp_adv      INTEGER,

    PRIMARY KEY (match_id, minute)
);

-- Ускоряет выборку всех матчей конкретного игрока
CREATE INDEX IF NOT EXISTS idx_match_players_account
    ON match_players(account_id);

-- Ускоряет агрегацию статистики по герою
CREATE INDEX IF NOT EXISTS idx_match_players_hero
    ON match_players(hero_id);

-- Ускоряет фильтрацию матчей по дате
CREATE INDEX IF NOT EXISTS idx_matches_start_time
    ON matches(start_time DESC);

-- Ускоряет загрузку таймлайна для графиков в Grafana
CREATE INDEX IF NOT EXISTS idx_player_timelines_match
    ON player_timelines(match_id);
