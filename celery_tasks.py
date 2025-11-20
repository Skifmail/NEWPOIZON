"""
Celery задачи для фоновой обработки.

Все тяжелые операции выполняются асинхронно:
- Загрузка товаров в WordPress
- Обновление цен
- Обработка изображений
- Очистка кеша
"""
import sys
import os
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH для корректного импорта модулей
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from celery import Task
from celery_config import app
from unified_cache import get_cache
from circuit_breaker import get_circuit_breaker, CircuitBreakerError

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """Базовая задача с поддержкой progress callback"""
    
    def __call__(self, *args, **kwargs):
        """Перехватываем вызов для добавления логирования"""
        logger.info(f"[TASK START] {self.name}")
        try:
            result = super().__call__(*args, **kwargs)
            logger.info(f"[TASK SUCCESS] {self.name}")
            return result
        except Exception as e:
            logger.error(f"[TASK ERROR] {self.name}: {e}")
            raise


@app.task(bind=True, base=CallbackTask, name='celery_tasks.upload_product')
def upload_product(
    self,
    spu_id: int,
    settings: dict,
    session_id: str = None
) -> dict:
    """
    Загружает один товар в WordPress (асинхронно).
    
    Args:
        spu_id: ID товара в Poizon
        settings: Настройки синхронизации (курс, наценка)
        session_id: ID сессии для отправки прогресса
        
    Returns:
        Результат загрузки
    """
    try:
        # Обновляем прогресс
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Начинаем загрузку...'}
        )
        
        # Импортируем здесь чтобы избежать circular imports
        try:
            # Явно добавляем текущую директорию в путь
            import sys
            import os
            current_dir = os.getcwd()
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)
            
            # Отладочный вывод
            logger.info(f"[DEBUG] CWD: {current_dir}")
            logger.info(f"[DEBUG] sys.path: {sys.path}")
            logger.info(f"[DEBUG] Files in CWD: {os.listdir(current_dir)}")

            from poizon_to_wordpress_service import (
                WooCommerceService,
                SyncSettings
            )
            from openai_service import OpenAIService  # Новый импорт
        except ImportError as e:
            logger.error(f"[IMPORT ERROR] Failed to import service: {e}")
            logger.error(f"[DEBUG] CWD: {os.getcwd()}")
            logger.error(f"[DEBUG] sys.path: {sys.path}")
            raise

        from poizon_api_fixed import PoisonAPIClientFixed
        # from web_app import OpenAIService  # УДАЛЕНО: вызывало циклический импорт
        
        # Получаем circuit breaker
        poizon_cb = get_circuit_breaker('poizon_api', failure_threshold=5, recovery_timeout=60)
        wordpress_cb = get_circuit_breaker('wordpress_api', failure_threshold=5, recovery_timeout=60)
        openai_cb = get_circuit_breaker('openai_api', failure_threshold=3, recovery_timeout=120)
        
        # Инициализируем клиенты
        poizon = PoisonAPIClientFixed()
        woocommerce = WooCommerceService()
        # openai = OpenAIService() - SEO генерируется внутри poizon.get_product_full_info
        
        # Создаем настройки
        sync_settings = SyncSettings(
            currency_rate=settings.get('currency_rate', 13.5),
            markup_rubles=settings.get('markup_rubles', 5000)
        )
        
        # Шаг 1: Загружаем товар из Poizon (с circuit breaker)
        self.update_state(
            state='PROGRESS',
            meta={'current': 20, 'total': 100, 'status': 'Загрузка из Poizon...'}
        )
        
        try:
            product = poizon_cb.call(poizon.get_product_full_info, spu_id)
        except CircuitBreakerError:
            logger.error(f"Poizon API недоступен (circuit open)")
            return {'status': 'error', 'message': 'Poizon API временно недоступен'}
        
        if not product:
            return {'status': 'error', 'message': 'Товар не найден'}
        
        # Шаг 2: Генерация SEO (уже выполнена внутри poizon.get_product_full_info)
        self.update_state(
            state='PROGRESS',
            meta={'current': 50, 'total': 100, 'status': 'Проверка данных...'}
        )
        
        # SEO данные уже находятся в объекте product, полученном на шаге 1
        if not product.description:
             logger.warning("SEO описание отсутствует, используется базовое")
        
        # Шаг 3: Загружаем в WordPress (с circuit breaker)
        self.update_state(
            state='PROGRESS',
            meta={'current': 75, 'total': 100, 'status': 'Загрузка в WordPress...'}
        )
        
        try:
            existing_id = wordpress_cb.call(woocommerce.product_exists, product.sku)
            
            if existing_id:
                updated = wordpress_cb.call(
                    woocommerce.update_product_variations,
                    existing_id,
                    product,
                    sync_settings
                )
                result = {
                    'status': 'updated',
                    'product_id': existing_id,
                    'variations_updated': updated,
                    'message': f'Обновлен товар ID {existing_id}'
                }
            else:
                new_id = wordpress_cb.call(
                    woocommerce.create_product,
                    product,
                    sync_settings
                )
                result = {
                    'status': 'created',
                    'product_id': new_id,
                    'message': f'Создан товар ID {new_id}'
                }
        except CircuitBreakerError:
            logger.error(f"WordPress API недоступен (circuit open)")
            return {'status': 'error', 'message': 'WordPress API временно недоступен'}
        
        # Завершено
        self.update_state(
            state='SUCCESS',
            meta={'current': 100, 'total': 100, 'status': 'Готово!'}
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка загрузки товара {spu_id}: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='celery_tasks.cleanup_expired_cache')
def cleanup_expired_cache():
    """Периодическая очистка истекшего кеша (запускается раз в день)"""
    logger.info("[TASK] Очистка истекшего кеша...")
    
    cache = get_cache()
    cache.cleanup_expired()
    
    stats = cache.get_stats()
    logger.info(f"[TASK] Кеш очищен. Статистика: {stats}")
    
    return {'status': 'success', 'stats': stats}


@app.task(name='celery_tasks.update_brands_cache')
def update_brands_cache():
    """Обновление кеша брендов (запускается раз в месяц)"""
    logger.info("[TASK] Обновление кеша брендов...")
    
    try:
        from poizon_api_fixed import PoisonAPIClientFixed
        from web_app import fetch_all_brands_from_api
        
        client = PoisonAPIClientFixed()
        brands = fetch_all_brands_from_api(client)
        
        # Сохраняем в кеш на 30 дней
        cache = get_cache()
        cache.set('all_brands', brands, ttl=30*24*60*60, namespace='brands')
        
        logger.info(f"[TASK] Кеш брендов обновлен: {len(brands)} брендов")
        return {'status': 'success', 'brands_count': len(brands)}
        
    except Exception as e:
        logger.error(f"[TASK ERROR] Ошибка обновления брендов: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='celery_tasks.update_categories_cache')
def update_categories_cache():
    """Обновление кеша категорий (запускается раз в месяц)"""
    logger.info("[TASK] Обновление кеша категорий...")
    
    try:
        from poizon_api_fixed import PoisonAPIClientFixed
        
        client = PoisonAPIClientFixed()
        categories = client.get_categories(lang="RU")
        
        # Сохраняем в кеш на 30 дней
        cache = get_cache()
        cache.set('all_categories', categories, ttl=30*24*60*60, namespace='categories')
        
        logger.info(f"[TASK] Кеш категорий обновлен: {len(categories)} категорий")
        return {'status': 'success', 'categories_count': len(categories)}
        
    except Exception as e:
        logger.error(f"[TASK ERROR] Ошибка обновления категорий: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='celery_tasks.batch_upload_callback')
def batch_upload_callback(results):
    """Callback для завершения пакетной загрузки (вызывается после всех подзадач)"""
    # Собираем статистику
    created = sum(1 for r in results if r and r.get('status') == 'created')
    updated = sum(1 for r in results if r and r.get('status') == 'updated')
    errors = sum(1 for r in results if r and r.get('status') == 'error')
    
    logger.info(f"[TASK] Пакетная загрузка завершена: создано={created}, обновлено={updated}, ошибок={errors}")
    
    return {
        'status': 'success',
        'total': len(results),
        'created': created,
        'updated': updated,
        'errors': errors,
        'results': results
    }


def batch_upload_products(product_ids: list, settings: dict):
    """
    Пакетная загрузка товаров (group).
    Возвращает GroupResult для отслеживания прогресса.
    """
    from celery import group
    
    logger.info(f"[TASK] Запуск пакетной загрузки {len(product_ids)} товаров...")
    
    header = [upload_product.s(spu_id, settings) for spu_id in product_ids]
    
    # Запускаем группу БЕЗ callback'а, чтобы получить GroupResult
    job = group(header)
    result = job.apply_async()
    result.save()
    
    logger.info(f"[TASK] Group запущен: {result.id}")
    
    return result


@app.task(bind=True, base=CallbackTask, name='celery_tasks.update_product_price')
def update_product_price(
    self,
    wc_product_id: int,
    settings: dict,
    session_id: str = None
) -> dict:
    """
    Обновляет цену и остатки одного товара (асинхронно).
    
    Args:
        wc_product_id: ID товара в WordPress
        settings: Настройки синхронизации
        session_id: ID сессии
        
    Returns:
        Результат обновления
    """
    try:
        # Обновляем прогресс
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Начинаем обновление...'}
        )
        
        # Импорты внутри задачи
        try:
            import sys
            import os
            current_dir = os.getcwd()
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)

            from poizon_to_wordpress_service import WooCommerceService
            from poizon_api_fixed import PoisonAPIClientFixed
        except ImportError as e:
            logger.error(f"[IMPORT ERROR] Failed to import service: {e}")
            raise

        # Получаем circuit breaker
        poizon_cb = get_circuit_breaker('poizon_api', failure_threshold=5, recovery_timeout=60)
        wordpress_cb = get_circuit_breaker('wordpress_api', failure_threshold=5, recovery_timeout=60)
        
        # Инициализируем клиенты
        poizon = PoisonAPIClientFixed()
        woocommerce = WooCommerceService()
        
        # Шаг 1: Получаем товар из WordPress
        self.update_state(
            state='PROGRESS',
            meta={'current': 20, 'total': 100, 'status': 'Загрузка из WordPress...'}
        )
        
        try:
            # Получаем товар (нужен для SKU/meta)
            url = f"{woocommerce.url}/wp-json/wc/v3/products/{wc_product_id}"
            response = wordpress_cb.call(
                lambda: __import__('requests').get(url, auth=woocommerce.auth, verify=False, timeout=30)
            )
            response.raise_for_status()
            wc_product = response.json()
        except Exception as e:
            return {'status': 'error', 'message': f'Ошибка WP: {str(e)}'}
            
        sku = wc_product.get('sku', '')
        product_name = wc_product.get('name', '')
        
        # Ищем spuId
        spu_id = None
        meta_data = wc_product.get('meta_data', [])
        for meta in meta_data:
            if meta.get('key') == '_poizon_spu_id':
                spu_id = int(meta.get('value'))
                break
        
        # Fallback: поиск по SKU
        if not spu_id:
            if not sku:
                return {'status': 'error', 'message': 'SKU не найден'}
            
            self.update_state(
                state='PROGRESS',
                meta={'current': 40, 'total': 100, 'status': f'Поиск SKU {sku}...'}
            )
            
            try:
                search_results = poizon_cb.call(lambda: poizon.search_products(sku, limit=1))
                if not search_results:
                    return {'status': 'error', 'message': 'Товар не найден в Poizon'}
                spu_id = search_results[0].get('spuId')
                
                # Сохраняем spuId
                try:
                    update_url = f"{woocommerce.url}/wp-json/wc/v3/products/{wc_product_id}"
                    update_data = {'meta_data': [{'key': '_poizon_spu_id', 'value': str(spu_id)}]}
                    __import__('requests').put(update_url, auth=woocommerce.auth, json=update_data, verify=False, timeout=30)
                except:
                    pass
            except Exception as e:
                return {'status': 'error', 'message': f'Ошибка поиска: {str(e)}'}

        # Шаг 2: Обновляем цены
        self.update_state(
            state='PROGRESS',
            meta={'current': 60, 'total': 100, 'status': 'Обновление цен...'}
        )
        
        updated = woocommerce.update_product_prices_only(
            wc_product_id,
            spu_id,
            settings.get('currency_rate', 13.5),
            settings.get('markup_rubles', 5000),
            poizon
        )
        
        if updated < 0:
            return {'status': 'error', 'message': 'Не удалось получить цены'}
        elif updated == 0:
            return {'status': 'warning', 'message': 'Нет совпадающих вариаций'}
            
        return {
            'status': 'completed',
            'product_id': wc_product_id,
            'product_name': product_name,
            'variations_updated': updated,
            'message': f'Обновлено {updated} вариаций'
        }
        
    except Exception as e:
        logger.error(f"Ошибка обновления товара {wc_product_id}: {e}")
        return {'status': 'error', 'message': str(e)}


@app.task(name='celery_tasks.batch_update_callback')
def batch_update_callback(results):
    """Callback для завершения пакетного обновления"""
    completed = sum(1 for r in results if r and r.get('status') == 'completed')
    warnings = sum(1 for r in results if r and r.get('status') == 'warning')
    errors = sum(1 for r in results if r and r.get('status') == 'error')
    
    logger.info(f"[TASK] Пакетное обновление завершено: OK={completed}, Warn={warnings}, Err={errors}")
    
    return {
        'status': 'success',
        'total': len(results),
        'completed': completed,
        'warnings': warnings,
        'errors': errors,
        'results': results
    }


def batch_update_prices(product_ids: list, settings: dict):
    """
    Пакетное обновление цен (group).
    Возвращает GroupResult для отслеживания прогресса.
    """
    from celery import group
    
    logger.info(f"[TASK] Запуск пакетного обновления {len(product_ids)} товаров...")
    
    header = [update_product_price.s(pid, settings) for pid in product_ids]
    
    job = group(header)
    result = job.apply_async()
    result.save()
    
    return result
