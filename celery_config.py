"""
Конфигурация Celery для фоновых задач.

Задачи:
- Загрузка товаров в WordPress (асинхронно)
- Обновление цен и остатков
- Обработка изображений
- Периодическая очистка кеша
- Периодическое обновление брендов/категорий
"""
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH для корректного импорта модулей
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import os
from celery import Celery
from celery.schedules import crontab

# Конфигурация Redis
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Создаем Celery app
app = Celery(
    'poizon_sync',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['celery_tasks']
)

# Конфигурация
app.conf.update(
    # Часовой пояс
    timezone='Europe/Moscow',
    enable_utc=True,
    
    # Сериализация
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Таймауты
    task_time_limit=3600,  # 1 час максимум на задачу
    task_soft_time_limit=3300,  # 55 минут soft limit
    
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Результаты
    result_expires=86400,  # Храним результаты 24 часа
    result_backend_transport_options={'master_name': 'mymaster'},
    
    # Worker
    worker_prefetch_multiplier=1,  # По одной задаче на worker
    worker_max_tasks_per_child=100,  # Перезапуск worker каждые 100 задач
    
    # Beat schedule (периодические задачи)
    beat_schedule={
        # Очистка истекшего кеша каждый день в 3:00
        'cleanup-expired-cache': {
            'task': 'celery_tasks.cleanup_expired_cache',
            'schedule': crontab(hour=3, minute=0),
        },
        
        # Обновление брендов раз в месяц
        'update-brands-cache': {
            'task': 'celery_tasks.update_brands_cache',
            'schedule': crontab(day_of_month=1, hour=4, minute=0),
        },
        
        # Обновление категорий раз в месяц
        'update-categories-cache': {
            'task': 'celery_tasks.update_categories_cache',
            'schedule': crontab(day_of_month=1, hour=5, minute=0),
        },
    },
)

if __name__ == '__main__':
    app.start()
