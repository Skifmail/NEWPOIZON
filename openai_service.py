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
        # Сначала пробуем взять полную строку прокси
        self.proxy = os.getenv('OPENAI_PROXY')
        
        # Если полной строки нет, пробуем собрать из компонентов
        if not self.proxy:
            proxy_host = os.getenv('OPENAI_PROXY_HOST')
            proxy_port = os.getenv('OPENAI_PROXY_PORT', '50100')  # HTTP/HTTPS порт
            proxy_login = os.getenv('OPENAI_PROXY_LOGIN')
            proxy_password = os.getenv('OPENAI_PROXY_PASSWORD')
            
            if proxy_host and proxy_login and proxy_password:
                # Формат: http://login:password@host:port
                self.proxy = f"http://{proxy_login}:{proxy_password}@{proxy_host}:{proxy_port}"
        
        if self.proxy:
            # Логируем факт использования прокси (скрывая пароль)
            safe_proxy = self.proxy.split('@')[-1] if '@' in self.proxy else '***'
            logger.info(f"[OpenAI] Используется прокси: {safe_proxy}")
        else:
            self.proxy = None
        
        if 'api.openai.com' not in self.api_url:
            logger.info(f"[OpenAI] Используется альтернативный API: {self.api_url}")
            
        if not self.api_key:
            logger.warning("OPENAI_API_KEY не найден в .env")
    
    @staticmethod
    def clean_chinese_text(text: str) -> str:
        """
        Централизованная функция очистки текста от иероглифов.
        Удаляет китайские символы, оставляет латиницу, кириллицу, цифры.
        Конвертирует полноширинные символы в обычные.
        
        Args:
            text: Исходный текст
            
        Returns:
            Очищенный текст
        """
        if not text:
            return ""
        
        result = []
        for char in text:
            code = ord(char)
            # ASCII латиница, цифры и базовые символы
            if ((0x0041 <= code <= 0x005A) or   # A-Z
                (0x0061 <= code <= 0x007A) or   # a-z
                (0x0030 <= code <= 0x0039) or   # 0-9
                (0x0410 <= code <= 0x044F) or   # А-я (кириллица)
                code in [0x0020, 0x002D, 0x0027, 0x002E, 0x002C, 0x002F, 0x003A, 0x003B, 0x0028, 0x0029, 0x0021, 0x003F]):
                result.append(char)
            # Конвертация полноширинных латинских в обычные
            elif 0xFF21 <= code <= 0xFF3A:  # Ａ-Ｚ → A-Z
                result.append(chr(code - 0xFEE0))
            elif 0xFF41 <= code <= 0xFF5A:  # ａ-ｚ → a-z
                result.append(chr(code - 0xFEE0))
            elif 0xFF10 <= code <= 0xFF19:  # ０-９ → 0-9
                result.append(chr(code - 0xFEE0))
        
        return ''.join(result).strip()
    
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

        # Формируем целевое название (Категория + Бренд + Артикул)
        target_title = f"{category} {brand} {article_number}" if article_number else f"{category} {brand} {title}"

        # Формируем промпт точно как в poizon_api_fixed.py
        prompt = f"""Создай SEO-контент для товара.

ДАННЫЕ:
- Бренд: {brand}
- Товар: {category} {brand} {title}
- Артикул: {article_number}
- Цвет: {color}
- Материал: {material}

ФОРМАТ ОТВЕТА (6 строк):
1. {target_title} (СТРОГО: Категория Бренд Модель Артикул. БЕЗ слов: "купить", "buy", "стиль", "комфорт", "мужские", "женские". Только факты: тип, бренд, модель, артикул)
2. Краткое описание (200-350 символов)
3. Полное описание (минимум 600 символов), начни: "{brand} {title} {article_number} –"
4. SEO Title (до 60 символов, БЕЗ слова "купить")
5. Meta Description (130-150 символов), заканчивается "Закажи онлайн!"
6. Список тегов через точку с запятой. ИСКЛЮЧИТЬ слова: "Товар", "стиль", "комфорт", "теги". Пример: {brand}; {category}; обувь; кроссовки"""

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
                
                # Извлекаем поля и очищаем от иероглифов через централизованную функцию
                title_ru = self.clean_chinese_text(parsed_lines[0])
                short_desc = self.clean_chinese_text(parsed_lines[1])
                full_desc = self.clean_chinese_text(parsed_lines[2])
                seo_title = self.clean_chinese_text(parsed_lines[3])
                meta_desc = self.clean_chinese_text(parsed_lines[4])
                tags = self.clean_chinese_text(parsed_lines[5])
                
                # ЖЕСТКАЯ ОЧИСТКА НАЗВАНИЯ
                # 1. Если есть артикул - находим его позицию и обрезаем ВСЁ после него
                if article_number and article_number in title_ru:
                    # Находим позицию артикула
                    article_pos = title_ru.find(article_number)
                    # Обрезаем строку: всё до конца артикула + удаляем всё что идёт после артикула
                    title_ru = title_ru[:article_pos + len(article_number)]
                    
                    # Удаляем любые символы и пробелы после артикула
                    title_ru = title_ru.rstrip(' -–—.,:;')
                    
                    # КРИТИЧНО: Если после артикула идут слова (цвет, описание и т.д.), удаляем их тоже
                    # Разбиваем по пробелам и берём только до артикула
                    import re
                    # Регулярка: находим всё что идёт ПОСЛЕ артикула (включая описания типа "белого цвета")
                    title_ru = re.sub(rf'{re.escape(article_number)}\s+.*', article_number, title_ru)
                
                # 2. Если артикула нет, берём только первые 4 слова (Категория Бренд Модель Дополнение)
                elif ' ' in title_ru:
                    words = title_ru.split()
                    if len(words) > 4:
                        title_ru = ' '.join(words[:4])
                
                # 3. Принудительно добавляем категорию в начало, если её нет
                if category and not title_ru.lower().startswith(category.lower()):
                    title_ru = f"{category} {title_ru}"
                
                # 4. Удаляем повторяющуюся категорию (если OpenAI её продублировал)
                if category:
                    category_lower = category.lower()
                    words = title_ru.split()
                    # Если категория встречается 2 раза подряд - удаляем дубль
                    if len(words) >= 2 and words[0].lower() == category_lower and words[1].lower() == category_lower:
                        title_ru = ' '.join(words[1:])
                
                title_ru = " ".join(title_ru.split()) # Убираем двойные пробелы

                # Дополнительная очистка тегов
                if tags.lower().startswith('теги:') or tags.lower().startswith('tags:'):
                    tags = tags.split(':', 1)[1].strip()
                
                # Нормализация разделителей
                tags = tags.replace(',', ';').replace('/', ';').replace('|', ';')
                
                # Фильтрация мусорных тегов
                clean_tags = []
                for tag in tags.split(';'):
                    tag = tag.strip()
                    if not tag: continue
                    if tag.lower() in ['товар', 'стиль', 'комфорт', 'теги', 'tags', 'product', 'style', 'comfort']:
                        continue
                    clean_tags.append(tag)
                
                tags = "; ".join(clean_tags)
                
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
