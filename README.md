# Dota 2 Post-Match Analytics

Большинство сервисов статистики отвечают на вопрос **что произошло** — убийства, смерти, GPM.  
Этот проект отвечает на другой вопрос: **насколько твои показатели хороши для твоего ранга, и где именно ты теряешь?**

После каждого матча данные автоматически загружаются из OpenDota API и сохраняются в PostgreSQL для дальнейшей аналитики и визуализации.

## Стек

Python · PostgreSQL · SQLAlchemy · Airflow · Grafana · Docker Compose

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
py etl/parse_player.py
```

*Данные: [OpenDota API](https://docs.opendota.com/)*
