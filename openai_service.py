"""
Сервис для работы с OpenAI API.
Вынесен в отдельный модуль для устранения циклических импортов.
"""
import os
import logging
import requests
from circuit_breaker import get_circuit_breaker, CircuitBreakerError

logger = logging.getLogger(__name__)

# Инициализация Circuit Breaker для OpenAI
openai_breaker = get_circuit_breaker(
    name='openai_api',
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=Exception
)

class OpenAIService:
    """Сервис для генерации SEO-описаний через GPT-5 Nano"""
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.api_url = "https://api.openai.com/v1/chat/completions"
        
        # Проверяем наличие прокси для OpenAI
        self.proxy = os.getenv('OPENAI_PROXY')
        if self.proxy:
            logger.info(f"[OpenAI] Используется прокси: {self.proxy}")
            
        if not self.api_key:
            logger.warning("OPENAI_API_KEY не найден в .env")
    
    def generate_seo_description(self, product_title: str, brand: str, category: str) -> str:
        """
        Генерирует SEO-оптимизированное описание товара.
        
        Args:
            product_title: Название товара
            brand: Бренд
            category: Категория
            
        Returns:
            Сгенерированное описание или пустую строку при ошибке
        """
        if not self.api_key:
            return ""
            
        try:
            prompt = f"""
            Напиши продающее SEO-описание для товара:
            Название: {product_title}
            Бренд: {brand}
            Категория: {category}
            
            Требования:
            1. Уникальность и привлекательность для покупателя
            2. Использовать ключевые слова: купить, цена, оригинал, доставка
            3. Длина: 3-4 предложения
            4. Язык: Русский
            5. Без воды, только по делу
            """
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-4o-mini",  # Используем доступную модель
                "messages": [
                    {"role": "system", "content": "Ты профессиональный копирайтер для интернет-магазина кроссовок и одежды."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 300
            }
            
            # Настройка прокси если есть
            proxies = None
            if self.proxy:
                proxies = {
                    "http": self.proxy,
                    "https": self.proxy
                }
            
            # Вызов API с защитой Circuit Breaker
            response = openai_breaker.call(
                lambda: requests.post(
                    self.api_url, 
                    headers=headers, 
                    json=data, 
                    timeout=15,
                    proxies=proxies
                )
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()
                logger.info(f"[OpenAI] Описание сгенерировано для '{product_title}'")
                return content
            else:
                logger.error(f"[OpenAI] Ошибка API {response.status_code}: {response.text}")
                return ""
                
        except CircuitBreakerError:
            logger.warning("[OpenAI] API временно недоступен (Circuit Breaker open)")
            return ""
        except Exception as e:
            logger.error(f"[OpenAI] Ошибка генерации описания: {e}")
            return ""
