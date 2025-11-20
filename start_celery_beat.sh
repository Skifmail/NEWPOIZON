#!/bin/bash
# Скрипт запуска Celery beat с правильным PYTHONPATH

cd /opt/poizon-app

# Устанавливаем PYTHONPATH
export PYTHONPATH=/opt/poizon-app:$PYTHONPATH

# Запускаем Celery beat
exec .venv/bin/celery -A celery_config beat --loglevel=info
