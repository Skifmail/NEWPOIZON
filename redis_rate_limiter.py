"""
Глобальный Rate Limiter на базе Redis для координации запросов между Celery воркерами.

Проблема:
- Celery worker'ы работают параллельно (4 воркера)
- Каждый делает запросы к Poizon API независимо
- Rate limit 0.1с работает только ВНУТРИ одного воркера
- При параллельных запросах → 4x нагрузка → 429 Too Many Requests

Решение:
- Глобальная блокировка через Redis
- Все воркеры используют общий токен-bucket
- Максимум N запросов в секунду ГЛОБАЛЬНО (не на воркер!)
"""
import redis
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    """
    Глобальный rate limiter через Redis с токен-bucket алгоритмом.
    
    Attributes:
        redis_client: Redis клиент
        key_prefix: Префикс для Redis ключей
        max_requests: Максимум запросов в окне
        window_seconds: Размер окна в секундах
        
    Example:
        >>> limiter = RedisRateLimiter(max_requests=5, window_seconds=1)
        >>> if limiter.acquire("poizon_api"):
        ...     # Делаем запрос к API
        ...     result = api_call()
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "rate_limit",
        max_requests: int = 8,  # Максимум запросов
        window_seconds: float = 1.0  # Окно времени
    ):
        """
        Инициализация rate limiter.
        
        Координация через Redis: ВСЕ задачи (от всех пользователей и воркеров) 
        используют ОБЩИЙ счетчик запросов.
        
        Args:
            redis_url: URL Redis сервера
            key_prefix: Префикс для ключей в Redis
            max_requests: Максимум запросов в окне времени
            window_seconds: Размер окна в секундах
        """
        self.redis_client = redis.from_url(redis_url, decode_responses=False)
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        
        rate = max_requests / window_seconds
        logger.info(
            f"🔐 [Rate Limiter] Инициализирован: {max_requests} запросов / {window_seconds}с "
            f"({rate:.2f} req/sec) — координация ВСЕХ Celery задач через Redis"
        )
    
    def _get_key(self, identifier: str) -> str:
        """Формирует Redis ключ для идентификатора"""
        return f"{self.key_prefix}:{identifier}"
    
    def acquire(self, identifier: str = "default", blocking: bool = True, timeout: float = 30.0) -> bool:
        """
        Пытается получить разрешение на выполнение запроса.
        
        Использует алгоритм Sliding Window Counter:
        1. Получаем текущее время
        2. Удаляем старые записи (старше window_seconds)
        3. Проверяем количество запросов в окне
        4. Если < max_requests → добавляем запись и разрешаем
        5. Если >= max_requests → блокируем или ждём
        
        Args:
            identifier: Идентификатор rate limit (например, "poizon_api")
            blocking: Блокировать ли до получения разрешения
            timeout: Максимальное время ожидания (сек)
            
        Returns:
            True если разрешение получено, False если timeout
            
        Example:
            >>> limiter = RedisRateLimiter(max_requests=10, window_seconds=1)
            >>> if limiter.acquire("poizon_api"):
            ...     response = requests.get(api_url)
        """
        key = self._get_key(identifier)
        start_time = time.time()
        
        while True:
            current_time = time.time()
            window_start = current_time - self.window_seconds
            
            # Используем Redis pipeline для атомарности
            pipe = self.redis_client.pipeline()
            
            try:
                # 1. Удаляем старые записи (score < window_start)
                pipe.zremrangebyscore(key, 0, window_start)
                
                # 2. Получаем количество запросов в текущем окне
                pipe.zcard(key)
                
                # 3. Выполняем pipeline
                results = pipe.execute()
                current_count = results[1]
                
                # 4. Проверяем лимит
                if current_count < self.max_requests:
                    # Есть свободный слот → добавляем запись
                    request_id = f"{current_time}:{id(self)}"
                    self.redis_client.zadd(key, {request_id: current_time})
                    
                    # Устанавливаем TTL на ключ (чтобы не копились мёртвые ключи)
                    self.redis_client.expire(key, int(self.window_seconds * 2))
                    
                    return True
                
                # 5. Лимит исчерпан
                if not blocking:
                    return False
                
                # 6. Ждём немного и пробуем снова
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(
                        f"⏱️  [Rate Limiter] Timeout {timeout}с для '{identifier}' "
                        f"(текущий счёт: {current_count}/{self.max_requests})"
                    )
                    return False
                
                # Спим минимальное время до освобождения слота
                # Находим самый старый запрос в окне
                oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_time = oldest[0][1]
                    wait_time = max(0.01, (oldest_time + self.window_seconds) - current_time)
                    wait_time = min(wait_time, 0.5)  # Максимум 0.5с ожидания
                else:
                    wait_time = 0.1
                
                time.sleep(wait_time)
                
            except redis.RedisError as e:
                logger.error(f"❌ [Rate Limiter] Redis ошибка: {e}")
                # При ошибке Redis → разрешаем запрос (fail-open)
                return True
    
    def get_stats(self, identifier: str = "default") -> dict:
        """
        Получает статистику rate limiter.
        
        Args:
            identifier: Идентификатор rate limit
            
        Returns:
            Dict с полями:
                - current_count: текущее количество запросов в окне
                - max_requests: максимум запросов
                - window_seconds: размер окна
                - available: доступно слотов
                - utilization: загрузка в %
        """
        key = self._get_key(identifier)
        current_time = time.time()
        window_start = current_time - self.window_seconds
        
        try:
            # Удаляем старые записи
            self.redis_client.zremrangebyscore(key, 0, window_start)
            
            # Считаем текущие
            current_count = self.redis_client.zcard(key)
            
            available = max(0, self.max_requests - current_count)
            utilization = (current_count / self.max_requests * 100) if self.max_requests > 0 else 0
            
            return {
                'current_count': current_count,
                'max_requests': self.max_requests,
                'window_seconds': self.window_seconds,
                'available': available,
                'utilization': round(utilization, 1)
            }
        except redis.RedisError as e:
            logger.error(f"❌ [Rate Limiter] Ошибка получения статистики: {e}")
            return {
                'current_count': 0,
                'max_requests': self.max_requests,
                'window_seconds': self.window_seconds,
                'available': self.max_requests,
                'utilization': 0
            }
    
    def reset(self, identifier: str = "default"):
        """
        Сбрасывает счётчик для идентификатора.
        
        Args:
            identifier: Идентификатор rate limit
        """
        key = self._get_key(identifier)
        try:
            self.redis_client.delete(key)
            logger.info(f"🔄 [Rate Limiter] Сброшен лимит для '{identifier}'")
        except redis.RedisError as e:
            logger.error(f"❌ [Rate Limiter] Ошибка сброса: {e}")


# Глобальный экземпляр для использования во всех модулях
_global_limiter: Optional[RedisRateLimiter] = None


def get_rate_limiter(
    max_requests: int = 8,
    window_seconds: float = 1.0,
    redis_url: str = "redis://localhost:6379/0"
) -> RedisRateLimiter:
    """
    Получает глобальный экземпляр rate limiter (singleton).
    
    Args:
        max_requests: Максимум запросов в окне
        window_seconds: Размер окна в секундах
        redis_url: URL Redis сервера
        
    Returns:
        Экземпляр RedisRateLimiter
        
    Example:
        >>> limiter = get_rate_limiter(max_requests=10, window_seconds=1)
        >>> if limiter.acquire("poizon_api"):
        ...     response = requests.get(api_url)
    """
    global _global_limiter
    
    if _global_limiter is None:
        _global_limiter = RedisRateLimiter(
            redis_url=redis_url,
            max_requests=max_requests,
            window_seconds=window_seconds
        )
    
    return _global_limiter
