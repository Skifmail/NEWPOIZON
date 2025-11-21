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
        
        # Поддержка кастомного Base URL (для ProxyAPI, VseGPT и т.д.)
        base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        self.api_url = f"{base_url}/chat/completions"
        
        # Настройка прокси для OpenAI (для обхода блокировок)
        proxy_host = os.getenv('OPENAI_PROXY_HOST')
        proxy_port = os.getenv('OPENAI_PROXY_PORT', '50100')  # HTTP/HTTPS порт
        proxy_login = os.getenv('OPENAI_PROXY_LOGIN')
        proxy_password = os.getenv('OPENAI_PROXY_PASSWORD')
        
        if proxy_host and proxy_login and proxy_password:
            # Формат: http://login:password@host:port
            self.proxy = f"http://{proxy_login}:{proxy_password}@{proxy_host}:{proxy_port}"
            logger.info(f"[OpenAI] Используется прокси: {proxy_login}@{proxy_host}:{proxy_port}")
        else:
            self.proxy = None
        
        if 'api.openai.com' not in self.api_url:
            logger.info(f"[OpenAI] Используется альтернативный API: {self.api_url}")
            
        if not self.api_key:
            logger.warning("OPENAI_API_KEY не найден в .env")
    
    def translate_and_generate_seo(self, title: str, description: str, category: str, brand: str, attributes: list = None, article_number: str = "") -> dict:
        """
        Генерирует SEO-контент, используя промпт из poizon_api_fixed.py.
        Адаптирует аргументы под формат промпта.
        """
        if not self.api_key:
            return {}

        # Извлечение цвета и материала из атрибутов
        color = ""
        material = ""
        if attributes:
            for attr in attributes:
                if isinstance(attr, dict):
                    name = attr.get('name', '').lower()
                    value = attr.get('value', '')
                    if 'color' in name or 'цвет' in name:
                        color = value
                    elif 'material' in name or 'материал' in name:
                        material = value

        # Формируем промпт точно как в poizon_api_fixed.py
        prompt = f"""Создай SEO-контент для товара.

ДАННЫЕ:
- Бренд: {brand}
- Товар: {category} {brand} {title}
- Артикул: {article_number}
- Цвет: {color}
- Материал: {material}

ФОРМАТ ОТВЕТА (6 строк):
1. {category} {brand} {title}
2. Краткое описание (200-350 символов)
3. Полное описание (минимум 600 символов), начни: "{brand} {title} {article_number} –"
4. SEO Title (до 60 символов)
5. Meta Description (130-150 символов), заканчивается "Закажи онлайн!"
6. Теги: {brand}"""

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "Ты SEO-копирайтер"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
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
                    timeout=30,
                    proxies=proxies
                )
            )
            
            if response.status_code == 200:
                result = response.json()
                result_text = result['choices'][0]['message']['content'].strip()
                usage = result.get('usage', {})
                total_tokens = usage.get('total_tokens', 0)
                
                logger.info(f"[OpenAI] SEO контент сгенерирован для '{title}' (tokens: {total_tokens})")
                
                # Парсим ответ (логика из poizon_api_fixed.py)
                lines = result_text.split('\n')
                parsed_lines = []
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    # Убираем нумерацию
                    if line and len(line) > 3:
                        if line[0].isdigit() and line[1:3] in ['. ', ') ', ': ']:
                            line = line[3:].strip()
                        elif line[:2].isdigit() and line[2:4] in ['. ', ') ', ': ']:
                            line = line[4:].strip()
                    
                    if line:
                        parsed_lines.append(line)
                
                if len(parsed_lines) < 6:
                    logger.error(f"[OpenAI] Недостаточно строк в ответе: {len(parsed_lines)}")
                    return {}
                
                # Очистка от китайских символов
                def clean_chinese(text: str) -> str:
                    result = []
                    for char in text:
                        code = ord(char)
                        if ((0x0041 <= code <= 0x005A) or  # A-Z
                            (0x0061 <= code <= 0x007A) or  # a-z
                            (0x0030 <= code <= 0x0039) or  # 0-9
                            (0x0410 <= code <= 0x044F) or  # А-я
                            code in [0x0020, 0x002D, 0x0027, 0x002E, 0x002C, 0x002F, 0x003A, 0x003B, 0x0028, 0x0029, 0x0021, 0x003F]):
                            result.append(char)
                    return ''.join(result).strip()
                
                # Извлекаем поля и очищаем от иероглифов
                title_ru = clean_chinese(parsed_lines[0])
                short_desc = clean_chinese(parsed_lines[1])
                full_desc = clean_chinese(parsed_lines[2])
                seo_title = clean_chinese(parsed_lines[3])
                meta_desc = clean_chinese(parsed_lines[4])
                tags = clean_chinese(parsed_lines[5])
                
                return {
                    'title_ru': title_ru,
                    'short_description': short_desc,
                    'full_description': full_desc,
                    'seo_title': seo_title,
                    'meta_description': meta_desc,
                    'keywords': tags,
                    'tokens': total_tokens
                }
                
            else:
                logger.error(f"[OpenAI] Ошибка API {response.status_code}: {response.text}")
                return {}
                
        except CircuitBreakerError:
            logger.warning("[OpenAI] API временно недоступен (Circuit Breaker open)")
            return {}
        except Exception as e:
            logger.error(f"[OpenAI] Ошибка генерации SEO: {e}")
            return {}

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
