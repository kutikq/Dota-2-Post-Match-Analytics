# Dota 2 Post-Match Analytics

Большинство сервисов статистики отвечают на вопрос **что произошло** — убийства, смерти, GPM.  
Этот проект отвечает на другой вопрос: **насколько твои показатели хороши для твоего ранга, и где именно ты теряешь?**

После каждого матча данные автоматически загружаются из OpenDota API, трансформируются и сохраняются в PostgreSQL для аналитики и визуализации в Grafana.

## Стек

Python · PostgreSQL · SQLAlchemy · Airflow · Grafana · Docker Compose

## Архитектура ETL

```
OpenDota API
     ↓
extract.py       — загрузка сырых данных, сохранение JSON
     ↓
transform.py     — очистка, типизация, подготовка к загрузке
     ↓
load.py          — запись в PostgreSQL через SQLAlchemy
     ↓
PostgreSQL        — хранение данных
     ↓
Grafana          — визуализация и дашборды
```

## Схема БД

| Таблица | Описание |
|---|---|
| `heroes` | Справочник героев |
| `players` | Профили игроков |
| `matches` | Общие данные матча |
| `match_players` | Итоговая статистика игрока за матч |
| `player_timelines` | Поминутная статистика (нетворс, голд, опыт, ластхиты) |
| `team_timelines` | Поминутное преимущество команд |

## Запуск

```bash
git clone https://github.com/kutikq/dota-analytics.git
cd dota-analytics
cp .env.example .env  # заполни переменные
docker compose up -d
py -m etl.extract     # загрузка данных из API
py -m etl.transform   # трансформация формата
py -m etl.load        # запись в БД
```


*Данные: [OpenDota API](https://docs.opendota.com/)*