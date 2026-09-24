from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from etl.run import run_etl

# Настройки по умолчанию для всех задач этого DAG
default_args = {
    "owner": "kutikq",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="dota_etl",
    description="Сбор матчей игрока из OpenDota API в PostgreSQL",
    default_args=default_args,
    # cron в UTC: 00:00, 06:00, 12:00, 18:00 UTC = 03:00, 09:00, 15:00, 21:00 МСК
    schedule="0 */6 * * *",
    start_date=datetime(2026, 9, 24),
    # не догонять пропущенные интервалы при первом запуске
    catchup=False,
    # не допускать параллельных прогонов: они пишут в те же файлы и таблицы
    max_active_runs=1,
    tags=["dota", "etl"],
) as dag:

    etl = PythonOperator(
        task_id="run_etl",
        python_callable=run_etl,
        # страховка от зависания на ожидании парсинга реплея
        execution_timeout=timedelta(minutes=30),
    )