"""
Асинхронный HTTP клиент для параллельных запросов к API.

Использует aiohttp для неблокирующих запросов.
Поддерживает пул соединений, retry logic, rate limiting.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

# Пробуем импортировать aiohttp
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger.warning("aiohttp не установлен - асинхронные запросы недоступны")


@dataclass
class RequestConfig:
    """Конфигурация для HTTP запроса"""
    url: str
    method: str = "GET"
    params: Optional[Dict] = None
    json_data: Optional[Dict] = None
    headers: Optional[Dict] = None
    timeout: int = 30


class AsyncHTTPClient:
    """
    Асинхронный HTTP клиент с пулом соединений.
    
    Features:
    - Connection pooling
    - Automatic retry with exponential backoff
    - Rate limiting
    - Concurrent request batching
    """
    
    def __init__(
        self,
        max_concurrent: int = 10,
        requests_per_second: int = 5,
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Инициализация клиента.
        
        Args:
            max_concurrent: Максимум одновременных запросов
            requests_per_second: Ограничение запросов в секунду
            max_retries: Количество повторов при ошибке
            timeout: Таймаут запроса в секундах
        """
        if not AIOHTTP_AVAILABLE:
            raise ImportError("aiohttp не установлен. Установите: pip install aiohttp")
        
        self.max_concurrent = max_concurrent
        self.requests_per_second = requests_per_second
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Rate limiting
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limiter = asyncio.Semaphore(requests_per_second)
        self.last_request_time = 0
        
        # Статистика
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'retries': 0
        }
        
        logger.info(f"AsyncHTTPClient: concurrent={max_concurrent}, rate={requests_per_second} req/s")
    
    async def _rate_limit(self):
        """Применяет rate limiting"""
        min_interval = 1.0 / self.requests_per_second
        
        now = time.time()
        elapsed = now - self.last_request_time
        
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        
        self.last_request_time = time.time()
    
    async def fetch(
        self,
        session: aiohttp.ClientSession,
        config: RequestConfig
    ) -> Optional[Dict]:
        """
        Выполняет один HTTP запрос с retry logic.
        
        Args:
            session: aiohttp session
            config: Конфигурация запроса
            
        Returns:
            JSON ответ или None при ошибке
        """
        async with self.semaphore:
            self.stats['total_requests'] += 1
            
            for attempt in range(self.max_retries):
                try:
                    # Rate limiting
                    await self._rate_limit()
                    
                    # Выполняем запрос
                    async with session.request(
                        method=config.method,
                        url=config.url,
                        params=config.params,
                        json=config.json_data,
                        headers=config.headers,
                        timeout=aiohttp.ClientTimeout(total=config.timeout)
                    ) as response:
                        response.raise_for_status()
                        data = await response.json()
                        
                        self.stats['successful_requests'] += 1
                        return data
                
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout для {config.url}, попытка {attempt + 1}/{self.max_retries}")
                    self.stats['retries'] += 1
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue
                
                except aiohttp.ClientError as e:
                    logger.error(f"HTTP ошибка {config.url}: {e}")
                    self.stats['retries'] += 1
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                
                except Exception as e:
                    logger.error(f"Неожиданная ошибка {config.url}: {e}")
                    break
            
            # Все попытки исчерпаны
            self.stats['failed_requests'] += 1
            return None
    
    async def fetch_many(
        self,
        configs: List[RequestConfig]
    ) -> List[Optional[Dict]]:
        """
        Выполняет несколько запросов параллельно.
        
        Args:
            configs: Список конфигураций запросов
            
        Returns:
            Список результатов (None для failed запросов)
        """
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent,
            limit_per_host=self.max_concurrent,
            ttl_dns_cache=300
        )
        
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self.fetch(session, config) for config in configs]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            return results
    
    def get_stats(self) -> dict:
        """Получить статистику запросов"""
        success_rate = 0
        if self.stats['total_requests'] > 0:
            success_rate = (self.stats['successful_requests'] / self.stats['total_requests']) * 100
        
        return {
            **self.stats,
            'success_rate': f"{success_rate:.1f}%"
        }


# Синхронная обертка для использования в синхронном коде
class SyncAsyncHTTPClient:
    """Синхронная обертка над AsyncHTTPClient для использования в обычном коде"""
    
    def __init__(self, **kwargs):
        self.client = AsyncHTTPClient(**kwargs)
    
    def fetch_many(self, configs: List[RequestConfig]) -> List[Optional[Dict]]:
        """Синхронный вызов fetch_many"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.client.fetch_many(configs))
        finally:
            loop.close()
    
    def get_stats(self) -> dict:
        return self.client.get_stats()


if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    if AIOHTTP_AVAILABLE:
        print("\n=== Тест асинхронных запросов ===")
        
        # Создаем конфигурации запросов
        configs = [
            RequestConfig(url="https://httpbin.org/delay/1"),
            RequestConfig(url="https://httpbin.org/delay/2"),
            RequestConfig(url="https://httpbin.org/delay/1"),
        ]
        
        client = SyncAsyncHTTPClient(max_concurrent=3, requests_per_second=2)
        
        start = time.time()
        results = client.fetch_many(configs)
        elapsed = time.time() - start
        
        print(f"Выполнено {len(configs)} запросов за {elapsed:.2f}s")
        print(f"Успешно: {sum(1 for r in results if r is not None)}")
        print(f"Статистика: {client.get_stats()}")
    else:
        print("aiohttp не установлен")
