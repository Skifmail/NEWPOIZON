"""
Circuit Breaker для защиты от падения внешних API.

Автоматически "размыкает" цепь при частых ошибках и переводит в режим fallback.
После timeout автоматически пробует восстановить подключение.

States:
- CLOSED: нормальная работа
- OPEN: API недоступен, все запросы возвращают ошибку
- HALF_OPEN: пробуем восстановление
"""
import time
import logging
import threading
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Состояния circuit breaker"""
    CLOSED = "closed"  # Нормальная работа
    OPEN = "open"  # Размокнуто, запросы блокируются
    HALF_OPEN = "half_open"  # Пробуем восстановление


class CircuitBreakerError(Exception):
    """Исключение когда circuit breaker разомкнут"""
    pass


class CircuitBreaker:
    """
    Circuit Breaker с автоматическим восстановлением.
    
    Защищает от каскадного падения при недоступности внешних сервисов.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
        name: str = "unnamed"
    ):
        """
        Инициализация circuit breaker.
        
        Args:
            failure_threshold: Количество ошибок до размыкания
            recovery_timeout: Время в секундах до попытки восстановления
            expected_exception: Тип исключения который считаем ошибкой
            name: Имя для логирования
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        
        self.lock = threading.Lock()
        
        # Статистика
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'rejected_requests': 0,
            'state_changes': []
        }
        
        logger.info(f"Circuit Breaker '{name}' инициализирован: threshold={failure_threshold}, timeout={recovery_timeout}s")
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Вызывает функцию через circuit breaker.
        
        Args:
            func: Функция для вызова
            *args, **kwargs: Аргументы функции
            
        Returns:
            Результат функции
            
        Raises:
            CircuitBreakerError: Если circuit разомкнут
        """
        with self.lock:
            self.stats['total_requests'] += 1
            
            # Проверяем состояние
            if self.state == CircuitState.OPEN:
                # Проверяем можно ли перейти в HALF_OPEN
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    # Блокируем запрос
                    self.stats['rejected_requests'] += 1
                    logger.warning(f"[{self.name}] Circuit OPEN - запрос отклонен")
                    raise CircuitBreakerError(f"Circuit breaker '{self.name}' is OPEN")
        
        # Пытаемся выполнить запрос
        try:
            result = func(*args, **kwargs)
            
            # Успешный запрос
            with self.lock:
                self.stats['successful_requests'] += 1
                self._on_success()
            
            return result
            
        except self.expected_exception as e:
            # Ошибка запроса
            with self.lock:
                self.stats['failed_requests'] += 1
                self._on_failure()
            
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Проверяет можно ли попробовать восстановление"""
        if self.last_failure_time is None:
            return True
        
        return time.time() - self.last_failure_time >= self.recovery_timeout
    
    def _transition_to_half_open(self):
        """Переход в состояние HALF_OPEN"""
        logger.info(f"[{self.name}] Circuit: OPEN → HALF_OPEN (пробуем восстановление)")
        self.state = CircuitState.HALF_OPEN
        self.stats['state_changes'].append({
            'from': 'OPEN',
            'to': 'HALF_OPEN',
            'time': datetime.now().isoformat()
        })
    
    def _on_success(self):
        """Обработка успешного запроса"""
        if self.state == CircuitState.HALF_OPEN:
            # Восстанавливаем circuit
            logger.info(f"[{self.name}] Circuit: HALF_OPEN → CLOSED (восстановлено)")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.stats['state_changes'].append({
                'from': 'HALF_OPEN',
                'to': 'CLOSED',
                'time': datetime.now().isoformat()
            })
        else:
            # Сбрасываем счетчик ошибок
            self.failure_count = max(0, self.failure_count - 1)
    
    def _on_failure(self):
        """Обработка ошибки запроса"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # Сразу размыкаем обратно
            logger.warning(f"[{self.name}] Circuit: HALF_OPEN → OPEN (восстановление не удалось)")
            self.state = CircuitState.OPEN
            self.stats['state_changes'].append({
                'from': 'HALF_OPEN',
                'to': 'OPEN',
                'time': datetime.now().isoformat()
            })
        elif self.failure_count >= self.failure_threshold:
            # Размыкаем circuit
            logger.error(f"[{self.name}] Circuit: CLOSED → OPEN (threshold {self.failure_threshold} достигнут)")
            self.state = CircuitState.OPEN
            self.stats['state_changes'].append({
                'from': 'CLOSED',
                'to': 'OPEN',
                'time': datetime.now().isoformat(),
                'failure_count': self.failure_count
            })
    
    def reset(self):
        """Ручной сброс circuit breaker"""
        with self.lock:
            logger.info(f"[{self.name}] Circuit: ручной сброс → CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = None
    
    def get_state(self) -> CircuitState:
        """Получить текущее состояние"""
        return self.state
    
    def get_stats(self) -> dict:
        """Получить статистику"""
        with self.lock:
            success_rate = 0
            if self.stats['total_requests'] > 0:
                success_rate = (self.stats['successful_requests'] / self.stats['total_requests']) * 100
            
            return {
                **self.stats,
                'current_state': self.state.value,
                'failure_count': self.failure_count,
                'success_rate': f"{success_rate:.1f}%"
            }


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception,
    name: str = None
):
    """
    Декоратор для применения circuit breaker к функции.
    
    Args:
        failure_threshold: Количество ошибок до размыкания
        recovery_timeout: Время до попытки восстановления (сек)
        expected_exception: Тип исключения
        name: Имя для логирования
    
    Example:
        @circuit_breaker(failure_threshold=3, recovery_timeout=30, name='poizon_api')
        def fetch_products():
            return api.get_products()
    """
    def decorator(func):
        # Создаем circuit breaker для функции
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception,
            name=name or func.__name__
        )
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        
        # Прикрепляем circuit breaker к функции для доступа к статистике
        wrapper.circuit_breaker = breaker
        
        return wrapper
    
    return decorator


# Глобальные circuit breakers для разных сервисов
_circuit_breakers = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """
    Получить или создать circuit breaker для сервиса.
    
    Args:
        name: Имя сервиса (poizon_api, wordpress_api, openai_api)
        **kwargs: Параметры для CircuitBreaker
        
    Returns:
        CircuitBreaker instance
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _circuit_breakers[name]


if __name__ == "__main__":
    # Тестирование
    logging.basicConfig(level=logging.INFO)
    
    print("\n=== Тест Circuit Breaker ===")
    
    @circuit_breaker(failure_threshold=3, recovery_timeout=5, name='test_api')
    def unstable_api_call():
        """Нестабильный API вызов"""
        import random
        if random.random() < 0.7:  # 70% вероятность ошибки
            raise Exception("API error")
        return "Success"
    
    # Генерируем ошибки
    for i in range(10):
        try:
            result = unstable_api_call()
            print(f"Попытка {i+1}: {result}")
        except CircuitBreakerError as e:
            print(f"Попытка {i+1}: Circuit OPEN - {e}")
        except Exception as e:
            print(f"Попытка {i+1}: Ошибка - {e}")
        
        time.sleep(0.5)
    
    # Статистика
    print(f"\nСтатистика: {unstable_api_call.circuit_breaker.get_stats()}")
