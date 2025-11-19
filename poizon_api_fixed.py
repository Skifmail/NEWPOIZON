"""
Клиент для работы с Poizon API (poizon-api.com).

Этот модуль предоставляет клиент для взаимодействия с Poizon API - 
платформой для получения данных о товарах с китайского маркетплейса DEWU/Poizon.

Основные функции:
    - Получение списка брендов
    - Получение категорий товаров
    - Поиск товаров по ключевым словам
    - Получение детальной информации о товаре (изображения, вариации, цены)
    
API Documentation: https://poizon-api.com/docs

Требования:
    - POIZON_API_KEY: API ключ от poizon-api.com
    - POIZON_CLIENT_ID: Client ID от poizon-api.com
    
Переменные окружения должны быть указаны в файле .env

"""
import os
import logging
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv
import urllib3
import time
import openai
import re

# Отключаем SSL предупреждения для работы с API
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

logger = logging.getLogger(__name__)


class PoisonAPIClientFixed:
    """
    Клиент для работы с Poizon API (исправленная версия).
    
    Предоставляет методы для получения информации о товарах, брендах, 
    категориях и ценах с платформы DEWU/Poizon через poizon-api.com.
    
    Attributes:
        api_key (str): API ключ для аутентификации
        client_id (str): Client ID для аутентификации
        base_url (str): Базовый URL API
        headers (dict): Заголовки HTTP для всех запросов
        
    Raises:
        ValueError: Если не указаны POIZON_API_KEY или POIZON_CLIENT_ID в .env
        
    Example:
        >>> client = PoisonAPIClientFixed()
        >>> products = client.search_products("Nike", limit=10)
        >>> for product in products:
        ...     print(product['title'])
    """
    
    def __init__(self):
        """Инициализация клиента"""
        self.api_key = os.getenv('POIZON_API_KEY')
        self.client_id = os.getenv('POIZON_CLIENT_ID')
        self.base_url = "https://poizon-api.com/api/dewu"
        
        # OpenAI API для генерации описаний
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        if not self.api_key or not self.client_id:
            raise ValueError("POIZON_API_KEY и POIZON_CLIENT_ID должны быть в .env")
        
        self.headers = {
            'x-api-key': self.api_key,
            'client-id': self.client_id,
            'Content-Type': 'application/json'
        }
        
        # Настройки retry
        self.max_retries = 3
        self.base_delay = 2  # базовая задержка в секундах
        self.request_delay = 0.5  # задержка между ВСЕМИ запросами (защита от rate limit)
        
        logger.info("🔌 [Poizon API] Клиент инициализирован")
        logger.info(f"⏱️  [Poizon API] Retry настройки: {self.max_retries} попыток, базовая задержка {self.base_delay}с")
        logger.info(f"🛡️  [Poizon API] Защита от rate limit: {self.request_delay}с между запросами")
        
        if self.openai_api_key:
            logger.info(f"🤖 [OpenAI] API key загружен: {self.openai_api_key[:7]}...{self.openai_api_key[-4:]}")
        else:
            logger.warning("⚠️  [OpenAI] API key не найден - SEO-контент не будет генерироваться")
    
    def _make_request_with_retry(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Выполняет запрос с retry механизмом при ошибках 429/503"""
        # ВСЕГДА делаем задержку перед запросом (защита от rate limit)
        time.sleep(self.request_delay)
        
        for attempt in range(self.max_retries):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, **kwargs)
                else:
                    response = requests.post(url, **kwargs)
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in [429, 503]:
                    # Экспоненциальная задержка
                    delay = self.base_delay * (2 ** attempt)
                    logger.warning(f"⚠️  [Poizon API] {e.response.status_code} ошибка, попытка {attempt + 1}/{self.max_retries}, жду {delay}с...")
                    time.sleep(delay)
                    continue
                else:
                    raise
            except requests.exceptions.Timeout:
                delay = self.base_delay * (2 ** attempt)
                logger.warning(f"⚠️  [Poizon API] Timeout, попытка {attempt + 1}/{self.max_retries}, жду {delay}с...")
                time.sleep(delay)
                continue
                
        return None
    
    def get_brands(self, limit: int = 100, page: int = 0) -> List[Dict]:
        """
        Получает список брендов.
        
        Args:
            limit: Максимальное количество брендов
            page: Номер страницы
            
        Returns:
            Список брендов
        """
        try:
            url = f"{self.base_url}/getBrands"
            data = {"limit": limit, "page": page}
            
            # Убрано DEBUG: запрос брендов
            response = requests.post(url, json=data, headers=self.headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            brands = result.get('data', [])
            
            logger.info(f"[OK] Загружено брендов: {len(brands)}")
            return brands
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка загрузки брендов: {e}")
            return []
    
    def get_categories(self, lang: str = "RU") -> List[Dict]:
        """
        Получает список категорий.
        
        Args:
            lang: Язык (RU, EN, CN)
            
        Returns:
            Список категорий
        """
        try:
            url = f"{self.base_url}/getCategories"
            params = {"lang": lang}
            
            # Убрано DEBUG: запрос категорий
            response = requests.get(url, params=params, headers=self.headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            # API возвращает массив напрямую
            categories = result if isinstance(result, list) else result.get('categories', [])
            
            logger.info(f"[OK] Загружено категорий: {len(categories)}")
            return categories
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка загрузки категорий: {e}")
            return []
    
    def search_products(self, keyword: str, limit: int = 100, page: int = 0) -> List[Dict]:
        """
        Поиск товаров по ключевому слову.
        
        Args:
            keyword: Ключевое слово для поиска
            limit: Максимальное количество товаров (по умолчанию 100 - проверенный максимум API)
            page: Номер страницы
            
        Returns:
            Список товаров
        """
        try:
            url = f"{self.base_url}/searchProducts"
            params = {
                "keyword": keyword,
                "limit": min(limit, 100),  # API Poizon максимум 100
                "page": page
            }
            
            # Используем retry механизм
            response = self._make_request_with_retry('GET', url, params=params, headers=self.headers, timeout=60)
            
            if not response:
                logger.error(f"❌ [Poizon API] Не удалось выполнить запрос после {self.max_retries} попыток")
                return []
            
            result = response.json()
            # API возвращает ключ productList
            products = result.get('productList') or result.get('list') or []
            
            # Дополнительная проверка
            if products is None:
                products = []
            
            logger.info(f"[OK] Найдено товаров: {len(products)}")
            return products
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка поиска товаров: {e}")
            return []
    
    def get_product_detail_v3(self, spu_id: int) -> Optional[Dict]:
        """
        Получает детальную информацию о товаре.
        
        Args:
            spu_id: ID товара
            
        Returns:
            Данные товара
        """
        try:
            url = f"{self.base_url}/productDetailV3"
            params = {"spuId": spu_id}
            
            # Используем retry механизм
            response = self._make_request_with_retry('GET', url, params=params, headers=self.headers, timeout=60)
            
            if not response:
                logger.error(f"❌ [Poizon API] Не удалось получить товар {spu_id} после {self.max_retries} попыток")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка получения товара {spu_id}: {e}")
            return None
    
    def get_price_info(self, spu_id: int) -> Dict:
        """
        Получает информацию о ценах товара.
        
        Args:
            spu_id: ID товара
            
        Returns:
            Словарь {skuId: {price, stock}}
        """
        try:
            url = f"{self.base_url}/priceInfo"
            params = {"spuId": spu_id}
            
            response = requests.get(url, params=params, headers=self.headers, timeout=60)
            
            # Проверка статуса ответа
            if response.status_code == 403:
                logger.warning(f"⚠️ priceInfo SPU {spu_id}: 403 Forbidden - эндпоинт недоступен или требует дополнительную авторизацию")
                return {}
            
            response.raise_for_status()
            
            data = response.json()
            # logger.debug(f"  [DEBUG] priceInfo response for SPU {spu_id}: {data}")  # Убрано: слишком много данных
            
            # API возвращает структуру {"skus": {...}}, а НЕ {"data": {"skus": {...}}}
            skus_dict = data.get('skus', {})
            
            # Парсим цены
            result = {}
            for sku_id, sku_info in skus_dict.items():
                prices_array = sku_info.get('prices', [])
                quantity = sku_info.get('quantity', 0)
                
                if prices_array and len(prices_array) > 0:
                    first_price = prices_array[0]
                    price = first_price.get('price')
                    
                    if price:
                        result[str(sku_id)] = {
                            'price': float(price) / 100,  # Цена в API в фенях, делим на 100 для юаней
                            'stock': int(quantity)
                        }
            
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка получения цен {spu_id}: {e}")
            return {}
    
    def generate_seo_content(self, brand: str, product_type: str, product_name: str, sku: str, color: str = "", material: str = "") -> Optional[Dict]:
        """
        Генерирует SEO-контент через GPT-4o-mini.
        
        Args:
            brand: Название бренда
            product_type: Тип товара (Кроссовки, Куртка и т.д.)
            product_name: Название модели
            sku: Артикул
            color: Цвет (опционально)
            material: Материал (опционально)
            
        Returns:
            Словарь с полями: seo_title, short_description, description, meta_description, keywords, tags
            или None при ошибке
        """
        if not self.openai_api_key:
            logger.warning("⚠️  OpenAI API key не настроен - пропускаем генерацию SEO")
            return None
        
        try:
            # Формируем промпт точно как в успешном скрипте fix_product_descriptions.py
            prompt = f"""Создай SEO-контент для товара.

ДАННЫЕ:
- Бренд: {brand}
- Товар: {product_type} {brand} {product_name}
- Артикул: {sku}
- Цвет: {color}
- Материал: {material}

ФОРМАТ ОТВЕТА (6 строк):
1. {product_type} {brand} {product_name}
2. Краткое описание (280-320 символов)
3. Полное описание (минимум 800 символов), начни: "{brand} {product_name} {sku} –"
4. SEO Title (до 60 символов)
5. Meta Description (150-160 символов), заканчивается "Закажи онлайн!"
6. Теги: {brand}; модель"""
            
            logger.info(f"🤖 [GPT-4o-mini] Генерация SEO для: {brand} {product_name}")
            
            client = openai.OpenAI(api_key=self.openai_api_key)
            
            # Используем GPT-4o-mini
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты SEO-копирайтер"},
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.choices[0].message.content.strip()
            logger.info(f"✅ [GPT-4o-mini] Ответ получен, токенов: {response.usage.total_tokens}")
            
            # Парсим ответ
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
                logger.error(f"❌ Недостаточно строк в ответе: {len(parsed_lines)}")
                return None
            
            # Очистка от китайских символов (функция из fix_product_descriptions.py)
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
            
            # Извлекаем поля
            title_ru = clean_chinese(parsed_lines[0])
            short_desc = parsed_lines[1]
            full_desc = parsed_lines[2]
            seo_title = clean_chinese(parsed_lines[3])
            meta_desc = parsed_lines[4]
            keywords = parsed_lines[5]
            
            # Извлекаем теги - только бренд и модель
            tags_list = [k.strip() for k in keywords.split(';')]
            filtered_tags = []
            for tag in tags_list:
                tag_lower = tag.lower()
                if tag_lower not in ['кроссовки', 'обувь', 'одежда', 'товар', 'sneakers', 'shoes']:
                    filtered_tags.append(tag)
            
            # Добавляем бренд если его нет
            if brand not in filtered_tags:
                filtered_tags.insert(0, brand)
            
            # Фокусное ключевое слово для Yoast SEO
            focus_keyword = brand
            
            logger.info(f"✅ [GPT-4o-mini] SEO контент сгенерирован:")
            logger.info(f"   Название: {title_ru[:60]}...")
            logger.info(f"   Теги: {', '.join(filtered_tags)}")
            
            return {
                'seo_title': title_ru,  # Используем Line 1 (Тип Бренд Модель) как основное название
                'short_description': short_desc,
                'description': full_desc,
                'meta_description': meta_desc,
                'keywords': focus_keyword,
                'tags': filtered_tags
            }
            
        except Exception as e:
            logger.error(f"❌ [GPT-4o-mini] Ошибка генерации SEO: {e}")
            return None
    
    def get_product_full_info(self, spu_id: int):
        """
        Получает полную информацию о товаре для загрузки в WordPress.
        
        Этот метод объединяет данные из нескольких API endpoints:
        - productDetailV3: основная информация, изображения, атрибуты
        - priceInfo: актуальные цены и остатки по размерам
        
        Выполняет сложную обработку:
        1. Парсинг китайских атрибутов (размеры, цвета)
        2. Сопоставление изображений с цветами
        3. Формирование вариаций товара (размер + цвет + цена)
        4. Перевод атрибутов и категорий
        
        Args:
            spu_id: Уникальный идентификатор товара в системе Poizon
            
        Returns:
            SimpleNamespace объект с полными данными товара или None при ошибке
            
        Note:
            Результат совместим с классом PoisonProduct из poizon_to_wordpress_service
        """
        try:
            # === ШАГ 1: Получаем детали товара через productDetailV3 ===
            detail_data = self.get_product_detail_v3(spu_id)
            
            if not detail_data:
                return None
            
            # === ШАГ 2: Получаем актуальные цены и остатки через priceInfo ===
            prices = self.get_price_info(spu_id)
            # Убрано избыточное логирование DEBUG
            
            # Парсим данные
            # Убрано избыточное логирование ключей detail_data
            
            detail = detail_data.get('detail', {})
            skus_array = detail_data.get('skus', [])
            # Убрано: logger.debug(f"  [DEBUG] Получено SKU из productDetailV3: {len(skus_array)}")
            
            # Проверяем структуру image
            image_root = detail_data.get('image', {})
            # Убрано избыточное логирование image.keys()
            
            # Проверяем sortList - может там изображения по цветам?
            sort_list = image_root.get('sortList', [])
            # Убрано избыточное логирование sortList
            
            image_data = image_root.get('spuImage', {})
            # Извлекаем бренд из brandRootInfo
            brand_root_info = detail_data.get('brandRootInfo', {})
            brand_list = brand_root_info.get('brandItemList', [])
            brand_data = brand_list[0] if brand_list else {}
            sale_properties = detail_data.get('saleProperties', {}).get('list', [])
            
            # === ШАГ 3: Создаем маппинг размеров и цветов ===
            # Парсим китайские атрибуты из saleProperties
            # '尺码' (chǐmǎ) = размер, '颜色' (yánsè) = цвет
            size_value_map = {}  # {propertyValueId: размер}
            color_value_map = {}  # {propertyValueId: название цвета}
            
            for prop in sale_properties:
                prop_name = prop.get('name', '')
                size_value = prop.get('value', '')
                property_value_id = prop.get('propertyValueId')
                
                # Ищем размеры (尺码 = размер)
                if '尺码' in prop_name and size_value and property_value_id:
                    size_value_map[property_value_id] = size_value
                    
                # Ищем цвета (颜色 = цвет)
                if '颜色' in prop_name and size_value and property_value_id:
                    color_value_map[property_value_id] = size_value
            
            # Убрано избыточное DEBUG логирование size/color maps
            
            # ТЕПЕРЬ извлекаем изображения
            images = []
            images_list = image_data.get('images', [])
            
            # Убрано избыточное DEBUG логирование image_data структуры
            
            for img in images_list:
                img_url = img.get('url', '')
                if img_url:
                    images.append(img_url)
            
            # Извлекаем изображения по цветам из colorBlockImages
            color_images_map = {}  # propertyValueId → список изображений
            color_block_images = image_data.get('colorBlockImages', {})
            
            # Убрано избыточное DEBUG логирование colorBlockImages
            
            if color_block_images and isinstance(color_block_images, dict) and len(color_block_images) > 0:
                # Убрано DEBUG: logger.debug(f"  [DEBUG] ✅ Найдено colorBlockImages!")
                
                for prop_id_str, img_list in color_block_images.items():
                    # Убрано DEBUG: logger.debug(f"  [DEBUG] Обработка colorBlockImages[{prop_id_str}]...")
                    prop_id = int(prop_id_str)
                    color_urls = []
                    
                    if isinstance(img_list, list):
                        for img_item in img_list:
                            if isinstance(img_item, dict):
                                img_url = img_item.get('url', '')
                                if img_url:
                                    color_urls.append(img_url)
                            elif isinstance(img_item, str):
                                color_urls.append(img_item)
                    
                    if color_urls:
                        color_images_map[prop_id] = color_urls
                        # Убрано DEBUG: изображения для цвета
                    else:
                        pass  # Убрано WARNING: нет изображений
            else:
                pass  # Убрано DEBUG: colorBlockImages пустой
                
                # Пробуем разбить общие изображения на группы по цветам
                # Если есть 4 цвета и 20 изображений, то по 5 изображений на цвет
                if images and len(color_value_map) > 0:
                    images_per_color = len(images) // len(color_value_map)
                    # Убрано DEBUG: разбивка изображений по цветам
                    
                    color_ids = sorted(color_value_map.keys())
                    for idx, color_id in enumerate(color_ids):
                        start_idx = idx * images_per_color
                        end_idx = start_idx + images_per_color
                        color_specific_imgs = images[start_idx:end_idx]
                        
                        if color_specific_imgs:
                            color_images_map[color_id] = color_specific_imgs
                            # Убрано DEBUG: изображения для каждого цвета
                
                if not color_images_map:
                    pass  # Убрано DEBUG: используем общие изображения
            
            # Убрано избыточное DEBUG логирование структуры SKU
            
            # Формируем вариации
            variations = []
            # Убрано DEBUG: начинаем формировать вариации
            for idx_price, (sku_id_str, price_data) in enumerate(prices.items()):
                # Убрано DEBUG: информация о каждой вариации
                # Ищем соответствующий SKU в skus_array для получения размера
                size = None
                color = None
                sku_found_in_array = False
                
                # Находим SKU в массиве skus_array (если он не пустой)
                if skus_array:
                    for idx, sku_item in enumerate(skus_array):
                        if str(sku_item.get('skuId')) == sku_id_str:
                            sku_found_in_array = True
                            properties = sku_item.get('properties', [])
                            
                            # Убрано DEBUG: SKU properties
                            
                            # Извлекаем размер и цвет из properties
                            # properties может содержать [level 1 = цвет, level 2 = размер] или только размер
                            
                            for prop in properties:
                                property_value_id = prop.get('propertyValueId')
                                
                                # Проверяем в каком маппинге находится этот propertyValueId
                                if property_value_id in size_value_map:
                                    size = size_value_map[property_value_id]
                                    # Убрано DEBUG: размер найден
                                elif property_value_id in color_value_map:
                                    color = color_value_map[property_value_id]
                                    # Убрано DEBUG: цвет найден
                            
                            # Если размер не найден через properties, используем fallback
                            if not size:
                                # Убрано DEBUG: используем fallback
                                size_props = [p for p in sale_properties if '尺码' in p.get('name', '')]
                                if idx < len(size_props):
                                    size = size_props[idx].get('value', '')
                                    # Убрано DEBUG: размер из saleProperties
                            
                            break
                else:
                    # skus_array пустой - используем fallback на основе priceInfo
                    pass  # Убрано DEBUG: skus_array пустой
                
                # Если размер не найден, используем SKU ID как размер
                if not size or size == 'None':
                    logger.warning(f"  SKU {sku_id_str}: размер не найден, используем SKU ID")
                    size = sku_id_str
                
                # Переводим цвет с китайского на русский
                color_translations = {
                    # === Базовые цвета ===
                    '黑': 'Черный', '黑色': 'Черный',
                    '白': 'Белый', '白色': 'Белый',
                    '灰': 'Серый', '灰色': 'Серый',
                    '红': 'Красный', '红色': 'Красный',
                    '蓝': 'Синий', '蓝色': 'Синий',
                    '绿': 'Зеленый', '绿色': 'Зеленый',
                    '黄': 'Желтый', '黄色': 'Желтый',
                    '橙': 'Оранжевый', '橙色': 'Оранжевый',
                    '粉': 'Розовый', '粉色': 'Розовый',
                    '紫': 'Фиолетовый', '紫色': 'Фиолетовый',
                    '棕': 'Коричневый', '棕色': 'Коричневый',
                    '咖啡色': 'Коричневый',
                    '褐色': 'Коричневый',
                    '米色': 'Бежевый',
                    '银色': 'Серебристый',
                    '金色': 'Золотой',
                    '青色': 'Бирюзовый',
                    '青绿': 'Бирюзовый',
                    '青蓝': 'Бирюзово-синий',
                    '湖蓝': 'Голубой',
                    '天蓝': 'Небесно-голубой',
                    '藏蓝': 'Темно-синий',
                    '深蓝': 'Темно-синий',
                    '浅蓝': 'Голубой',
                    '海军蓝': 'Темно-синий',
                    '宝蓝': 'Королевский синий',
                    '蓝灰': 'Сине-серый',
                    '墨绿': 'Темно-зеленый',
                    '军绿': 'Хаки',
                    '卡其': 'Хаки', '卡其色': 'Хаки',
                    '橄榄绿': 'Оливковый',
                    '草绿': 'Травяной зеленый',
                    '苹果绿': 'Яблочно-зеленый',
                    '嫩绿': 'Салатовый',
                    '薄荷绿': 'Мятный',
                    '枣红': 'Бордовый',
                    '酒红': 'Бордовый',
                    '深红': 'Темно-красный',
                    '浅红': 'Светло-красный',
                    '玫红': 'Малиновый',
                    '粉红': 'Розовый',
                    '浅粉': 'Светло-розовый',
                    '桃红': 'Персиковый',
                    '橘红': 'Оранжево-красный',
                    '柠檬黄': 'Желтый',
                    '姜黄': 'Горчичный',
                    '金黄': 'Золотистый',
                    '奶白': 'Молочный белый',
                    '象牙白': 'Слоновая кость',
                    '米白': 'Молочно-белый',
                    '烟灰': 'Дымчато-серый',
                    '银灰': 'Серебристо-серый',
                    '石墨灰': 'Графитовый',
                    '苍岩灰': 'Серый',
                    '探险棕': 'Коричневый',
                    '桦木': 'Бежевый',
                    '桦木绿': 'Зеленый',
                    '耀夜紫': 'Фиолетовый',
                    '骑士黑': 'Черный',
                    
                    # === Комбинации цветов (двухцветные и более) ===
                    '黑白': 'Черно-белый', '黑白色': 'Черно-белый',
                    '红白': 'Красно-белый', '红白色': 'Красно-белый',
                    '蓝白': 'Сине-белый', '蓝白色': 'Сине-белый',
                    '黑红': 'Черно-красный', '黑红色': 'Черно-красный',
                    '黑蓝': 'Черно-синий', '黑蓝色': 'Черно-синий',
                    '黑灰': 'Черно-серый', '黑灰色': 'Черно-серый',
                    '黑金': 'Черно-золотой', '黑金色': 'Черно-золотой',
                    '黑银': 'Черно-серебристый', '黑银色': 'Черно-серебристый',
                    '红黑': 'Красно-черный', '红黑色': 'Красно-черный',
                    '红蓝': 'Красно-синий', '红蓝色': 'Красно-синий',
                    '红黄': 'Красно-желтый', '红黄色': 'Красно-желтый',
                    '红绿': 'Красно-зеленый', '红绿色': 'Красно-зеленый',
                    '蓝黑': 'Сине-черный', '蓝黑色': 'Сине-черный',
                    '蓝灰': 'Сине-серый', '蓝灰色': 'Сине-серый',
                    '蓝绿': 'Сине-зеленый', '蓝绿色': 'Сине-зеленый',
                    '蓝金': 'Сине-золотой', '蓝金色': 'Сине-золотой',
                    '蓝银': 'Сине-серебристый', '蓝银色': 'Сине-серебристый',
                    '白金': 'Белый с золотом', '白金色': 'Белый с золотом',
                    '白银': 'Белый с серебром', '白银色': 'Белый с серебром',
                    '灰白': 'Серо-белый', '灰白色': 'Серо-белый',
                    '灰蓝': 'Серо-синий', '灰蓝色': 'Серо-синий',
                    '灰黑': 'Серо-черный', '灰黑色': 'Серо-черный',
                    '棕白': 'Коричнево-белый', '棕白色': 'Коричнево-белый',
                    '棕黑': 'Коричнево-черный', '棕黑色': 'Коричнево-черный',
                    '粉白': 'Розово-белый', '粉白色': 'Розово-белый',
                    '粉蓝': 'Розово-голубой', '粉蓝色': 'Розово-голубой',
                    '粉紫': 'Розово-фиолетовый', '粉紫色': 'Розово-фиолетовый',
                    '紫白': 'Фиолетово-белый', '紫白色': 'Фиолетово-белый',
                    '紫黑': 'Фиолетово-черный', '紫黑色': 'Фиолетово-черный',
                    '紫蓝': 'Фиолетово-синий', '紫蓝色': 'Фиолетово-синий',
                    '金黑': 'Золотисто-черный', '金黑色': 'Золотисто-черный',
                    '金白': 'Золотисто-белый', '金白色': 'Золотисто-белый',
                    '金银': 'Золото-серебристый', '金银色': 'Золото-серебристый',
                    '绿白': 'Зелено-белый', '绿白色': 'Зелено-белый',
                    '绿黑': 'Зелено-черный', '绿黑色': 'Зелено-черный',
                    '绿蓝': 'Зелено-синий', '绿蓝色': 'Зелено-синий',
                    '黄黑': 'Желто-черный', '黄黑色': 'Желто-черный',
                    '黄白': 'Желто-белый', '黄白色': 'Желто-белый',
                    '黄蓝': 'Желто-синий', '黄蓝色': 'Желто-синий',
                    '黄绿': 'Желто-зеленый', '黄绿色': 'Желто-зеленый',
                    '银黑': 'Серебристо-черный', '银黑色': 'Серебристо-черный',
                    '银白': 'Серебристо-белый', '银白色': 'Серебристо-белый',
                    '银蓝': 'Серебристо-синий', '银蓝色': 'Серебристо-синий',
                    '银灰': 'Серебристо-серый', '银灰色': 'Серебристо-серый',
                    '彩色': 'Разноцветный',
                    '多色': 'Многоцветный',
                    '撞色': 'Контрастный цвет',
                    '渐变色': 'Градиентный цвет'
                }
                
                color_ru = color_translations.get(color, color) if color else None
                # Убрано DEBUG: перевод цвета
                
                # Находим propertyValueId цвета для извлечения изображений
                color_prop_id = None
                if color:
                    for prop in properties:
                        prop_id = prop.get('propertyValueId')
                        if prop_id in color_value_map:
                            color_prop_id = prop_id
                            break
                
                # Получаем изображения для этого цвета
                color_specific_images = []
                if color_prop_id and color_prop_id in color_images_map:
                    color_specific_images = color_images_map[color_prop_id]
                    # Убрано DEBUG: изображения для цвета
                
                # Убрано DEBUG: итоговая информация о вариации
                
                # Проверяем цену (должна быть адекватной)
                price_yuan = price_data['price']
                # Цены в Poizon API обычно указаны в фенях (1/100 юаня)
                if price_yuan > 10000:  # Если больше 10000, скорее всего это фени
                    price_yuan = price_yuan / 100
                
                variation_data = {
                    'sku_id': sku_id_str,
                    'size': str(size),  # Размер БЕЗ цвета
                    'price': price_yuan,
                    'stock': price_data['stock']
                }
                
                # Добавляем цвет отдельно (если есть)
                if color_ru:
                    variation_data['color'] = color_ru  # Переведенный цвет
                
                # Добавляем изображения для этого цвета (если есть)
                if color_specific_images:
                    variation_data['images'] = color_specific_images
                
                variations.append(variation_data)
            
            # Убрано DEBUG: создано вариаций
            if variations:
                sizes = [v['size'] for v in variations[:5]]
                logger.info(f"  Примеры размеров: {sizes}")
            else:
                logger.warning(f"  ВАРИАЦИЙ НЕТ! prices={len(prices)}, skus_array={len(skus_array)}, sale_properties={len(sale_properties)}")
            
            # Формируем атрибуты (переводим китайские названия)
            from category_mapper import translate_attribute_name
            
            attributes = {}
            for prop in sale_properties:
                attr_name = prop.get('name', '')
                attr_value = prop.get('value', '')
                if attr_name and attr_value and '尺码' not in attr_name:  # Пропускаем размер (он уже в вариациях)
                    # Переводим название атрибута
                    translated_name = translate_attribute_name(attr_name)
                    attributes[translated_name] = attr_value
            
            # Добавляем атрибуты из baseProperties если есть
            base_properties = detail_data.get('baseProperties', {}).get('list', [])
            for prop in base_properties:
                attr_key = prop.get('key', '')
                attr_value = prop.get('value', '')
                if attr_key and attr_value:
                    translated_key = translate_attribute_name(attr_key)
                    if translated_key not in attributes:
                        attributes[translated_key] = attr_value
            
            # Извлекаем бренд (пробуем разные источники)
            brand_from_api = brand_data.get('brandName') or brand_data.get('showName')
            brand_name = brand_from_api or detail.get('brandName')
            
            # Если бренд не найден - берем из названия, НО фильтруем служебные префиксы
            if not brand_name:
                title = detail.get('title', '')
                # Убираем китайские служебные префиксы типа 【定制球鞋】, 【联名款】 и т.д.
                import re
                # Удаляем текст в 【】 скобках
                cleaned_title = re.sub(r'【[^】]+】', '', title).strip()
                # Берем первое слово после очистки
                brand_name = cleaned_title.split()[0] if cleaned_title else 'Unknown'
                logger.info(f"⚠️ Бренд не найден в API, извлечен из названия: '{brand_name}'")
            else:
                logger.info(f"✅ Бренд из brandRootInfo: '{brand_name}'")
            
            # Маппим категорию в WordPress категорию
            # Перезагружаем модуль category_mapper для актуальных изменений
            import importlib
            import category_mapper
            importlib.reload(category_mapper)
            from category_mapper import map_category_to_wordpress
            
            poizon_category = detail.get('categoryName', '')
            wordpress_category = map_category_to_wordpress(poizon_category, detail.get('title', ''))
            
            logger.info(f"Категория Poizon: '{poizon_category}'")
            logger.info(f"Категория WordPress: '{wordpress_category}'")
            
            # === ШАГ 5: Генерация SEO-контента через GPT-4o-mini ===
            # Определяем тип товара из WordPress категории
            product_type = "Товар"
            category_lower = wordpress_category.lower()
            
            if 'кроссовки' in category_lower or 'sneakers' in category_lower:
                product_type = "Кроссовки"
            elif 'куртка' in category_lower or 'jacket' in category_lower:
                product_type = "Куртка"
            elif 'футболка' in category_lower or 't-shirt' in category_lower:
                product_type = "Футболка"
            elif 'толстовка' in category_lower or 'hoodie' in category_lower:
                product_type = "Толстовка"
            elif 'брюки' in category_lower or 'pants' in category_lower:
                product_type = "Брюки"
            elif 'шорты' in category_lower or 'shorts' in category_lower:
                product_type = "Шорты"
            
            # Извлекаем цвет и материал из атрибутов
            color = attributes.get('Цвет', attributes.get('Color', ''))
            material = attributes.get('Материал', attributes.get('Material', ''))
            
            # Извлекаем название модели из title (убираем бренд и китайские символы)
            product_title = detail.get('title', '')
            product_name = product_title.replace(brand_name, '').strip()
            product_name = re.sub(r'【[^】]+】', '', product_name).strip()  # Убираем китайские скобки
            
            # Генерируем SEO-контент
            seo_content = self.generate_seo_content(
                brand=brand_name,
                product_type=product_type,
                product_name=product_name,
                sku=detail.get('articleNumber', ''),
                color=color,
                material=material
            )
            
            # Используем сгенерированный контент или fallback на базовый
            if seo_content:
                seo_title = seo_content['seo_title']
                short_description = seo_content['short_description']
                full_description = seo_content['description']
                meta_description = seo_content['meta_description']
                keywords = seo_content['keywords']
                tags = seo_content['tags']
            else:
                # Fallback: базовый контент если GPT-4o-mini не сработал
                seo_title = f"{product_type} {brand_name} {product_name}"
                short_description = f"{product_type} {brand_name} {product_name}. Артикул: {detail.get('articleNumber', '')}"
                full_description = detail.get('desc', '')
                meta_description = f"{product_type} {brand_name} {product_name}. Закажи онлайн!"
                keywords = brand_name
                tags = [brand_name]
                logger.warning(f"⚠️  Используется fallback контент (GPT-4o-mini недоступен)")
            
            # Создаем объект товара (простой dict вместо dataclass)
            from types import SimpleNamespace
            
            product = SimpleNamespace(
                spu_id=detail.get('spuId'),
                dewu_id=detail.get('spuId'),
                poizon_id=str(detail.get('spuId')),
                sku=str(detail.get('spuId')),
                title=detail.get('title', ''),
                article_number=detail.get('articleNumber', ''),
                brand=brand_name,
                category=poizon_category,
                wordpress_category=wordpress_category,
                images=images,
                variations=variations,
                attributes=attributes,
                description=full_description,
                # Новые SEO-поля
                seo_title=seo_title,
                short_description=short_description,
                meta_description=meta_description,
                keywords=keywords,
                tags=tags
            )
            
            logger.info(f"[OK] Загружена полная информация о товаре {spu_id}")
            return product
            
        except Exception as e:
            logger.error(f"[ERROR] Ошибка загрузки полной информации {spu_id}: {e}")
            return None


# Тестирование
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    client = PoisonAPIClientFixed()
    
    print("\n=== Тест 1: Получение брендов ===")
    brands = client.get_brands(limit=10)
    if brands:
        print(f"Найдено брендов: {len(brands)}")
        for i, brand in enumerate(brands[:5], 1):
            print(f"  {i}. {brand.get('name', 'N/A')} (ID: {brand.get('id')})")
    
    print("\n=== Тест 2: Получение категорий ===")
    categories = client.get_categories()
    if categories:
        print(f"Найдено категорий: {len(categories)}")
        # Фильтруем только главные категории (level=1)
        main_cats = [c for c in categories if c.get('level') == 1][:10]
        for i, cat in enumerate(main_cats, 1):
            print(f"  {i}. {cat.get('name', 'N/A')} (ID: {cat.get('id')}, Level: {cat.get('level')})")
    
    print("\n=== Тест 3: Поиск товаров ===")
    products = client.search_products("Nike", limit=5)
    if products:
        print(f"Найдено товаров: {len(products)}")
        for i, product in enumerate(products, 1):
            print(f"  {i}. {product.get('title', 'N/A')} (spuId: {product.get('spuId', 'N/A')})")

