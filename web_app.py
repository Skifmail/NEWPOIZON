"""
Веб-приложение для синхронизации товаров Poizon → WordPress.

Это Flask веб-приложение предоставляет графический интерфейс для:
- Поиска товаров на Poizon по ключевым словам
- Просмотра товаров с изображениями и ценами
- Выбора товаров для загрузки в WordPress
- Настройки курса валюты и наценки
- Автоматической генерации SEO-оптимизированных описаний через GigaChat
- Загрузки товаров в WooCommerce с вариациями (размеры, цвета)

Технологии:
    - Flask: веб-фреймворк
    - Server-Sent Events (SSE): потоковая передача прогресса загрузки
    - In-memory кэш: минимизация запросов к API
    - Файловый кэш: долговременное хранение брендов (обновление раз в месяц)
    - GigaChat API: генерация описаний товаров

Архитектура:
    /api/search - поиск товаров в Poizon
    /api/upload-stream - загрузка товаров с потоковым прогрессом
    /api/gigachat-generate - генерация описаний через AI
    
Безопасность:
    - Работает только локально (127.0.0.1)
    - Не требует внешнего доступа
    
"""
import os
import logging
import requests
import json
from typing import Dict, List, Optional
from flask import Flask, render_template, jsonify, request, Response, stream_with_context, session, redirect, url_for, flash
from werkzeug.security import check_password_hash
from functools import wraps
from dotenv import load_dotenv
from dataclasses import dataclass, asdict
from pathlib import Path
import time
import uuid
from datetime import datetime, timedelta
import queue
import threading

# Импорт существующих модулей
from poizon_to_wordpress_service import (
    WooCommerceService,
    SyncSettings
)
from poizon_api_fixed import PoisonAPIClientFixed as PoisonAPIService

# Импорт новых улучшений
# Fallback-импорты: если модулей нет в проекте, используем простые заглушки
try:
    from unified_cache import get_cache
except ImportError:  # упрощенный кэш в памяти
    class _SimpleCache:
        def __init__(self):
            self._store = {}
            self.stats = {}

        def get(self, key, namespace=None):
            return self._store.get((namespace, key)) if namespace else self._store.get(key)

        def set(self, key, value, ttl=None, namespace=None):
            if namespace:
                self._store[(namespace, key)] = value
            else:
                self._store[key] = value

        def clear(self):
            self._store.clear()

        def get_stats(self):
            return dict(self.stats)

    def get_cache():
        return _SimpleCache()

try:
    from circuit_breaker import get_circuit_breaker, CircuitBreakerError
except ImportError:
    class CircuitBreakerError(Exception):
        pass

    class _DummyBreaker:
        def call(self, fn):
            return fn()

    def get_circuit_breaker(*args, **kwargs):
        return _DummyBreaker()

# Попытка импорта Celery (опционально для асинхронной обработки)
try:
    from celery_tasks import batch_upload_products
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    batch_upload_products = None

# Настройка логирования (конфигурируем root logger для совместимости с Flask)
import logging.handlers

# Создаем папку для логов если не существует
from pathlib import Path
log_dir = Path("kash")
log_dir.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Создаем и настраиваем handlers (однократно)
file_handler = logging.FileHandler('kash/web_app.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Формат логов
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Настраиваем root logger и избегаем дублирования хендлеров
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
if not root_logger.handlers:
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# Сообщение о доступности Celery после настройки логов
root_logger.info(f"[Celery] {'✅ Доступен' if CELERY_AVAILABLE else '⚠️  Недоступен (используется threading)'}")

# Отключаем DEBUG логи от сторонних библиотек (urllib3, requests и т.д.)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

# Настраиваем werkzeug чтобы избежать дублирования
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.setLevel(logging.INFO)
werkzeug_logger.propagate = False  # Не передавать логи root logger (избегаем дублей)
# Добавляем наши handlers напрямую к werkzeug
if not werkzeug_logger.handlers:
    werkzeug_logger.addHandler(file_handler)
    werkzeug_logger.addHandler(console_handler)

# Используем root logger напрямую (уже настроен выше с file_handler + console_handler)
logger = root_logger

# Загрузка переменных окружения
load_dotenv()

# Инициализация Flask
app = Flask(__name__)

# СТАБИЛЬНЫЙ SECRET_KEY из окружения, чтобы сессии не слетали при рестарте
secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    logger.warning("[SECURITY] SECRET_KEY не задан в .env — используется дефолтный dev-ключ. Установите SECRET_KEY для продакшена.")
    secret_key = 'dev-change-me'  # стабильный dev-ключ; заменить в продакшене
app.config['SECRET_KEY'] = secret_key

# Настройки сессий: длительность и безопасность куки
app.config['JSON_AS_ASCII'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
session_days = int(os.getenv('SESSION_DAYS', '7'))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=session_days)

# ============================================================================
# КЭШИРОВАНИЕ (унифицированный трехуровневый кэш)
# ============================================================================
# УДАЛЕНО: SimpleCache заменен на UnifiedCache из unified_cache.py
# UnifiedCache предоставляет:
# - L1 (Memory): 5 мин TTL, быстрый доступ
# - L2 (Redis): 24ч TTL, shared между процессами (опционально)
# - L3 (File): 30 дней TTL, персистентный
# Автоматический fallback: Redis недоступен → File cache


# ============================================================================
# ФАЙЛОВЫЙ КЭШ (для долговременного хранения брендов)
# ============================================================================

class BrandFileCache:
    """
    Файловый кэш для брендов с автоматическим обновлением раз в месяц.
    
    Сохраняет полный список брендов в JSON файл в папке kash/.
    При перезапуске сервиса загружает бренды из файла.
    Автоматически обновляет данные через API раз в 30 дней.
    
    Attributes:
        cache_dir (Path): Директория для хранения кэша (kash/)
        brands_file (Path): Файл с брендами (kash/brands_cache.json)
        ttl_days (int): Время жизни кэша в днях (по умолчанию 30)
    """
    
    def __init__(self, cache_dir: str = "kash", ttl_days: int = 30):
        """
        Инициализация файлового кэша.
        
        Args:
            cache_dir: Название директории для кэша
            ttl_days: Время жизни кэша в днях
        """
        self.cache_dir = Path(cache_dir)
        self.brands_file = self.cache_dir / "brands_cache.json"
        self.ttl_days = ttl_days
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        
        # Создаем директорию если не существует
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Создает директорию кэша если её нет."""
        if not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[FILE CACHE] Создана папка кэша: {self.cache_dir.absolute()}")
        # Убрано DEBUG: папка кэша существует
    
    def is_expired(self) -> bool:
        """
        Проверяет, истёк ли срок кэша.
        
        Returns:
            True если кэш устарел или не существует
        """
        if not self.brands_file.exists():
            logger.info("[FILE CACHE] Файл кэша брендов не найден")
            return True
        
        # Проверяем время последнего изменения файла
        file_mtime = self.brands_file.stat().st_mtime
        file_age = time.time() - file_mtime
        
        if file_age > self.ttl_seconds:
            days_old = file_age / (24 * 60 * 60)
            logger.info(f"[FILE CACHE] Кэш брендов устарел ({days_old:.1f} дней, лимит {self.ttl_days} дней)")
            return True
        
        # Убрано DEBUG: кэш актуален
        return False
    
    def load(self) -> Optional[List[Dict]]:
        """
        Загружает бренды из файла.
        
        Returns:
            Список брендов или None если файл не существует/поврежден
        """
        if not self.brands_file.exists():
            logger.info("[FILE CACHE] Файл брендов не найден")
            return None
        
        try:
            with open(self.brands_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            brands = data.get('brands', [])
            timestamp = data.get('timestamp', 0)
            created = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            
            logger.info(f"[FILE CACHE] Загружено {len(brands)} брендов из файла (создан: {created})")
            return brands
            
        except Exception as e:
            logger.error(f"[FILE CACHE] Ошибка чтения файла брендов: {e}")
            return None
    
    def save(self, brands: List[Dict]):
        """
        Сохраняет бренды в файл.
        
        Args:
            brands: Список брендов для сохранения
        """
        try:
            data = {
                'brands': brands,
                'timestamp': time.time(),
                'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(brands)
            }
            
            with open(self.brands_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[FILE CACHE] Сохранено {len(brands)} брендов в {self.brands_file}")
            
        except Exception as e:
            logger.error(f"[FILE CACHE] Ошибка сохранения брендов: {e}")
    
    def get_or_fetch(self, fetch_function) -> List[Dict]:
        """
        Получает бренды из кэша или загружает через API если нужно.
        
        Args:
            fetch_function: Функция для загрузки брендов через API (callable без параметров)
            
        Returns:
            Список брендов
        """
        # Проверяем, нужно ли обновить кэш
        if self.is_expired():
            logger.info("[FILE CACHE] Обновление кэша брендов через API...")
            brands = fetch_function()  # Вызываем переданную функцию
            self.save(brands)
            return brands
        
        # Загружаем из файла
        brands = self.load()
        if brands:
            return brands
        
        # Если не удалось загрузить из файла - загружаем через API
        logger.warning("[FILE CACHE] Не удалось загрузить из файла, загружаем через API")
        brands = fetch_function()  # Вызываем переданную функцию
        self.save(brands)
        return brands


# ============================================================================
# СОЗДАНИЕ ГЛОБАЛЬНОГО КЕША (UnifiedCache)
# ============================================================================
# Создаем единый трехуровневый кеш
# Работает даже без Redis (fallback на file cache)
cache = get_cache()

# УДАЛЕНО: BrandFileCache - теперь все кеширование через UnifiedCache
# brand_file_cache встроен в L3 (File) уровень UnifiedCache

# ============================================================================
# КАТЕГОРИИ И ФИЛЬТРАЦИЯ
# ============================================================================

# Словарь категорий и ключевых слов (на основе анализа dewu.com)
CATEGORY_KEYWORDS = {
    # ОБУВЬ (29)
    29: {
        'keywords': ['鞋', '运动鞋', '板鞋', '跑鞋', '篮球鞋', '足球鞋', '球鞋', '拖鞋', '凉鞋', '靴', '靴子', '滑板鞋',
                    'shoes', 'sneakers', 'boots', 'sandals', 'trainers', 'loafers', 'slippers', 'footwear'],
        'search_terms': ['sneakers', 'shoes', 'boots', 'trainers', 'sandals', 'loafers', 'slippers', 'footwear']
    },
    
    # ЖЕНСКАЯ ОДЕЖДА (1000095)
    1000095: {
        'keywords': ['女装', '女士', '女款', 'T恤', '卫衣', '外套', '裤子', '短裤', '裙', '连衣裙',
                    'women clothing', 'dress', 'blouse', 'skirt', 'top', 't-shirt', 'jacket', 
                    'pants', 'jeans', 'women', 'coat', 'sweater'],
        'search_terms': ['women clothing', 'dress', 'blouse', 'skirt', 'women jacket', 'women pants', 'women jeans']
    },
    
    # МУЖСКАЯ ОДЕЖДА (1000096)
    1000096: {
        'keywords': ['男装', '男士', '男款', 'T恤', '卫衣', '外套', '裤子', '短裤',
                    'men clothing', 'shirt', 't-shirt', 'jacket', 'pants', 'jeans', 
                    'sweater', 'hoodie', 'men', 'coat'],
        'search_terms': ['men clothing', 'shirt', 'men jacket', 'men pants', 'jeans', 'sweater', 'hoodie']
    },
    
    # АКСЕССУАРЫ (92)
    92: {
        'keywords': ['帽子', '眼镜', '围巾', '手套', '袜子', '腰带', '领带', '发带',
                    'accessories', 'belt', 'hat', 'cap', 'necklace', 'earring', 'bracelet', 
                    'ring', 'sunglasses', 'scarf', 'gloves', 'socks'],
        'search_terms': ['accessories', 'belt', 'hat', 'cap', 'necklace', 'sunglasses']
    },
    
    # СУМКИ И РЮКЗАКИ (48)
    48: {
        'keywords': ['包', '背包', '手提包', '单肩包', '斜挎包', '钱包',
                    'bag', 'handbag', 'tote', 'shoulder bag', 'clutch', 'crossbody bag', 
                    'purse', 'backpack', 'rucksack', 'school bag', 'laptop backpack', 'sports backpack'],
        'search_terms': ['bag', 'handbag', 'tote', 'backpack', 'shoulder bag', 'clutch', 'crossbody bag']
    },
    
    # КОСМЕТИКА И ПАРФЮМЕРИЯ (278)
    278: {
        'keywords': ['香水', '口红', '面膜', '护肤', '化妆', '精华', '乳液', '面霜',
                    'cosmetics', 'perfume', 'skincare', 'lipstick', 'foundation', 
                    'eyeshadow', 'mascara', 'toner', 'moisturizer', 'fragrance'],
        'search_terms': ['cosmetics', 'perfume', 'skincare', 'lipstick', 'foundation', 'fragrance', 'moisturizer']
    },
}


def filter_products_by_category(products: List[Dict], category_id: int) -> List[Dict]:
    """
    Фильтрует товары по категории на основе ключевых слов в названии
    
    Args:
        products: Список товаров
        category_id: ID категории
        
    Returns:
        list: Отфильтрованные товары
    """
    if not category_id or category_id not in CATEGORY_KEYWORDS:
        logger.warning(f"Нет ключевых слов для категории {category_id}, показываем все товары")
        return products
    
    keywords = CATEGORY_KEYWORDS[category_id]['keywords']
    filtered = []
    
    for product in products:
        title = product.get('title', '').lower()
        
        # Проверяем наличие хотя бы одного ключевого слова
        if any(keyword.lower() in title for keyword in keywords):
            filtered.append(product)
    
    logger.info(f"Фильтрация: {len(products)} товаров → {len(filtered)} (категория {category_id})")
    return filtered


# Глобальные клиенты
poizon_client = None
woocommerce_client = None
openai_client = None

# Очередь для прогресс-событий (SSE)
progress_queues = {}  # {session_id: queue.Queue()}


# ============================================================================
# АВТОРИЗАЦИЯ
# ============================================================================

def login_required(f):
    """Декоратор для проверки авторизации"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Необходима авторизация для доступа к этой странице', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@dataclass
class ProcessingStatus:
    """Статус обработки товара"""
    product_id: str
    status: str  # pending, processing, gigachat, wordpress, completed, error
    progress: int
    message: str
    timestamp: str


class OpenAIService:
    """Клиент для работы с OpenAI API"""
    
    def __init__(self):
        """Инициализация клиента OpenAI"""
        logger.info("="*80)
        logger.info("🤖 [OpenAI] Инициализация OpenAI сервиса...")
        
        self.api_key = os.getenv('OPENAI_API_KEY')
        
        if not self.api_key:
            logger.error("❌ [OpenAI] OPENAI_API_KEY не найден в .env файле!")
            self.enabled = False
        else:
            masked_key = f"{self.api_key[:7]}...{self.api_key[-4:]}"
            logger.info(f"✅ [OpenAI] API ключ загружен: {masked_key}")
            logger.info(f"🚀 [OpenAI] Модель: gpt-4o (новейшая флагманская модель)")
            self.enabled = True
            
        logger.info(f"🔌 [OpenAI] Статус сервиса: {'ВКЛЮЧЕН ✅' if self.enabled else 'ВЫКЛЮЧЕН ❌'}")
        logger.info("="*80)
    
    def translate_color(self, color_chinese: str) -> str:
        """
        Переводит название цвета с китайского на русский через OpenAI.
        
        Args:
            color_chinese: Название цвета на китайском (например "黑白灰")
            
        Returns:
            Переведенное название цвета на русском
        """
        if not self.enabled or not color_chinese:
            return color_chinese
        
        # Быстрая проверка - если уже латиница/кириллица, не переводим
        if all(ord(c) < 0x4E00 for c in color_chinese.replace(' ', '')):
            return color_chinese
        
        try:
            import openai
            
            logger.info(f"[OpenAI] Начинаем перевод цвета: '{color_chinese}'")
            
            prompt = f"""Переведи название цвета с китайского на русский.

ЦВЕТ: {color_chinese}

ИНСТРУКЦИЯ:
- Если это один цвет (例如: "черный" → "Черный", "白色" → "Белый")
- Если это комбинация цветов (例如: "黑白" → "Черно-белый", "黑白灰" → "Черно-бело-серый")
- Отвечай ОДНИМ словом или словосочетанием через дефис
- Без пояснений, только перевод цвета
- Первая буква заглавная

ОТВЕТ (только название цвета):"""
            
            logger.info(f"[OpenAI] 🔧 Создаем клиент OpenAI...")
            client = openai.OpenAI(api_key=self.api_key)
            logger.info(f"[OpenAI] ✅ Клиент создан: {type(client).__name__}")
            
            logger.info(f"[OpenAI] 📤 Отправляем запрос к модели gpt-5.1...")
            logger.debug(f"[OpenAI] 📝 Prompt длина: {len(prompt)} символов")
            logger.debug(f"[OpenAI] 🎨 Переводим цвет: '{color_chinese}'")
            
            response = client.chat.completions.create(
                model="gpt-5.1",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=50
            )
            
            logger.info(f"[OpenAI] 📥 Получен ответ от API")
            logger.info(f"[OpenAI] 🆔 Response ID: {response.id}")
            logger.info(f"[OpenAI] 🤖 Использована модель: {response.model}")
            logger.info(f"[OpenAI] 💰 Токены: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}, total={response.usage.total_tokens}")
            
            translated = response.choices[0].message.content.strip()
            
            # Очищаем от лишних символов
            translated = translated.strip('"\'.,;!? \n\r\t')
            
            logger.info(f"[OpenAI] ✅ Перевод цвета: '{color_chinese}' → '{translated}'")
            return translated
            
        except Exception as e:
            logger.error(f"[OpenAI] ❌ Ошибка перевода цвета: {type(e).__name__}: {e}")
            import traceback
            logger.debug(f"[OpenAI] Traceback:\n{traceback.format_exc()}")
            return color_chinese

    def translate_and_generate_seo(
        self,
        title: str,
        description: str,
        category: str,
        brand: str,
        attributes: Dict[str, str] = None,
        article_number: str = ''
    ) -> Dict[str, str]:
        """
        Переводит название, создает SEO описание через GigaChat.
        
        Args:
            title: Оригинальное название товара
            description: Оригинальное описание
            category: Категория товара
            brand: Бренд
            
        Returns:
            Словарь с переведенными и сгенерированными данными
        """
        # Если GigaChat не настроен, используем базовую обработку
        if not self.enabled:
            logger.warning("GigaChat не настроен, используется базовая обработка")
            return {
                "title_ru": title,
                "seo_title": f"{brand} {title[:50]}",
                "short_description": f"Качественный товар {brand} из категории {category}",
                "full_description": f"Описание товара {title}. {description[:200] if description else 'Подробное описание будет добавлено позже.'}",
                "meta_description": f"{brand} - {title[:80]}"
            }
        
        try:
            # Если атрибуты не переданы, используем пустой словарь
            if attributes is None:
                attributes = {}
            
            # Извлекаем данные из атрибутов
            color = attributes.get('Цвет', attributes.get('Основной цвет', ''))
            material = attributes.get('Материал', attributes.get('Материал верхней части', ''))
            
            # Определяем тип товара из категории
            cat_lower = category.lower()
            if '运动鞋' in title or '跑步鞋' in title or 'кроссовк' in cat_lower or 'туфля' in cat_lower:
                product_type = 'спортивная обувь'
            elif '板鞋' in title:
                product_type = 'кеды'
            else:
                product_type = 'обувь'
            
            # Извлекаем название модели из title
            product_name = title.split()[2:4] if len(title.split()) > 3 else title.split()[:2]
            product_name = ' '.join(str(x) for x in product_name if x)
            
            # Формируем промпт ТОЧНО как в main.py
            prompt = f"""⚠️ КРИТИЧЕСКИ ВАЖНО: 
1. СНАЧАЛА переведи ВСЕ китайские/японские слова на АНГЛИЙСКИЙ
2. ЗАТЕМ составь торговое название ТОЛЬКО из латиницы (A-Z) и цифр всегда с заглавной буквы
3. НЕ копируй иероглифы - ПЕРЕВОДИ их!

Ты — профессиональный SEO-копирайтер интернет-магазина, специализирующийся на бренде {brand}.
Создай структурированный SEO-контент для товара.

ИСХОДНЫЕ ДАННЫЕ (могут содержать китайский текст - ПЕРЕВЕДИ ЕГО):
- Бренд: {brand}
- Тип товара: {product_type}
- Исходное название: {title}  // ПЕРЕВЕДИ китайские слова на английский!
- Артикул/Style ID: {article_number}
- Цвет: {color}
- Материал: {material}
- Исходная категория: {category}
- Атрибуты: {attributes}

КЛЮЧЕВАЯ ФРАЗА: {brand} {product_name} {color} {article_number}
ВАЖНО: эта ключевая фраза должна присутствовать В ПЕРВОМ АБЗАЦЕ полного описания!

ИНСТРУКЦИЯ ПО ПЕРЕВОДУ:
- "定制球鞋" → "Custom Sneakers" (или просто убери)
- "阿卡丽" → транслитерация "Akali" или убери если непонятно
- "男款" → "Men's" или "Мужские"
- "黑白" → "Black White" или "Черно-белые"
- Если не можешь перевести - УБЕРИ это слово, НЕ копируй иероглифы!

ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА:
✓ Никогда не придумывай характеристики, которых нет в данных.
✓ Названия моделей, линейки (Air Jordan 1, Dunk Low, Yeezy 350 V2, Samba OG и т.д.) пиши латиницей всегда с заглавной буквы и не переводи.
✓ Не упоминай другие бренды.
✓ Пиши живым, разговорным языком: избегай канцелярита «высококачественный, многофункциональный, превосходный».
✓ Используй конкретику: вместо «удобные» – «мягкий воротник не натирает ахилл», вместо «лёгкие» – «вес одной кроссовки 320 г (42 размер)».
✓ Объём: краткое описание 280-320 зн., ПОЛНОЕ ОПИСАНИЕ МИНИМУМ 800 СИМВОЛОВ (не менее 300 слов!).

ПРАВИЛА ЧИТАЕМОСТИ (КРИТИЧЕСКИ ВАЖНО!):
⚠️ АКТИВНЫЙ ГОЛОС: Используй ТОЛЬКО активный голос! Максимум 10% пассивного голоса.
   ❌ Плохо: "Модель была выпущена в 2021 году", "Кроссовки были созданы для бега"
   ✅ Хорошо: "Бренд выпустил модель в 2021 году", "Дизайнеры создали кроссовки для бега"
   ✅ Хорошо: "Кроссовки держат асфальт", "Подошва амортизирует удары", "Материал дышит"

⚠️ КОРОТКИЕ ПРЕДЛОЖЕНИЯ: Максимум 25% предложений длиннее 15 слов!
   ❌ Плохо: Длинное предложение с множеством придаточных, запятых и деепричастных оборотов, которое трудно читать и понимать.
   ✅ Хорошо: Пиши короткими фразами. Одна мысль – одно предложение. Максимум 12-15 слов.
   ✅ Примеры коротких предложений: "Верх из кожи." "Подошва держит асфальт." "Вес 320 грамм."

В ПОЛНОМ ОПИСАНИИ обязательно раскрой (КОРОТКИМИ ПРЕДЛОЖЕНИЯМИ!):
→ ПЕРВЫЙ АБЗАЦ: начни с ключевой фразы "{brand} {product_name} {color} {article_number}". Кратко опиши товар;
→ визуальный образ (цвет, фактуры, контрасты);
→ материалы и их тактильные ощущения;
→ технологии (если указаны в attributes: Air, Boost, GORE-TEX и т.д.);
→ с чем носить. Куда надевать;
→ выгода для покупателя (лёгкость, устойчивость к погоде, доп. шнурки и т.д.).

SEO-заголовок ≤ 60 зн., ОБЯЗАТЕЛЬНО включает ТОЧНУЮ ключевую фразу в начале: "{brand} {product_name} {color}" (например: "Nike Dunk Low White Black – купить").
Мета-описание 150-160 зн., ОБЯЗАТЕЛЬНО включает ключевую фразу в начале, заканчивается призывом «Купить с доставкой» / «Закажи онлайн».
Ключевые слова: 3-4 слова (Nike; Dunk Low; кроссовки).

ФОРМАТ ОТВЕТА (ровно 6 строк, без пустых, без комментариев):
1. Название модели СТРОГО в формате: Бренд Модель Артикул (БЕЗ иероглифов, БЕЗ эмодзи, БЕЗ скобок)
2. Краткое описание
3. Полное описание
4. SEO Title (только латиница + кириллица, БЕЗ иероглифов)
5. Meta Description
6. Ключевые слова через точку с запятой (3-4 слова)

КРИТИЧЕСКИ ВАЖНО для строк 1 и 4:
- ❌ ЗАПРЕЩЕНО использовать китайские/японские иероглифы (定制球鞋、阿卡丽、时尚 и т.д.)
- ❌ ЗАПРЕЩЕНО использовать спецсимволы (【】、（）等)
- ✅ ТОЛЬКО латиница (A-Z, a-z) и кириллица (А-Я, а-я)
- ✅ ОБЯЗАТЕЛЬНО начинай с бренда: {brand} всегда с заглавной буквы
- ✅ Формат строки 1: "{brand} Модель Артикул" (например: Nike Court Borough BQ5448-115)
- ✅ Формат строки 4: "{brand} Модель - купить оригинал" (например: Nike Court Borough - купить оригинал)

Пример ПРАВИЛЬНОГО перевода с китайского:
Исходное название: "【定制球鞋】 Jordan Air Jordan 1 Mid 阿卡丽2 中帮 复古篮球鞋 男款 黑白"
                        ↓ ПЕРЕВОДИМ ↓
1. Jordan Air Jordan 1 Mid Akali 2 Black White DQ8426-154
   (убрали "定制球鞋", перевели "阿卡丽"→"Akali", "黑白"→"Black White", убрали лишнее)

Пример полного ответа (опирайся на стиль):
1. Nike Dunk Low White Black DD1391-103
2. Классический двухцветный Dunk Low: белая кожаная основа + чёрные замшевые оверлеи. Подошва средней толщины. Плотная строчка.
3. Nike Dunk Low White Black DD1391-103 – классика уличного стиля. Nike выпустил эту модель в 2021 году. Дизайн повторяет оригинальный блок 1985-го. Верх сделан из натуральной кожи. Белая гладкая кожа покрывает toe-box. Чёрная замша украшает swoosh и пятку. Перфорация в носке пропускает воздух. Внутри текстильная сетка. Она приятная и не растягивается. Промежуточная подошва из EVA весит на 30% меньше оригинала. Кроссовки подходят для города. Резиновая подметка держит асфальт и плитку. Даже в дождь. В комплекте белые шнурки flat. Есть вторая пара чёрных. Эти кроссовки сочетаются с джинсами-скинни. С карго тоже. С летними шортами отлично. Белый с чёрным всегда в тренде.
4. Nike Dunk Low White Black DD1391-103 – купить оригинал
5. Nike Dunk Low White Black DD1391-103 – оригинальные кроссовки в наличии. Бесплатная примерка, доставка по РФ в день заказа. Закажи онлайн!
6. Nike"""

            # Запрос к OpenAI
            logger.info(f"[OpenAI] ═══════════════════════════════════════")
            logger.info(f"[OpenAI] Начинаем генерацию SEO для товара: {title[:50]}...")
            logger.info(f"[OpenAI] Бренд: {brand}, Категория: {category}")
            logger.info(f"[OpenAI] Артикул: {article_number}")
            logger.info(f"[OpenAI] Атрибуты: {attributes}")
            
            import openai
            
            logger.info(f"[OpenAI] Создаем клиент OpenAI...")
            
            logger.info("="*80)
            logger.info(f"[OpenAI] 🔧 Создаем клиент OpenAI...")
            client = openai.OpenAI(api_key=self.api_key)
            logger.info(f"[OpenAI] ✅ Клиент создан: {type(client).__name__}")
            
            logger.info(f"[OpenAI] 📤 Отправляем запрос к модели gpt-4o...")
            logger.info(f"[OpenAI] 📊 Бренд: {brand}, Категория: {category}")
            logger.info(f"[OpenAI] 📝 Длина промпта: {len(prompt)} символов")
            logger.info(f"[OpenAI] ⚙️  Параметры: temperature=0.7, max_tokens=1500")
            
            # Вызов OpenAI с Circuit Breaker защитой
            try:
                response = openai_breaker.call(
                    lambda: client.chat.completions.create(
                        model="gpt-5.1",
                        messages=[
                            {"role": "system", "content": f"Ты - SEO-копирайтер, эксперт по товарам {brand}."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=1500
                    )
                )
            except CircuitBreakerError:
                logger.warning("[Circuit Breaker] OpenAI API временно недоступен, используем базовое описание")
                return {
                    "title_ru": title,
                    "seo_title": f"{brand} {title[:50]}",
                    "short_description": f"Качественный товар {brand} из категории {category}",
                    "full_description": f"Описание товара {title}. {description[:200] if description else 'Подробное описание будет добавлено позже.'}",
                    "meta_description": f"{brand} - {title[:80]}"
                }
            except Exception as e:
                logger.error(f"[OpenAI ERROR] Ошибка генерации: {e}")
                return {
                    "title_ru": title,
                    "seo_title": f"{brand} {title[:50]}",
                    "short_description": f"Качественный товар {brand} из категории {category}",
                    "full_description": f"Описание товара {title}. {description[:200] if description else 'Подробное описание будет добавлено позже.'}",
                    "meta_description": f"{brand} - {title[:80]}"
                }
            
            logger.info(f"[OpenAI] 📥 ✅ Получен ответ от API!")
            logger.info(f"[OpenAI] 🆔 Response ID: {response.id}")
            logger.info(f"[OpenAI] 🤖 Использована модель: {response.model}")
            logger.info(f"[OpenAI] 🏁 Finish reason: {response.choices[0].finish_reason}")
            logger.info(f"[OpenAI] 💰 Токены использовано: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}, total={response.usage.total_tokens}")
            
            result_text = response.choices[0].message.content.strip()
            logger.info(f"[OpenAI] 📄 Длина ответа: {len(result_text)} символов")
            logger.info(f"[OpenAI] 📋 Первые 300 символов ответа:\n{result_text[:300]}")
            logger.info(f"[OpenAI] ═══════════════════════════════════════")
            
            # Парсим построчный ответ - ожидаем 6 строк
            logger.info(f"[OpenAI] 🔍 Парсим ответ на строки...")
            lines = result_text.split('\n')
            
            # Убираем пустые строки и нумерацию
            parsed_lines = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Убираем "1. ", "2. ", "3. " и т.д.
                if line and len(line) > 3:
                    if line[0].isdigit() and line[1:3] in ['. ', ') ', ': ']:
                        line = line[3:].strip()
                    elif line[:2].isdigit() and line[2:4] in ['. ', ') ', ': ']:
                        line = line[4:].strip()
                
                if line:
                    parsed_lines.append(line)
            
            # Логируем что получили
            logger.info(f"[OpenAI] 📊 Распарсено {len(parsed_lines)} строк")
            for i, line in enumerate(parsed_lines[:6], 1):
                logger.info(f"[OpenAI]   Строка {i}: {line[:80]}...")
            
            logger.info(f"[OpenAI] 🧹 Очистка от китайских символов...")
            
            # Функция для АГРЕССИВНОЙ очистки текста от иероглифов
            import re
            
            def clean_chinese_chars(text: str) -> str:
                """ИЗВЛЕКАЕТ только латиницу, КИРИЛЛИЦУ, цифры и базовые символы из текста"""
                if not text:
                    return ""
                
                result = []
                for char in text:
                    code = ord(char)
                    # ASCII латиница и цифры
                    if (0x0041 <= code <= 0x005A or   # A-Z
                        0x0061 <= code <= 0x007A or   # a-z
                        0x0030 <= code <= 0x0039 or   # 0-9
                        code == 0x0020 or              # пробел
                        code == 0x002D or              # тире -
                        code == 0x0027 or              # апостроф '
                        code == 0x002E or              # точка .
                        code == 0x002C or              # запятая ,
                        code == 0x002F):               # слэш /
                        result.append(char)
                    # КИРИЛЛИЦА
                    elif (0x0410 <= code <= 0x042F or  # А-Я
                          0x0430 <= code <= 0x044F or  # а-я
                          code == 0x0401 or            # Ё
                          code == 0x0451):             # ё
                        result.append(char)
                    # Полноширинные латинские
                    elif 0xFF21 <= code <= 0xFF3A:  # Ａ-Ｚ
                        result.append(chr(code - 0xFEE0))
                    elif 0xFF41 <= code <= 0xFF5A:  # ａ-ｚ
                        result.append(chr(code - 0xFEE0))
                    elif 0xFF10 <= code <= 0xFF19:  # ０-９
                        result.append(chr(code - 0xFEE0))
                
                text = ''.join(result)
                text = re.sub(r'\s+', ' ', text).strip()
                text = text.lstrip('/').strip(' -.,/')
                
                if not text or len(text) < 3:
                    return ""
                
                return text
            
            # Очищаем строки
            title_clean = clean_chinese_chars(parsed_lines[0] if len(parsed_lines) > 0 else title)
            seo_title_clean = clean_chinese_chars(parsed_lines[3] if len(parsed_lines) > 3 else title)
            
            logger.info(f"После очистки: title='{title_clean}', seo_title='{seo_title_clean}'")
            
            # Fallback если пусто
            if not title_clean or len(title_clean.strip()) < 5 or title_clean.strip() in ['-', '-(', '-(-', '(', ')']:
                title_clean = f"{brand} {article_number}".strip() if article_number else brand
            
            if not seo_title_clean or len(seo_title_clean.strip()) < 5 or seo_title_clean.strip() in ['-', '-(', '-(-', '(', ')']:
                seo_title_clean = title_clean + " - купить оригинал"
            
            # Очищаем бренд
            brand_for_title = clean_chinese_chars(brand)
            if not brand_for_title or len(brand_for_title) < 2:
                brand_for_title = brand
            
            # Добавляем бренд если его нет
            brand_upper = brand_for_title.upper()
            
            if title_clean and brand_upper not in title_clean.upper():
                title_clean = f"{brand_for_title} {title_clean}"
            
            if seo_title_clean and brand_upper not in seo_title_clean.upper():
                seo_title_clean = f"{brand_for_title} {seo_title_clean}"
            
            # Получаем описание
            full_description = parsed_lines[2] if len(parsed_lines) > 2 else f"Описание {title}"
            
            # Очищаем keywords
            keywords_raw = parsed_lines[5] if len(parsed_lines) > 5 else f"{brand}, {category}"
            keywords_clean = clean_chinese_chars(keywords_raw)
            
            result = {
                "title_ru": title_clean,
                "short_description": parsed_lines[1] if len(parsed_lines) > 1 else f"Товар {brand}",
                "full_description": full_description,
                "seo_title": seo_title_clean,
                "meta_description": parsed_lines[4] if len(parsed_lines) > 4 else f"{brand} - купить онлайн",
                "keywords": keywords_clean
            }
            
            logger.info("="*80)
            logger.info(f"[OpenAI] ✅ ФИНАЛЬНЫЙ РЕЗУЛЬТАТ:")
            logger.info(f"[OpenAI]   📌 title_ru: {result.get('title_ru', '')[:80]}")
            logger.info(f"[OpenAI]   📌 seo_title: {result.get('seo_title', '')[:80]}")
            logger.info(f"[OpenAI]   📌 short_description (длина): {len(result.get('short_description', ''))} символов")
            logger.info(f"[OpenAI]   📌 full_description (длина): {len(result.get('full_description', ''))} символов")
            logger.info(f"[OpenAI]   📌 meta_description: {result.get('meta_description', '')[:80]}")
            logger.info(f"[OpenAI]   📌 keywords: {result.get('keywords', '')}")
            logger.info("="*80)
            return result
            
        except Exception as e:
            logger.error("="*80)
            logger.error(f"[OpenAI] ❌ КРИТИЧЕСКАЯ ОШИБКА!")
            logger.error(f"[OpenAI] 🔥 Тип ошибки: {type(e).__name__}")
            logger.error(f"[OpenAI] 💬 Сообщение: {e}")
            import traceback
            logger.error(f"[OpenAI] 📜 Полный traceback:")
            logger.error(traceback.format_exc())
            logger.warning(f"[OpenAI] ⚠️  Возвращаем fallback данные...")
            logger.error("="*80)
            # Возвращаем базовую обработку в случае ошибки
            return {
                "title_ru": title,
                "seo_title": f"{brand} {title[:50]}",
                "short_description": f"Качественный товар {brand} из категории {category}",
                "full_description": f"Описание товара {title}. {description[:200] if description else 'Подробное описание будет добавлено позже.'}",
                "meta_description": f"{brand} - {title[:80]}"
            }


class ProductProcessor:
    """Обработчик товаров: Poizon → OpenAI → WordPress"""
    
    def __init__(
        self,
        poizon: PoisonAPIService,
        openai_service: OpenAIService,
        woocommerce: WooCommerceService,
        settings: SyncSettings,
        session_id: str = None
    ):
        """Инициализация процессора"""
        self.poizon = poizon
        self.openai = openai_service
        self.woocommerce = woocommerce
        self.settings = settings
        self.session_id = session_id
        self.processing_status = {}
    
    def process_product(self, spu_id: int) -> ProcessingStatus:
        """
        Обрабатывает один товар через весь pipeline.
        
        Args:
            spu_id: ID товара в Poizon
            
        Returns:
            Статус обработки
        """
        product_key = str(spu_id)
        
        try:
            # Шаг 1: Получение данных из Poizon
            self._update_status(product_key, 'processing', 10, 'Загрузка из Poizon API...')
            
            product = self.poizon.get_product_full_info(spu_id)
            if not product:
                return self._update_status(product_key, 'error', 0, 'Не удалось загрузить товар')
            
            # КРИТИЧЕСКИ ВАЖНО: ВСЕГДА очищаем бренд из API, НЕ используем override_brand!
            # override_brand используется только для ПОИСКА товаров, но НЕ для названия!
            import re
            def extract_latin_only(text: str) -> str:
                """Извлекает только латиницу, цифры, тире, точку и слэш"""
                if not text:
                    return ""
                result = []
                for char in text:
                    code = ord(char)
                    if (0x0041 <= code <= 0x005A or   # A-Z
                        0x0061 <= code <= 0x007A or   # a-z
                        0x0030 <= code <= 0x0039 or   # 0-9
                        code == 0x0020 or              # пробел
                        code == 0x002D or              # тире -
                        code == 0x002F or              # слэш /
                        code == 0x002E):               # точка .
                        result.append(char)
                return ''.join(result).strip()
            
            original_brand = product.brand
            original_article = product.article_number
            
            # ВСЕГДА очищаем бренд из API (он может содержать иероглифы)
            product.brand = extract_latin_only(product.brand) or "Brand"
            logger.info(f"Бренд из API: '{original_brand}' → '{product.brand}'")
            
            product.article_number = extract_latin_only(product.article_number) or product.article_number
            logger.info(f"Артикул: '{original_article}' → '{product.article_number}'")
            
            # Шаг 2: Обработка через OpenAI
            self._update_status(product_key, 'openai', 40, 'Обработка через OpenAI...')
            
            seo_data = self.openai.translate_and_generate_seo(
                title=product.title,
                description=product.description,
                category=product.category,
                brand=product.brand,  # Теперь это очищенный бренд!
                attributes=product.attributes,
                article_number=product.article_number
            )
            
            # Обновляем данные товара ВСЕМИ полями из OpenAI
            product.title = seo_data['title_ru']  # Название модели
            product.description = seo_data['full_description']  # Полное описание
            product.short_description = seo_data.get('short_description', '')  # Краткое описание
            product.seo_title = seo_data.get('seo_title', seo_data['title_ru'])  # SEO Title
            product.meta_description = seo_data.get('meta_description', '')  # Meta Description
            product.keywords = seo_data.get('keywords', '')  # Ключевые слова
            
            logger.info(f"Обновленные поля товара:")
            logger.info(f"  product.title: {product.title[:80]}")
            logger.info(f"  product.seo_title: {product.seo_title[:80]}")
            
            # Шаг 2.5: Перевод цветов в вариациях через OpenAI
            if product.variations:
                logger.info(f"Переводим цвета в {len(product.variations)} вариациях...")
                unique_colors = set()
                color_translations = {}
                
                # Собираем уникальные цвета
                for variation in product.variations:
                    if 'color' in variation and variation['color']:
                        unique_colors.add(variation['color'])
                
                # Переводим каждый уникальный цвет
                for color in unique_colors:
                    translated = self.openai.translate_color(color)
                    color_translations[color] = translated
                
                # Применяем переводы к вариациям
                for variation in product.variations:
                    if 'color' in variation and variation['color']:
                        original_color = variation['color']
                        variation['color'] = color_translations.get(original_color, original_color)
                
                logger.info(f"Переведено цветов: {len(color_translations)}")
                for orig, trans in color_translations.items():
                    logger.info(f"  {orig} → {trans}")
            
            # Шаг 3: Проверка существования в WordPress
            self._update_status(product_key, 'wordpress', 70, 'Проверка существования в WordPress...')
            
            existing_id = self.woocommerce.product_exists(product.sku)
            
            if existing_id:
                # Товар уже существует - обновляем только цены и остатки
                logger.info(f"  Товар существует (ID {existing_id}), обновляем цены и остатки...")
                self._update_status(product_key, 'wordpress', 75, f'Обновление товара ID {existing_id}...')
                updated = self.woocommerce.update_product_variations(existing_id, product, self.settings)
                self._update_status(product_key, 'wordpress', 90, f'Обновлено {updated} вариаций товара ID {existing_id}')
                message = f'Обновлен товар ID {existing_id} ({updated} вариаций)'
            else:
                # Создаем новый товар
                logger.info(f"  Создаем новый товар...")
                self._update_status(product_key, 'wordpress', 75, 'Создание нового товара в WordPress...')
                
                self._update_status(product_key, 'wordpress', 80, f'Загрузка основной информации (название, цена, категория)...')
                new_id = self.woocommerce.create_product(product, self.settings)
                
                if new_id:
                    self._update_status(product_key, 'wordpress', 95, f'Товар успешно создан (ID {new_id})')
                    message = f'Создан товар ID {new_id}'
                else:
                    return self._update_status(product_key, 'error', 0, 'Ошибка создания товара в WordPress')
            
            # Шаг 4: Завершено
            return self._update_status(product_key, 'completed', 100, message)
            
        except Exception as e:
            logger.error(f"Ошибка обработки товара {spu_id}: {e}")
            return self._update_status(product_key, 'error', 0, f'Ошибка: {str(e)}')
    
    def _update_status(
        self,
        product_id: str,
        status: str,
        progress: int,
        message: str
    ) -> ProcessingStatus:
        """Обновляет статус обработки товара и отправляет событие в SSE"""
        status_obj = ProcessingStatus(
            product_id=product_id,
            status=status,
            progress=progress,
            message=message,
            timestamp=datetime.now().isoformat()
        )
        self.processing_status[product_id] = status_obj
        
        # Отправляем событие в SSE если есть session_id
        if self.session_id and self.session_id in progress_queues:
            progress_queues[self.session_id].put({
                'type': 'status_update',
                'product_id': product_id,
                'status': status,
                'progress': progress,
                'message': message
            })
        
        return status_obj
    
    def get_status(self, product_id: str) -> Optional[ProcessingStatus]:
        """Получает статус обработки товара"""
        return self.processing_status.get(product_id)


# Инициализация Circuit Breakers для каждого внешнего API
poizon_breaker = get_circuit_breaker(
    name='poizon_api',
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception
)

woocommerce_breaker = get_circuit_breaker(
    name='woocommerce_api',
    failure_threshold=5,
    recovery_timeout=60,
    expected_exception=Exception
)

openai_breaker = get_circuit_breaker(
    name='openai_api',
    failure_threshold=3,
    recovery_timeout=30,
    expected_exception=Exception
)


# Инициализация при запуске
def init_services():
    """Инициализация всех сервисов с защитой Circuit Breaker"""
    global poizon_client, woocommerce_client, openai_client
    
    # Предотвращаем дублирование логов в режиме DEBUG (Flask запускает процесс дважды)
    # Показываем логи инициализации только в главном процессе
    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    
    try:
        poizon_client = PoisonAPIService()
        woocommerce_client = WooCommerceService()
        openai_client = OpenAIService()
        
        if not is_reloader:
            logger.info("[OK] Все сервисы инициализированы с Circuit Breaker защитой")
    except Exception as e:
        logger.error(f"[ERROR] Ошибка инициализации сервисов: {e}")
        raise


# Вызываем инициализацию сервисов при импорте модуля (для gunicorn)
init_services()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница авторизации"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Получаем логин/пароль из .env
        admin_user = os.getenv('ADMIN_USERNAME', 'admin')
        admin_pass_plain = os.getenv('ADMIN_PASSWORD')  # опционально
        admin_pass_hash = os.getenv('ADMIN_PASSWORD_HASH')  # предпочтительно

        is_valid = False
        if username == admin_user:
            if admin_pass_hash:
                # Проверяем хэш пароля
                try:
                    is_valid = check_password_hash(admin_pass_hash, password)
                except Exception:
                    is_valid = False
            elif admin_pass_plain is not None:
                # Fallback: сравнение с простым паролем (не рекомендуется в продакшене)
                is_valid = (password == admin_pass_plain)

        if is_valid:
            session.permanent = True  # использовать PERMANENT_SESSION_LIFETIME
            session['logged_in'] = True
            session['username'] = username
            flash('Вы успешно авторизовались!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный логин или пароль', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Выход из системы"""
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/update')
@login_required
def update_page():
    """Страница обновления цен и остатков"""
    return render_template('update.html')


# ============================================================================
# ЗАГРУЗКА БРЕНДОВ (вспомогательные функции)
# ============================================================================

def fetch_all_brands_from_api(api_client) -> List[Dict]:
    """
    Загружает ВСЕ бренды из Poizon API через пагинацию.
    
    Используется файловым кэшем для обновления данных раз в месяц.
    
    Args:
        api_client: Экземпляр PoisonAPIService для запросов к API
    
    Returns:
        Список брендов с полями: id, name, logo, products_count
    """
    all_brands_raw = []
    page = 0
    max_pages = 50  # Максимум 5000 брендов (50 × 100)
    
    logger.info("[API] Загрузка всех брендов через пагинацию...")
    
    while page < max_pages:
        brands_page = api_client.get_brands(limit=100, page=page)
        
        if not brands_page or len(brands_page) == 0:
            logger.info(f"[API] Страница {page} пустая - все бренды загружены")
            break
        
        all_brands_raw.extend(brands_page)
        # Убрано DEBUG: информация о каждой странице
        
        # Если получили меньше 100, значит это последняя страница
        if len(brands_page) < 100:
            logger.info(f"[API] Последняя страница {page}: {len(brands_page)} брендов")
            break
        
        page += 1
    
    logger.info(f"[API] Загружено {len(all_brands_raw)} брендов с {page + 1} страниц")
    
    # Фильтруем и форматируем
    brands_list = []
    for brand in all_brands_raw:
        brand_name = brand.get('name', '')
        if brand_name and brand_name != '热门系列':  # Пропускаем "Горячие серии"
            brands_list.append({
                'id': brand.get('id'),
                'name': brand_name,
                'logo': brand.get('logo', ''),
                'products_count': 0
            })
    
    logger.info(f"[API] Отфильтровано брендов: {len(brands_list)}")
    return brands_list


@app.route('/api/brands', methods=['GET'])
@login_required
def get_brands():
    """
    Получает список всех доступных брендов.
    
    Использует файловый кэш (обновление раз в 30 дней).
    
    Returns:
        JSON список брендов
    """
    try:
        # Используем UnifiedCache (TTL 30 дней для брендов)
        brands_list = cache.get('all_brands', namespace='brands')
        
        if not brands_list:
            logger.info("[API /brands] Кеш пуст, загружаем бренды из API...")
            brands_list = fetch_all_brands_from_api(poizon_client)
            cache.set('all_brands', brands_list, ttl=30*24*60*60, namespace='brands')  # 30 дней
        
        logger.info(f"[API /brands] Возвращаем {len(brands_list)} брендов")
        return jsonify({
            'success': True,
            'brands': brands_list
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения брендов: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """
    Получает список категорий (главные категории первого уровня).
    
    Returns:
        JSON список категорий
    """
    try:
        # Получаем все категории
        all_categories = poizon_client.get_categories(lang="RU")
        
        # Фильтруем только главные категории (level = 1)
        main_categories = []
        for cat in all_categories:
            if cat.get('level') == 1:
                main_categories.append({
                    'id': cat.get('id'),
                    'name': cat.get('name', ''),
                    'rootId': cat.get('rootId')
                })
        
        logger.info(f"Найдено главных категорий: {len(main_categories)}")
        return jsonify({
            'success': True,
            'categories': main_categories
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# НОВЫЕ ЭНДПОИНТЫ ДЛЯ КАТЕГОРИЙ И ПОИСКА
# ============================================================================

@app.route('/api/categories/simplified', methods=['GET'])
def get_simplified_categories():
    """
    Получает упрощенный список основных категорий
    (6 категорий вместо тысяч для удобства пользователя)
    """
    try:
        simple_categories = [
            {'id': 29, 'name': 'Обувь', 'level': 1},
            {'id': 1000095, 'name': 'Женская одежда', 'level': 1},
            {'id': 1000096, 'name': 'Мужская одежда', 'level': 1},
            {'id': 92, 'name': 'Аксессуары', 'level': 1},
            {'id': 48, 'name': 'Сумки и рюкзаки', 'level': 1},
            {'id': 278, 'name': 'Косметика и парфюмерия', 'level': 1},
        ]
        
        logger.info(f"Возвращаем {len(simple_categories)} упрощенных категорий")
        return jsonify({
            'success': True,
            'categories': simple_categories,
            'total': len(simple_categories)
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/brands/by-category', methods=['GET'])
def get_brands_by_category():
    """
    Получает бренды для категории.
    ДЛЯ ОБУВИ (ID=29): Возвращает ВСЕ бренды из API (быстро!)
    ДЛЯ ДРУГИХ: Ищет товары по ключевым словам и извлекает бренды
    """
    try:
        category_id = request.args.get('category_id', type=int)
        
        if not category_id:
            return jsonify({
                'success': False,
                'error': 'Не указан category_id'
            }), 400
        
        # Проверяем кэш
        cache_key = f'brands_category_{category_id}'
        cached = cache.get(cache_key)
        if cached:
            logger.info(f"[CACHE] Бренды категории {category_id} из кэша ({len(cached)} шт)")
            cache.stats['requests_saved'] = cache.stats.get('requests_saved', 0) + 1
            return jsonify({
                'success': True,
                'brands': cached,
                'total': len(cached)
            })
        
        logger.info(f"[API] Получение брендов для категории {category_id}...")
        
        # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ОБУВИ (ID=29) - ПОКАЗЫВАЕМ ВСЕ БРЕНДЫ!
        if category_id == 29:
            logger.info(f"[ОБУВЬ] Загружаем ВСЕ бренды (UnifiedCache, 30 дней)")
            
            # Используем UnifiedCache (TTL 30 дней для брендов)
            all_brands_info = cache.get('all_brands', namespace='brands')
            
            if not all_brands_info:
                logger.info("[ОБУВЬ] Кеш пуст, загружаем бренды из API...")
                all_brands_info = fetch_all_brands_from_api(poizon_client)
                cache.set('all_brands', all_brands_info, ttl=30*24*60*60, namespace='brands')  # 30 дней
            
            # Сортируем по алфавиту
            brands_list = sorted(all_brands_info, key=lambda x: x['name'])
            
            logger.info(f"[ОБУВЬ] Возвращаем {len(brands_list)} брендов")
            
            # Кэшируем на 24 часа (для обуви долгий кэш)
            cache.set(cache_key, brands_list, ttl=86400)
            
            return jsonify({
                'success': True,
                'brands': brands_list,
                'total': len(brands_list)
            })
        
        # ДЛЯ ДРУГИХ КАТЕГОРИЙ - СТАРАЯ ЛОГИКА (поиск по ключевым словам)
        
        # Проверяем наличие категории
        if category_id not in CATEGORY_KEYWORDS:
            logger.warning(f"Категория {category_id} не поддерживается")
            return jsonify({
                'success': True,
                'brands': [],
                'total': 0
            })
        
        # Получаем поисковые термины
        search_terms = CATEGORY_KEYWORDS[category_id]['search_terms']
        logger.info(f"[API] Поиск товаров по терминам: {search_terms}")
        
        all_products = []
        
        # Ищем товары по каждому термину с Circuit Breaker защитой
        for term in search_terms:
            try:
                products = poizon_breaker.call(
                    lambda: poizon_client.search_products(keyword=term, limit=100)
                )
                all_products.extend(products)
                logger.info(f"  '{term}': найдено {len(products)} товаров")
            except CircuitBreakerError:
                logger.warning(f"[Circuit Breaker] Poizon API временно недоступен для термина '{term}'")
                # Продолжаем со следующим термином
                continue
            except Exception as e:
                logger.error(f"[ERROR] Ошибка поиска по термину '{term}': {e}")
                continue
        
        # Дедупликация
        unique_products = {}
        for product in all_products:
            spu_id = product.get('spuId', product.get('productId'))
            if spu_id and spu_id not in unique_products:
                unique_products[spu_id] = product
        
        logger.info(f"Уникальных товаров: {len(unique_products)}")
        
        # Фильтруем по категории
        filtered_products = filter_products_by_category(list(unique_products.values()), category_id)
        
        # Извлекаем уникальные бренды
        brands_dict = {}
        for product in filtered_products:
            brand_name = product.get('brandName', product.get('brand', ''))
            if brand_name and brand_name != '热门系列':
                if brand_name not in brands_dict:
                    brands_dict[brand_name] = {
                        'id': 0,
                        'name': brand_name,
                        'logo': '',
                        'products_count': 0
                    }
                brands_dict[brand_name]['products_count'] += 1
        
        logger.info(f"Найдено уникальных брендов: {len(brands_dict)}")
        
        # Получаем инфо о брендах (логотипы)
        all_brands_info = cache.get('all_brands')
        if not all_brands_info:
            all_brands = poizon_client.get_brands(limit=100)
            all_brands_info = []
            for b in all_brands:
                if b.get('name') and b.get('name') != '热门系列':
                    all_brands_info.append({
                        'id': b.get('id'),
                        'name': b.get('name'),
                        'logo': b.get('logo', ''),
                        'products_count': 0
                    })
            cache.set('all_brands', all_brands_info, ttl=43200)
        
        brand_info_map = {b['name']: b for b in all_brands_info}
        
        # Обогащаем данные
        brands_list = []
        for brand_name, brand_data in brands_dict.items():
            if brand_name in brand_info_map:
                full_brand = brand_info_map[brand_name]
                brand_data['id'] = full_brand.get('id', 0)
                brand_data['logo'] = full_brand.get('logo', '')
            brands_list.append(brand_data)
        
        # Сортируем по алфавиту
        brands_list.sort(key=lambda x: x['name'])
        
        # Кэшируем на 6 часов
        cache.set(cache_key, brands_list, ttl=21600)
        logger.info(f"[CACHE] Бренды категории {category_id} сохранены")
        
        return jsonify({
            'success': True,
            'brands': brands_list,
            'total': len(brands_list)
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения брендов категории: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/search/manual', methods=['GET'])
def manual_search():
    """
    Ручной поиск по SPU ID или артикулу
    """
    try:
        query = request.args.get('query', '').strip()
        
        if not query:
            return jsonify({
                'success': False,
                'error': 'Не указан запрос'
            }), 400
        
        logger.info(f"Ручной поиск: '{query}'")
        
        # Поиск по SPU ID (если число)
        if query.isdigit():
            spu_id = int(query)
            logger.info(f"Поиск по SPU ID: {spu_id}")
            
            try:
                product_detail = poizon_breaker.call(
                    lambda: poizon_client.get_product_detail_v3(spu_id)
                )
                
                if product_detail:
                    logger.info(f"Найден товар по SPU ID")
                    
                    return jsonify({
                        'success': True,
                        'products': [{
                            'spuId': spu_id,
                            'sku': str(spu_id),
                            'title': product_detail.get('title', ''),
                            'brand': product_detail.get('brandName', ''),
                            'description': product_detail.get('title', '')[:200],
                            'images': product_detail.get('images', []),
                            'articleNumber': product_detail.get('articleNumber', ''),
                            'price': 0
                        }],
                        'total': 1
                    })
            except CircuitBreakerError:
                logger.warning("[Circuit Breaker] Poizon API временно недоступен")
                return jsonify({
                    'success': False,
                    'error': 'Poizon API временно недоступен. Попробуйте позже.'
                }), 503
            except Exception as e:
                logger.error(f"[ERROR] Ошибка поиска по SPU ID: {e}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 500
        
        # Поиск по ключевому слову
        logger.info(f"Поиск по ключевому слову: '{query}'")
        # Убрано ограничение limit=50, теперь вернет максимум доступных результатов (обычно 100)
        try:
            products = poizon_breaker.call(
                lambda: poizon_client.search_products(keyword=query)
            )
        except CircuitBreakerError:
            logger.warning("[Circuit Breaker] Poizon API временно недоступен")
            return jsonify({
                'success': False,
                'error': 'Poizon API временно недоступен. Попробуйте позже.'
            }), 503
        except Exception as e:
            logger.error(f"[ERROR] Ошибка поиска: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
        
        formatted_products = []
        for product in products:
            spu_id = product.get('spuId', product.get('productId'))
            formatted_products.append({
                'spuId': spu_id,
                'sku': str(spu_id),
                'title': product.get('title', ''),
                'brand': product.get('brandName', product.get('brand', '')),
                'description': product.get('title', '')[:200],
                'images': product.get('images', [product.get('logoUrl')]) if product.get('images') else [product.get('logoUrl', '')],
                'articleNumber': product.get('articleNumber', ''),
                'price': product.get('price', 0)
            })
        
        logger.info(f"Найдено товаров: {len(formatted_products)}")
        
        return jsonify({
            'success': True,
            'products': formatted_products,
            'total': len(formatted_products)
        })
        
    except Exception as e:
        logger.error(f"Ошибка ручного поиска: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """Получить статистику кэша"""
    stats = cache.get_stats()
    return jsonify({
        'success': True,
        'stats': stats
    })


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache_endpoint():
    """Очистить весь кэш"""
    cache.clear()
    return jsonify({
        'success': True,
        'message': 'Кэш очищен'
    })


@app.route('/api/products', methods=['GET'])
def get_products():
    """
    Получает список товаров для выбранного бренда и категории.
    ОБНОВЛЕНО: Поддержка category_id и множественной пагинации!
    
    Query params:
        brand: Название бренда
        category: Название категории (старый формат, для совместимости)
        category_id: ID категории (новый формат)
        page: Номер страницы (начиная с 0)
        limit: Количество товаров (по умолчанию 20)
        
    Returns:
        JSON список товаров с пагинацией
    """
    try:
        brand = request.args.get('brand', '')
        category = request.args.get('category', '')
        category_id = request.args.get('category_id', type=int)
        
        # Безопасная обработка page параметра
        try:
            page = int(request.args.get('page', 0))
        except (ValueError, TypeError):
            page = 0
            
        limit = int(request.args.get('limit', 20))
        
        # Проверка на undefined/null значения
        if brand == 'undefined' or brand == 'null':
            brand = ''
        if category == 'undefined' or category == 'null':
            category = ''
            
        if not brand and not category and not category_id:
            return jsonify({
                'success': False,
                'error': 'Не указан бренд или категория'
            }), 400
        
        # Формируем ключевое слово для поиска
        if brand:
            keyword = brand
        else:
            keyword = category
        
        cache_key = f"products_{keyword}_{category_id}_{page}_{limit}"
        cached_response = cache.get(cache_key)
        if cached_response:
            logger.info(f"[CACHE] Товары для brand={brand} category_id={category_id} page={page} из кэша ({cached_response.get('total', 0)} шт)")
            cache.stats['requests_saved'] = cache.stats.get('requests_saved', 0) + 1
            return jsonify(cached_response)

        logger.info(f"Поиск товаров: brand={brand}, category_id={category_id}, page={page}")
        
        # УМНАЯ ПАГИНАЦИЯ: загружаем по 10 страниц API за раз (1000 товаров)
        # Это дает хороший баланс между скоростью и полнотой данных
        all_products = []
        pages_per_batch = 10  # Загружаем по 10 страниц API за раз
        start_page = page * pages_per_batch  # Начальная страница для этого батча
        is_last_batch = False  # Флаг: достигли конца данных API
        
        for p in range(start_page, start_page + pages_per_batch):
            products_page = poizon_client.search_products(keyword=keyword, limit=100, page=p)
            
            if not products_page or len(products_page) == 0:
                logger.info(f"  API страница {p}: пустая, останавливаем загрузку")
                is_last_batch = True
                break
            
            all_products.extend(products_page)
            logger.info(f"  API страница {p}: найдено {len(products_page)} товаров")
            
            # Если API вернул меньше 100 товаров - это последняя страница
            if len(products_page) < 100:
                logger.info(f"  Получена последняя API страница (товаров < 100)")
                is_last_batch = True
                break
        
        logger.info(f"ВСЕГО загружено из API: {len(all_products)} товаров (страницы {start_page}-{start_page + pages_per_batch - 1})")
        
        # Дедупликация
        unique_products = {}
        for product in all_products:
            spu_id = product.get('spuId', product.get('productId'))
            if spu_id and spu_id not in unique_products:
                unique_products[spu_id] = product
        
        products = list(unique_products.values())
        logger.info(f"Уникальных товаров: {len(products)}")
        
        # Фильтруем по категории (если указан category_id)
        if category_id and category_id != 0:
            products = filter_products_by_category(products, category_id)
            logger.info(f"После фильтрации по категории: {len(products)}")
        
        # Форматируем результаты
        formatted_products = []
        for product in products:
            spu_id = product.get('spuId', product.get('productId'))
            
            formatted_products.append({
                'spuId': spu_id,
                'sku': str(spu_id),
                'title': product.get('title', ''),
                'brand': brand,
                'category': category,
                'description': product.get('title', '')[:200],
                'images': product.get('images', [product.get('logoUrl')]) if product.get('images') else [product.get('logoUrl', '')],
                'articleNumber': product.get('articleNumber', ''),
                'price': product.get('price', 0)
            })
        
        # Определяем, есть ли еще товары
        # Если достигли конца API данных (последняя страница или пустой ответ), то has_more=False
        has_more = not is_last_batch
        
        response_payload = {
            'success': True,
            'products': formatted_products,
            'total': len(formatted_products),
            'page': page,
            'has_more': has_more  # Есть ли еще товары для загрузки
        }

        # Кэшируем результат чтобы не дергать Poizon повторно при повторной загрузке страницы
        cache.set(cache_key, response_payload, ttl=600)

        logger.info(f"Возвращаем товаров: {len(formatted_products)}, has_more={has_more}")
        return jsonify(response_payload)
        
    except Exception as e:
        logger.error(f"Ошибка получения товаров: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/progress/<session_id>')
def progress_stream(session_id):
    """
    SSE endpoint для получения прогресса обработки в реальном времени
    """
    def generate():
        # Создаем очередь для этой сессии если ее нет
        if session_id not in progress_queues:
            progress_queues[session_id] = queue.Queue()
        
        q = progress_queues[session_id]
        
        try:
            while True:
                # Ждем сообщение из очереди (timeout 30 сек)
                try:
                    message = q.get(timeout=30)
                    
                    # Если получили 'DONE' - завершаем
                    if message == 'DONE':
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                    
                    # Отправляем сообщение клиенту
                    yield f"data: {json.dumps(message)}\n\n"
                    
                except queue.Empty:
                    # Отправляем keepalive каждые 30 секунд
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                    
        finally:
            # Очищаем очередь после завершения
            if session_id in progress_queues:
                del progress_queues[session_id]
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/task-status/<task_id>', methods=['GET'])
@login_required
def get_task_status(task_id):
    """
    Получает статус Celery задачи.
    
    Returns:
        JSON со статусом задачи
    """
    if not CELERY_AVAILABLE:
        return jsonify({
            'success': False,
            'error': 'Celery не доступен'
        }), 503
    
    try:
        from celery.result import AsyncResult
        
        task = AsyncResult(task_id, app=batch_upload_products.app)
        
        response = {
            'success': True,
            'state': task.state,
            'ready': task.ready(),
        }
        
        if task.ready():
            # Задача завершена
            if task.successful():
                response['result'] = task.result
                response['status'] = 'completed'
            else:
                response['error'] = str(task.info)
                response['status'] = 'error'
        else:
            # Задача еще выполняется
            if task.state == 'PROGRESS':
                response['progress'] = task.info
            response['status'] = 'running'
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Ошибка проверки статуса задачи {task_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/upload', methods=['POST'])
@login_required
def upload_products():
    """
    Загружает выбранные товары в WordPress через GigaChat.
    Возвращает session_id для отслеживания прогресса через SSE.
    
    Request body:
        {
            "product_ids": [123, 456, 789],
            "settings": {
                "currency_rate": 13.5,
                "markup_rubles": 5000
            }
        }
        
    Returns:
        JSON с session_id для подключения к SSE
    """
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        settings_data = data.get('settings', {})
        
        if not product_ids:
            return jsonify({
                'success': False,
                'error': 'Не выбраны товары'
            }), 400
        
        # Генерируем уникальный session_id
        session_id = str(uuid.uuid4())
        
        # Создаем очередь для этой сессии
        progress_queues[session_id] = queue.Queue()
        
        # Создаем настройки
        settings = SyncSettings(
            currency_rate=settings_data.get('currency_rate', 13.5),
            markup_rubles=settings_data.get('markup_rubles', 5000)
        )
        
        logger.info(f"Загрузка товаров: ids={product_ids}")
        
        # Если Celery доступен, используем его для фоновой обработки
        if CELERY_AVAILABLE:
            logger.info("[Celery] Запускаем фоновую задачу обработки товаров")
            
            # Запускаем Celery задачу асинхронно
            task = batch_upload_products.delay(
                product_ids=product_ids,
                settings={
                    'currency_rate': settings_data.get('currency_rate', 13.5),
                    'markup_rubles': settings_data.get('markup_rubles', 5000)
                }
            )
            
            logger.info(f"[Celery] Задача создана: {task.id}")
            
            # Сразу возвращаем session_id клиенту
            return jsonify({
                'success': True,
                'session_id': session_id,
                'task_id': task.id,
                'total': len(product_ids),
                'mode': 'celery'
            })
        
        # Fallback: используем threading если Celery недоступен
        logger.info("[Threading] Запускаем обработку в отдельном потоке")
        
        # Запускаем обработку в отдельном потоке
        def process_products_thread():
            try:
                # Создаем процессор с передачей session_id
                processor = ProductProcessor(
                    poizon_client,
                    openai_client,
                    woocommerce_client,
                    settings,
                    session_id  # Передаем session_id в процессор
                )
                
                # Отправляем начальное сообщение
                progress_queues[session_id].put({
                    'type': 'start',
                    'total': len(product_ids),
                    'message': f'Начинаем обработку {len(product_ids)} товаров...'
                })
                
                # Обрабатываем товары
                results = []
                for idx, spu_id in enumerate(product_ids, 1):
                    progress_queues[session_id].put({
                        'type': 'product_start',
                        'current': idx,
                        'total': len(product_ids),
                        'spu_id': spu_id,
                        'message': f'[{idx}/{len(product_ids)}] Обработка товара {spu_id}...'
                    })
                    
                    # Обрабатываем товар (бренд будет взят из Poizon API и очищен)
                    status = processor.process_product(spu_id)
                    results.append(asdict(status))
                    
                    # Отправляем результат обработки товара
                    progress_queues[session_id].put({
                        'type': 'product_done',
                        'current': idx,
                        'total': len(product_ids),
                        'spu_id': spu_id,
                        'status': status.status,
                        'message': status.message
                    })
                
                # Отправляем финальное сообщение
                completed = sum(1 for r in results if r['status'] == 'completed')
                errors = sum(1 for r in results if r['status'] == 'error')
                
                progress_queues[session_id].put({
                    'type': 'complete',
                    'results': results,
                    'total': len(results),
                    'completed': completed,
                    'errors': errors,
                    'message': f'Готово! Успешно: {completed}, Ошибок: {errors}'
                })
                
                # Сигнал завершения
                progress_queues[session_id].put('DONE')
                
            except Exception as e:
                logger.error(f"Ошибка в потоке обработки: {e}")
                if session_id in progress_queues:
                    progress_queues[session_id].put({
                        'type': 'error',
                        'message': f'Критическая ошибка: {str(e)}'
                    })
                    progress_queues[session_id].put('DONE')
        
        # Запускаем поток
        thread = threading.Thread(target=process_products_thread, daemon=True)
        thread.start()
        
        # Сразу возвращаем session_id клиенту
        return jsonify({
            'success': True,
            'session_id': session_id,
            'total': len(product_ids),
            'mode': 'threading'
        })
        
    except Exception as e:
        logger.error(f"Ошибка загрузки товаров: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/status/<product_id>', methods=['GET'])
def get_product_status(product_id):
    """
    Получает статус обработки товара.
    
    Args:
        product_id: ID товара
        
    Returns:
        JSON со статусом
    """
    # TODO: Реализовать получение статуса из глобального processor
    return jsonify({
        'success': True,
        'status': 'pending'
    })


@app.route('/api/wordpress/categories', methods=['GET'])
def get_wordpress_categories():
    """
    Получает дерево категорий из WordPress для фильтра.
    
    Returns:
        JSON с деревом категорий
    """
    try:
        categories = []
        
        # Строим дерево из загруженных категорий
        for cat_id, cat_data in woocommerce_client.category_tree.items():
            path = woocommerce_client._build_category_path(cat_id)
            categories.append({
                'id': cat_id,
                'name': cat_data['name'],
                'parent': cat_data['parent'],
                'path': path,
                'slug': cat_data['slug']
            })
        
        # Сортируем по пути
        categories.sort(key=lambda x: x['path'])
        
        logger.info(f"Отправлено категорий: {len(categories)}")
        return jsonify({
            'success': True,
            'categories': categories
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/wordpress/products', methods=['GET'])
def get_wordpress_products():
    """
    Получает список товаров из WordPress для обновления (ЛЕГКОВЕСНЫЙ - без загрузки вариаций).
    Товары всегда отсортированы от старых к новым по дате обновления.
    
    Query params:
        page: номер страницы (default=1)
        per_page: товаров на странице (default=20)
        categories: Список ID категорий через запятую (необязательно)
        date_created_after: дата в формате YYYY-MM-DD (фильтр создания)
        product_id: ID конкретного товара для поиска (необязательно)
    
    Returns:
        JSON с товарами, пагинацией, без полной загрузки вариаций
        Товары отсортированы по дате обновления (от старых к новым)
    """
    try:
        # Параметры пагинации
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # Фильтры
        category_filter = request.args.get('categories', '')
        date_created_after = request.args.get('date_created_after', '')
        product_id = request.args.get('product_id', '')  # Новый параметр для поиска по ID
        
        # Если указан product_id - ищем только этот товар
        if product_id:
            try:
                product_id_int = int(product_id)
                logger.info(f"Поиск товара по ID: {product_id_int}")
                
                # Запрос одного товара
                url = f"{woocommerce_client.url}/wp-json/wc/v3/products/{product_id_int}"
                
                response = requests.get(
                    url,
                    auth=woocommerce_client.auth,
                    verify=False,
                    timeout=30
                )
                
                if response.status_code == 404:
                    return jsonify({
                        'success': False,
                        'error': f'Товар с ID {product_id_int} не найден'
                    }), 404
                
                response.raise_for_status()
                product = response.json()
                
                # Проверяем что это вариативный товар
                if product.get('type') != 'variable':
                    return jsonify({
                        'success': False,
                        'error': f'Товар ID {product_id_int} не является вариативным товаром'
                    }), 400
                
                logger.info(f"Найден товар: {product.get('name')}")
                
                # Формируем ответ для одного товара
                result_product = {
                    'id': product['id'],
                    'sku': product.get('sku', ''),
                    'name': product.get('name', ''),
                    'image': product.get('images', [{}])[0].get('src', '') if product.get('images') else '',
                    'date_created': product.get('date_created', ''),
                    'date_modified': product.get('date_modified', ''),
                }
                
                return jsonify({
                    'success': True,
                    'products': [result_product],
                    'pagination': {
                        'current_page': 1,
                        'per_page': 1,
                        'total_pages': 1,
                        'total_items': 1
                    }
                })
                
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'product_id должен быть числом'
                }), 400
        
        # Обычный поиск со списком товаров
        selected_category_ids = []
        if category_filter:
            selected_category_ids = [int(c.strip()) for c in category_filter.split(',') if c.strip().isdigit()]
        
        logger.info(f"Запрос товаров WordPress: page={page}, per_page={per_page}, categories={selected_category_ids}")
        
        # Параметры запроса к WordPress API
        # Всегда сортируем от старых к новым по дате обновления
        params = {
            'type': 'variable',  # Только вариативные товары
            'page': page,
            'per_page': per_page,
            'orderby': 'modified',
            'order': 'asc'  # От старых к новым по дате обновления
        }
        
        if selected_category_ids:
            params['category'] = ','.join(map(str, selected_category_ids))
        
        if date_created_after:
            params['after'] = date_created_after + 'T00:00:00'
        
        # Запрос к WordPress API
        url = f"{woocommerce_client.url}/wp-json/wc/v3/products"
        
        response = requests.get(
            url,
            auth=woocommerce_client.auth,
            params=params,
            verify=False,
            timeout=30
        )
        response.raise_for_status()
        
        products = response.json()
        total_pages = int(response.headers.get('X-WP-TotalPages', 1))
        total_filtered = int(response.headers.get('X-WP-Total', 0))
        
        logger.info(f"Получено товаров: {len(products)}, всего: {total_filtered}, страниц: {total_pages}")
        
        # Формируем легковесный ответ (БЕЗ загрузки вариаций!)
        result_products = []
        for product in products:
            result_products.append({
                'id': product['id'],
                'sku': product.get('sku', ''),
                'name': product.get('name', ''),
                'image': product.get('images', [{}])[0].get('src', '') if product.get('images') else '',
                'date_created': product.get('date_created', ''),
                'date_modified': product.get('date_modified', ''),
                # Информацию о вариациях получим при обновлении
            })
        
        return jsonify({
            'success': True,
            'products': result_products,
            'pagination': {
                'current_page': page,
                'per_page': per_page,
                'total_pages': total_pages,
                'total_items': total_filtered
            }
        })
        
    except Exception as e:
        logger.error(f"Ошибка получения товаров WordPress: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/update-prices', methods=['POST'])
@login_required
def update_prices_and_stock():
    """
    Обновляет цены и остатки выбранных товаров из Poizon API.
    Возвращает session_id для отслеживания прогресса через SSE.
    
    Request body:
        {
            "product_ids": [123, 456],
            "settings": {
                "currency_rate": 13.5,
                "markup_rubles": 5000
            }
        }
        
    Returns:
        JSON с session_id для подключения к SSE
    """
    try:
        data = request.get_json()
        product_ids = data.get('product_ids', [])
        settings_data = data.get('settings', {})
        
        if not product_ids:
            return jsonify({
                'success': False,
                'error': 'Не выбраны товары'
            }), 400
        
        # Генерируем уникальный session_id
        session_id = str(uuid.uuid4())
        
        # Создаем очередь для этой сессии
        progress_queues[session_id] = queue.Queue()
        
        # Создаем настройки
        settings = SyncSettings(
            currency_rate=settings_data.get('currency_rate', 13.5),
            markup_rubles=settings_data.get('markup_rubles', 5000)
        )
        
        logger.info(f"Обновление цен: товаров={len(product_ids)}, курс={settings.currency_rate}, наценка={settings.markup_rubles}₽")
        
        # Запускаем обновление в отдельном потоке
        def update_prices_thread():
            results = []
            updated_count = 0
            error_count = 0
            
            try:
                # Отправляем начальное сообщение
                progress_queues[session_id].put({
                    'type': 'start',
                    'total': len(product_ids),
                    'message': f'Начинаем обновление {len(product_ids)} товаров...'
                })
                
                for idx, wc_product_id in enumerate(product_ids, 1):
                    # Отправляем событие начала обработки товара
                    progress_queues[session_id].put({
                        'type': 'product_start',
                        'current': idx,
                        'total': len(product_ids),
                        'product_id': wc_product_id,
                        'message': f'[{idx}/{len(product_ids)}] Обработка товара ID {wc_product_id}...'
                    })
                    
                    try:
                        # Получаем товар из WordPress
                        progress_queues[session_id].put({
                            'type': 'status_update',
                            'message': f'  → Загрузка товара из WordPress...'
                        })
                        
                        url = f"{woocommerce_client.url}/wp-json/wc/v3/products/{wc_product_id}"
                        response = requests.get(url, auth=woocommerce_client.auth, verify=False, timeout=30)
                        response.raise_for_status()
                        wc_product = response.json()
                        
                        sku = wc_product.get('sku', '')
                        product_name = wc_product.get('name', '')
                        
                        logger.info(f"Товар WordPress ID {wc_product_id}: SKU='{sku}', Название='{product_name}'")
                        
                        # ВАЖНО: Ищем сохраненный spuId в meta_data (надежнее чем поиск!)
                        spu_id = None
                        meta_data = wc_product.get('meta_data', [])
                        for meta in meta_data:
                            if meta.get('key') == '_poizon_spu_id':
                                spu_id = int(meta.get('value'))
                                logger.info(f"  Найден сохраненный spuId: {spu_id}")
                                break
                        
                        # Если spuId не найден в meta_data - пробуем по SKU (fallback)
                        if not spu_id:
                            if not sku:
                                progress_queues[session_id].put({
                                    'type': 'product_done',
                                    'current': idx,
                                    'status': 'error',
                                    'message': f'SKU и spuId не найдены'
                                })
                                results.append({'product_id': wc_product_id, 'status': 'error', 'message': 'SKU не найден'})
                                error_count += 1
                                continue
                            
                            # Ищем товар в Poizon по SKU (fallback)
                            progress_queues[session_id].put({
                                'type': 'status_update',
                                'message': f'  → Поиск в Poizon по SKU {sku}...'
                            })
                            
                            search_results = poizon_client.search_products(sku, limit=1)
                            
                            logger.info(f"Fallback: поиск по SKU '{sku}' - найдено={len(search_results) if search_results else 0}")
                            
                            if not search_results or len(search_results) == 0:
                                progress_queues[session_id].put({
                                    'type': 'product_done',
                                    'current': idx,
                                    'status': 'error',
                                    'message': f'[{idx}/{len(product_ids)}] Товар не найден в Poizon'
                                })
                                results.append({'product_id': wc_product_id, 'status': 'error', 'message': 'Товар не найден в Poizon'})
                                error_count += 1
                                continue
                            
                            spu_id = search_results[0].get('spuId')
                            logger.warning(f"  Используем spuId из поиска: {spu_id} (может быть неточно!)")
                            
                            # Сохраняем spuId в meta_data для будущих обновлений
                            try:
                                update_url = f"{woocommerce_client.url}/wp-json/wc/v3/products/{wc_product_id}"
                                update_data = {
                                    'meta_data': [{'key': '_poizon_spu_id', 'value': str(spu_id)}]
                                }
                                requests.put(update_url, auth=woocommerce_client.auth, json=update_data, verify=False, timeout=30)
                                logger.info(f"  Сохранен spuId в meta_data для будущих обновлений")
                            except:
                                pass  # Не критично если не удалось
                        else:
                            logger.info(f"  Используем сохраненный spuId: {spu_id} (надежно!)")
                        
                        # ОПТИМИЗАЦИЯ: Обновляем только цены и остатки (без полной загрузки товара!)
                        progress_queues[session_id].put({
                            'type': 'status_update',
                            'message': f'  → Загрузка цен из Poizon (SPU: {spu_id})...'
                        })
                        
                        # Используем быстрый метод - только цены и остатки, без изображений/переводов/категорий
                        updated = woocommerce_client.update_product_prices_only(
                            wc_product_id,
                            spu_id,
                            settings.currency_rate,
                            settings.markup_rubles,
                            poizon_client  # Передаем клиент Poizon
                        )
                        
                        if updated < 0:  # Ошибка получения цен
                            progress_queues[session_id].put({
                                'type': 'product_done',
                                'current': idx,
                                'status': 'error',
                                'message': f'[{idx}/{len(product_ids)}] Не удалось получить цены'
                            })
                            results.append({'product_id': wc_product_id, 'status': 'error', 'message': 'Не удалось получить цены'})
                            error_count += 1
                            continue
                        
                        # Обновляем вариации
                        progress_queues[session_id].put({
                            'type': 'status_update',
                            'message': f'  → Обновление цен и остатков в WordPress...'
                        })
                        
                        if updated > 0:
                            progress_queues[session_id].put({
                                'type': 'status_update',
                                'message': f'  → Успешно обновлено {updated} вариаций'
                            })
                            
                            progress_queues[session_id].put({
                                'type': 'product_done',
                                'current': idx,
                                'status': 'completed',
                                'message': f'[{idx}/{len(product_ids)}] {product_name}: обновлено {updated} вариаций'
                            })
                            results.append({
                                'product_id': wc_product_id,
                                'product_name': product_name,
                                'status': 'completed',
                                'message': f'Обновлено вариаций: {updated}'
                            })
                            updated_count += 1
                        else:
                            progress_queues[session_id].put({
                                'type': 'product_done',
                                'current': idx,
                                'status': 'warning',
                                'message': f'[{idx}/{len(product_ids)}] {product_name}: SKU не совпадают'
                            })
                            results.append({
                                'product_id': wc_product_id,
                                'status': 'warning',
                                'message': 'Нет совпадающих вариаций'
                            })
                        
                        # Пауза для соблюдения rate limits
                        time.sleep(2)
                    
                    except Exception as e:
                        logger.error(f"Ошибка обновления товара {wc_product_id}: {e}")
                        progress_queues[session_id].put({
                            'type': 'product_done',
                            'current': idx,
                            'status': 'error',
                            'message': f'[{idx}/{len(product_ids)}] Ошибка: {str(e)}'
                        })
                        results.append({
                            'product_id': wc_product_id,
                            'status': 'error',
                            'message': str(e)
                        })
                        error_count += 1
                
                # Отправляем финальное сообщение
                progress_queues[session_id].put({
                    'type': 'complete',
                    'results': results,
                    'total': len(results),
                    'updated': updated_count,
                    'errors': error_count,
                    'message': f'Готово! Обновлено: {updated_count}, Ошибок: {error_count}'
                })
                
                # Сигнал завершения
                progress_queues[session_id].put('DONE')
                
            except Exception as e:
                logger.error(f"Критическая ошибка в потоке обновления: {e}")
                if session_id in progress_queues:
                    progress_queues[session_id].put({
                        'type': 'error',
                        'message': f'Критическая ошибка: {str(e)}'
                    })
                    progress_queues[session_id].put('DONE')
        
        # Запускаем поток
        thread = threading.Thread(target=update_prices_thread, daemon=True)
        thread.start()
        
        # Сразу возвращаем session_id клиенту
        return jsonify({
            'success': True,
            'session_id': session_id,
            'total': len(product_ids)
        })
        
    except Exception as e:
        logger.error(f"Ошибка обновления цен: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================================================================

if __name__ == '__main__':
    try:
        # Предотвращаем дублирование логов в режиме DEBUG (Flask запускает процесс дважды)
        # Логи инициализации показываем только в главном процессе
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            logger.info("="*70)
            logger.info("ЗАПУСК ВЕБ-ПРИЛОЖЕНИЯ POIZON → WORDPRESS")
            logger.info("="*70)
        
        # Инициализация сервисов
        init_services()
        
        # Запуск Flask
        port = int(os.getenv('WEB_APP_PORT', 5000))
        # По умолчанию без debug и без перезапуска (чтобы не было двойного запуска)
        debug = os.getenv('WEB_APP_DEBUG', 'False').lower() == 'true'
        
        # Логи запуска показываем только в главном процессе
        if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
            logger.info(f"Запуск веб-сервера на http://localhost:{port}")
            logger.info("Для остановки нажмите Ctrl+C")
            logger.info("="*70)
        
        # Для продакшена используем 0.0.0.0 для доступа извне
        app.run(
            host='0.0.0.0',  # Изменено для доступа извне
            port=port,
            debug=debug,
            use_reloader=False  # ВАЖНО: отключаем перезапуск, чтобы не было двух процессов
        )
        
    except Exception as e:
        logger.error(f"[ERROR] Критическая ошибка при запуске: {e}")
        raise

