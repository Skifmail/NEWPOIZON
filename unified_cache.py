"""
Унифицированная система кеширования с Redis и файловым fallback.

Многоуровневая архитектура:
1. L1 - in-memory (fastest, TTL 5 min)
2. L2 - Redis (fast, shared, TTL configurable)
3. L3 - File cache (slow, persistent, TTL days)

Автоматический fallback при недоступности Redis.
"""
import os
import json
import time
import re
import pickle
import logging
from pathlib import Path
from typing import Any, Optional, Callable
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger(__name__)

# Пробуем импортировать Redis, но не критично если не установлен
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis не установлен - используется только файловый кеш")


class UnifiedCache:
    """
    Трехуровневый кеш с автоматическим fallback.
    
    Поддерживает:
    - Автоматическую инвалидацию по TTL
    - Сжатие данных
    - Статистику (hits, misses)
    - Graceful degradation при падении Redis
    """
    
    def __init__(
        self,
        cache_dir: str = "kash",
        redis_url: str = None,
        enable_redis: bool = True,
        enable_file_cache: bool = True,
        enable_memory_cache: bool = True
    ):
        """
        Инициализация кеша.
        
        Args:
            cache_dir: Директория для файлового кеша
            redis_url: URL для подключения к Redis (e.g., redis://localhost:6379/0)
            enable_redis: Использовать ли Redis
            enable_file_cache: Использовать ли файловый кеш
            enable_memory_cache: Использовать ли in-memory кеш
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Настройки уровней кеширования
        self.enable_memory = enable_memory_cache
        self.enable_redis = enable_redis and REDIS_AVAILABLE
        self.enable_file = enable_file_cache
        
        # L1: In-memory cache (быстрый, но теряется при перезапуске)
        self.memory_cache = {} if self.enable_memory else None
        self.memory_ttl = 300  # 5 минут в памяти
        
        # L2: Redis cache (быстрый, shared между процессами)
        self.redis_client = None
        if self.enable_redis:
            try:
                redis_url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=False,  # Работаем с bytes для pickle
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                # Проверяем подключение
                self.redis_client.ping()
                logger.info(f"✅ Redis подключен: {redis_url}")
            except Exception as e:
                logger.warning(f"⚠️ Redis недоступен: {e}, используем только файловый кеш")
                self.redis_client = None
                self.enable_redis = False
        
        # L3: File cache (медленный, но персистентный)
        # Файлы: kash/cache_{key}.pkl
        
        # Статистика
        self.stats = {
            'memory_hits': 0,
            'redis_hits': 0,
            'file_hits': 0,
            'misses': 0,
            'sets': 0,
            'errors': 0,
            # Сколько запросов к API удалось избежать благодаря кэшу
            'requests_saved': 0
        }
        
        logger.info(f"Кеш инициализирован: memory={self.enable_memory}, redis={self.enable_redis}, file={self.enable_file}")
    
    def _make_key(self, key: str, namespace: str = "") -> str:
        """Создает уникальный ключ с namespace"""
        return f"{namespace}:{key}" if namespace else key

    def _file_path(self, full_key: str) -> Path:
        """Возвращает безопасный путь к файлу кеша для ключа.
        Заменяет двоеточия, слеши и любые недопустимые для имени файла символы.
        """
        # Сначала заменим двоеточия, затем нормализуем любые не [A-Za-z0-9._-]
        normalized = full_key.replace(":", "_")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized)
        return self.cache_dir / f"cache_{safe}.pkl"
    
    def get(self, key: str, namespace: str = "", default: Any = None) -> Any:
        """
        Получить значение из кеша (проверяет все уровни).
        
        Args:
            key: Ключ кеша
            namespace: Namespace для группировки ключей (brands, products, categories)
            default: Значение по умолчанию если не найдено
            
        Returns:
            Закешированное значение или default
        """
        full_key = self._make_key(key, namespace)
        
        # L1: Проверяем memory cache
        if self.enable_memory and self.memory_cache is not None:
            if full_key in self.memory_cache:
                data, timestamp, ttl = self.memory_cache[full_key]
                if time.time() - timestamp < ttl:
                    self.stats['memory_hits'] += 1
                    logger.debug(f"[CACHE HIT L1] {full_key}")
                    return data
                else:
                    # Expired
                    del self.memory_cache[full_key]
        
        # L2: Проверяем Redis cache
        if self.enable_redis and self.redis_client:
            try:
                cached = self.redis_client.get(full_key)
                if cached:
                    data = pickle.loads(cached)
                    self.stats['redis_hits'] += 1
                    logger.debug(f"[CACHE HIT L2] {full_key}")
                    
                    # Копируем в memory cache
                    if self.enable_memory and self.memory_cache is not None:
                        self.memory_cache[full_key] = (data, time.time(), self.memory_ttl)
                    
                    return data
            except Exception as e:
                logger.error(f"[CACHE ERROR Redis] {e}")
                self.stats['errors'] += 1
        
        # L3: Проверяем file cache
        if self.enable_file:
            try:
                cache_file = self._file_path(full_key)
                if cache_file.exists():
                    with open(cache_file, 'rb') as f:
                        cached_data = pickle.load(f)
                    
                    data = cached_data['data']
                    timestamp = cached_data['timestamp']
                    ttl = cached_data['ttl']
                    
                    if time.time() - timestamp < ttl:
                        self.stats['file_hits'] += 1
                        logger.debug(f"[CACHE HIT L3] {full_key}")
                        
                        # Копируем в верхние уровни
                        if self.enable_memory and self.memory_cache is not None:
                            self.memory_cache[full_key] = (data, time.time(), self.memory_ttl)
                        
                        if self.enable_redis and self.redis_client:
                            try:
                                self.redis_client.setex(
                                    full_key,
                                    int(min(ttl, 86400)),  # Max 24h в Redis
                                    pickle.dumps(data)
                                )
                            except:
                                pass
                        
                        return data
                    else:
                        # Expired
                        cache_file.unlink()
            except Exception as e:
                logger.error(f"[CACHE ERROR File] {e}")
                self.stats['errors'] += 1
        
        # Cache miss
        self.stats['misses'] += 1
        logger.debug(f"[CACHE MISS] {full_key}")
        return default
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600,
        namespace: str = "",
        skip_memory: bool = False,
        skip_redis: bool = False,
        skip_file: bool = False
    ):
        """
        Сохранить значение во все уровни кеша.
        
        Args:
            key: Ключ кеша
            value: Значение для кеширования
            ttl: Время жизни в секундах
            namespace: Namespace для группировки
            skip_memory: Пропустить memory cache
            skip_redis: Пропустить Redis cache
            skip_file: Пропустить file cache
        """
        full_key = self._make_key(key, namespace)
        self.stats['sets'] += 1
        
        # L1: Memory cache
        if self.enable_memory and not skip_memory and self.memory_cache is not None:
            # В памяти храним максимум 5 минут
            memory_ttl = min(ttl, self.memory_ttl)
            self.memory_cache[full_key] = (value, time.time(), memory_ttl)
        
        # L2: Redis cache
        if self.enable_redis and not skip_redis and self.redis_client:
            try:
                # В Redis максимум 24 часа
                redis_ttl = min(ttl, 86400)
                self.redis_client.setex(
                    full_key,
                    redis_ttl,
                    pickle.dumps(value)
                )
            except Exception as e:
                logger.error(f"[CACHE ERROR Redis set] {e}")
                self.stats['errors'] += 1
        
        # L3: File cache (для долговременного хранения)
        if self.enable_file and not skip_file:
            try:
                cache_file = self._file_path(full_key)
                cached_data = {
                    'data': value,
                    'timestamp': time.time(),
                    'ttl': ttl,
                    'created': datetime.now().isoformat()
                }
                with open(cache_file, 'wb') as f:
                    pickle.dump(cached_data, f)
            except Exception as e:
                logger.error(f"[CACHE ERROR File set] {e}")
                self.stats['errors'] += 1
    
    def delete(self, key: str, namespace: str = ""):
        """Удалить ключ из всех уровней кеша"""
        full_key = self._make_key(key, namespace)
        
        # L1
        if self.enable_memory and self.memory_cache is not None:
            self.memory_cache.pop(full_key, None)
        
        # L2
        if self.enable_redis and self.redis_client:
            try:
                self.redis_client.delete(full_key)
            except:
                pass
        
        # L3
        if self.enable_file:
            try:
                cache_file = self._file_path(full_key)
                if cache_file.exists():
                    cache_file.unlink()
            except:
                pass
    
    def clear(self, namespace: str = ""):
        """Очистить весь кеш или namespace"""
        if namespace:
            # Очищаем только по namespace
            # TODO: Реализовать через pattern matching
            logger.warning(f"Очистка namespace '{namespace}' не реализована")
        else:
            # Полная очистка
            if self.enable_memory and self.memory_cache is not None:
                self.memory_cache.clear()
            
            if self.enable_redis and self.redis_client:
                try:
                    self.redis_client.flushdb()
                except:
                    pass
            
            if self.enable_file:
                for cache_file in self.cache_dir.glob("cache_*.pkl"):
                    try:
                        cache_file.unlink()
                    except:
                        pass
        
        logger.info(f"Кеш очищен (namespace={namespace or 'all'})")
    
    def get_stats(self) -> dict:
        """Получить статистику кеша"""
        total_hits = self.stats['memory_hits'] + self.stats['redis_hits'] + self.stats['file_hits']
        total_requests = total_hits + self.stats['misses']
        
        return {
            **self.stats,
            'total_requests': total_requests,
            'hit_rate': f"{(total_hits / total_requests * 100):.1f}%" if total_requests > 0 else "0%",
            'memory_enabled': self.enable_memory,
            'redis_enabled': self.enable_redis,
            'file_enabled': self.enable_file
        }
    
    def cleanup_expired(self):
        """
        Очищает истекшие файлы из file cache.
        Рекомендуется запускать периодически (например, раз в день через Celery beat).
        """
        if not self.enable_file:
            return
        
        cleaned = 0
        for cache_file in self.cache_dir.glob("cache_*.pkl"):
            try:
                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)
                
                timestamp = cached_data.get('timestamp', 0)
                ttl = cached_data.get('ttl', 0)
                
                if time.time() - timestamp >= ttl:
                    cache_file.unlink()
                    cleaned += 1
            except:
                # Поврежденный файл - удаляем
                try:
                    cache_file.unlink()
                    cleaned += 1
                except:
                    pass
        
        if cleaned > 0:
            logger.info(f"Очищено истекших файлов кеша: {cleaned}")


# Декоратор для кеширования результатов функций
def cached(
    ttl: int = 3600,
    namespace: str = "",
    key_func: Optional[Callable] = None,
    cache_instance: Optional[UnifiedCache] = None
):
    """
    Декоратор для автоматического кеширования результатов функций.
    
    Args:
        ttl: Время жизни кеша в секундах
        namespace: Namespace для группировки
        key_func: Функция для генерации ключа из аргументов (по умолчанию str(args))
        cache_instance: Экземпляр UnifiedCache (если None, создастся новый)
    
    Example:
        @cached(ttl=3600, namespace='brands')
        def get_brands():
            return api.get_brands()
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Создаем экземпляр кеша если не передан
            cache = cache_instance or UnifiedCache()
            
            # Генерируем ключ
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Простой ключ из имени функции + аргументов
                cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            # Проверяем кеш
            result = cache.get(cache_key, namespace=namespace)
            
            if result is not None:
                return result
            
            # Вызываем функцию
            result = func(*args, **kwargs)
            
            # Кешируем результат
            if result is not None:
                cache.set(cache_key, result, ttl=ttl, namespace=namespace)
            
            return result
        
        return wrapper
    return decorator


# Глобальный экземпляр кеша
_global_cache = None


def get_cache() -> UnifiedCache:
    """Получить глобальный экземпляр кеша (singleton)"""
    global _global_cache
    if _global_cache is None:
        _global_cache = UnifiedCache()
    return _global_cache


if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    cache = UnifiedCache()
    
    print("\n=== Тест кеширования ===")
    
    # Сохраняем данные
    cache.set('test_key', {'data': 'value'}, ttl=10, namespace='test')
    
    # Получаем из памяти
    print(f"Get 1: {cache.get('test_key', namespace='test')}")  # L1 hit
    
    # Очищаем память, должен получить из Redis/File
    cache.memory_cache.clear()
    print(f"Get 2: {cache.get('test_key', namespace='test')}")  # L2/L3 hit
    
    # Статистика
    print(f"\nСтатистика: {cache.get_stats()}")
