# Dota 2 Post-Match Analytics

Большинство сервисов статистики отвечают на вопрос **что произошло** — убийства, смерти, GPM.
Этот проект отвечает на другой вопрос: **насколько твои показатели хороши для твоего ранга, и где именно ты теряешь?**

Данные автоматически загружаются из OpenDota API по расписанию, трансформируются и сохраняются
в PostgreSQL для аналитики и визуализации.

## Стек

Python · PostgreSQL · SQLAlchemy Core · Apache Airflow · Grafana · Docker Compose

## Архитектура

```
                    ┌─────────────────┐
                    │ Apache Airflow  │  раз в сутки
                    │   (scheduler)   │
                    └────────┬────────┘
                             │
                             ▼
OpenDota API ──►  extract ──►  transform ──►  load  ──►  PostgreSQL ──►  Grafana
                     │            │             │
                 data/raw/    типизация    bulk insert
                  (JSON)      и фильтры    ON CONFLICT
```

| Модуль | Ответственность |
|---|---|
| `etl/config.py` | переменные окружения, пути, подключение к БД |
| `etl/extract.py` | запросы к OpenDota API, кэширование ответов в `data/raw/` |
| `etl/transform.py` | фильтрация полей, типизация, разворот поминутных массивов |
| `etl/load.py` | идемпотентная запись в PostgreSQL |
| `etl/run.py` | оркестратор: полный цикл, грузит только новые матчи |
| `dags/dota_etl.py` | DAG для Airflow |

Конфигурация отделена от кода: один и тот же ETL работает и локально
(`localhost:5433`), и внутри Airflow (`dota_postgres:5432`) — различия только
в переменных окружения.

## Схема БД

| Таблица | Описание |
|---|---|
| `heroes` | справочник героев |
| `players` | профили игроков |
| `matches` | общие данные матча |
| `match_players` | итоговая статистика игрока за матч + перцентили по рангу |
| `player_timelines` | поминутная статистика (нетворс, золото, опыт, ластхиты) |
| `team_timelines` | поминутное преимущество команд |

Перцентили (`bench_*_pct`) приходят готовыми из OpenDota: значение `0.71` означает,
что показатель выше, чем у 71% игроков того же ранга в этом матче.

## Запуск

```bash
git clone https://github.com/kutikq/dota-analytics.git
cd dota-analytics

cp .env.example .env        # заполнить пароли и ACCOUNT_ID
docker compose build
docker compose up -d
```

Сервисы:

| Адрес | Что это |
|---|---|
| `localhost:8080` | Airflow — расписание и логи задач |
| `localhost:5050` | pgAdmin — просмотр БД |
| `localhost:5433` | PostgreSQL — подключение извне |

В Airflow снять `dota_etl` с паузы. Дальше он работает сам; расписание задаётся
параметром `schedule` в DAG (cron в UTC).

Запуск ETL вручную, без Airflow:

```bash
py -m etl.run
```

## Структура проекта

```
├── dags/
│   └── dota_etl.py
├── etl/
│   ├── config.py
│   ├── extract.py
│   ├── transform.py
│   ├── load.py
│   └── run.py
├── sql/
│   └── schema.sql
├── data/raw/              # кэш ответов API (в git не попадает)
├── Dockerfile             # образ Airflow + зависимости проекта
├── docker-compose.yml
└── requirements.txt
```
---

*Данные: [OpenDota API](https://docs.opendota.com/)*