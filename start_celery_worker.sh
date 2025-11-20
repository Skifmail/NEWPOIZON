#!/bin/bash
# Скрипт запуска Celery worker с правильным PYTHONPATH

cd /opt/poizon-app

# Устанавливаем PYTHONPATH
export PYTHONPATH=/opt/poizon-app:$PYTHONPATH

# Запускаем Celery worker
exec .venv/bin/celery -A celery_config worker \
  --loglevel=info \
  --concurrency=4 \
  --max-tasks-per-child=50 \
  --time-limit=3600 \
  --soft-time-limit=3300
