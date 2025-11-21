print("Script started...")
import os
import logging
import requests
import time
import io
from datetime import datetime
from dotenv import load_dotenv
from poizon_to_wordpress_service import WooCommerceService
from openai_service import OpenAIService
from image_processor import resize_image_to_square
from PIL import Image

import concurrent.futures
import threading

# Force reconfiguration of logging (reset handlers from imported modules)
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('update_old_products.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Lock for thread-safe printing and stats updates
print_lock = threading.Lock()

class ProductUpdater:
    def __init__(self):
        self.wc = WooCommerceService()
        self.openai = OpenAIService()
        # Дата отсечки: 12.11.2025 включительно
        self.cutoff_date = datetime.strptime("2025-11-12 23:59:59", "%Y-%m-%d %H:%M:%S")
        self.stats = {
            'processed': 0,
            'tokens': 0,
            'start_time': time.time()
        }

    def get_product(self, product_id):
        """Получает данные товара по ID"""
        url = f"{self.wc.url}/wp-json/wc/v3/products/{product_id}"
        response = requests.get(url, auth=self.wc.auth, verify=False, timeout=60)
        if response.status_code == 200:
            return response.json()
        logger.error(f"Ошибка получения товара {product_id}: {response.status_code}")
        return None

    def delete_image(self, image_id):
        """Удаляет изображение из медиатеки"""
        if not image_id:
            return
        try:
            url = f"{self.wc.url}/wp-json/wp/v2/media/{image_id}"
            response = requests.delete(url, auth=self.wc.wp_auth or self.wc.auth, params={'force': True}, verify=False)
            if response.status_code in [200, 202, 204]:
                logger.info(f"  Удалено старое изображение ID {image_id}")
            else:
                logger.warning(f"  Не удалось удалить изображение ID {image_id}: {response.status_code}")
        except Exception as e:
            logger.error(f"  Ошибка удаления изображения {image_id}: {e}")

    def process_images(self, product):
        """
        Скачивает текущие изображения, ресайзит их и загружает обратно.
        Возвращает список новых ID изображений.
        """
        current_images = product.get('images', [])
        if not current_images:
            return []

        new_image_ids = []
        old_image_ids = []

        logger.info(f"  Обработка {len(current_images)} изображений...")

        for idx, img_data in enumerate(current_images):
            img_url = img_data['src']
            img_id = img_data['id']
            old_image_ids.append(img_id)
            
            # Формируем имя файла
            # Стараемся сохранить осмысленное имя или генерируем новое
            filename = img_data.get('name', f"image_{product['id']}_{idx}")
            if not filename.endswith('.jpg'):
                filename += '.jpg'
            
            # Очистка имени файла
            import re
            filename = re.sub(r'[^\w\s.-]', '', filename)
            filename = filename.replace(' ', '_')

            try:
                # Загружаем и ресайзим (используем метод из WooCommerceService, но нам нужно передать URL)
                # Метод upload_resized_image сам скачивает и ресайзит
                
                # ВАЖНО: Если URL локальный (wp-content), он может быть недоступен извне, если сервер за NAT/Firewall?
                # Но скрипт запускается локально, а сервер удаленный. URL должен быть публичным.
                
                logger.info(f"    Обработка изображения {idx+1}: {img_url}")
                new_media_id = self.wc.upload_resized_image(img_url, filename, size=600)
                
                if new_media_id:
                    new_image_ids.append({'id': new_media_id})
                else:
                    logger.warning(f"    Не удалось обработать изображение {img_url}, оставляем старое")
                    new_image_ids.append({'id': img_id}) # Оставляем старое если не вышло
                    old_image_ids.remove(img_id) # Не удаляем старое

            except Exception as e:
                logger.error(f"    Ошибка обработки изображения {img_url}: {e}")
                new_image_ids.append({'id': img_id})
                old_image_ids.remove(img_id)

        return new_image_ids, old_image_ids

    def analyze_product_data(self, title, attributes, current_category):
        """
        Анализирует данные товара: определяет правильный бренд, категорию и очищает название.
        """
        title_lower = title.lower()
        
        # 1. Исправление бренда
        brand = ""
        for attr in attributes:
            if attr['name'].lower() in ['бренд', 'brand']:
                brand = attr['options'][0]
                break
        
        # Очистка бренда от мусора
        if brand:
            brand = brand.strip().lstrip('/').strip()

        # Исправление для The North Face
        if brand == "THE" and "north face" in title_lower:
            brand = "The North Face"
            
        # Если бренда нет или он "Brand", пытаемся найти известный бренд в названии
        if not brand or brand.lower() == 'brand':
            known_brands = {
                'nike': 'Nike',
                'adidas': 'Adidas',
                'jordan': 'Jordan',
                'air jordan': 'Jordan',
                'new balance': 'New Balance',
                'asics': 'Asics',
                'puma': 'Puma',
                'reebok': 'Reebok',
                'vans': 'Vans',
                'converse': 'Converse',
                'ugg': 'UGG',
                'crocs': 'Crocs',
                'the north face': 'The North Face',
                'tnf': 'The North Face',
                'timberland': 'Timberland',
                'dr. martens': 'Dr. Martens',
                'salomon': 'Salomon',
                'balenciaga': 'Balenciaga',
                'gucci': 'Gucci',
                'louis vuitton': 'Louis Vuitton',
                'burberry': 'Burberry',
                'dior': 'Dior',
                'versace': 'Versace',
                'prada': 'Prada',
                'stone island': 'Stone Island',
                'cp company': 'C.P. Company',
                'supreme': 'Supreme',
                'off-white': 'Off-White',
                'fear of god': 'Fear of God',
                'essentials': 'Essentials',
                'yeezy': 'Yeezy'
            }
            
            # Маппинг моделей к брендам (если бренда нет в названии)
            model_to_brand = {
                'court borough': 'Nike',
                'air force': 'Nike',
                'air max': 'Nike',
                'dunk': 'Nike',
                'blazer': 'Nike',
                'pegasus': 'Nike',
                'vomero': 'Nike',
                'monarch': 'Nike',
                'superstar': 'Adidas',
                'stan smith': 'Adidas',
                'samba': 'Adidas',
                'gazelle': 'Adidas',
                'campus': 'Adidas',
                'forum': 'Adidas',
                'ozweego': 'Adidas',
                'yeezy': 'Adidas',
                'old skool': 'Vans',
                'sk8-hi': 'Vans',
                'chuck taylor': 'Converse',
                'all star': 'Converse',
                '550': 'New Balance',
                '2002r': 'New Balance',
                '9060': 'New Balance',
                '530': 'New Balance',
                '574': 'New Balance',
                'gel-lyte': 'Asics',
                'gel-kayano': 'Asics',
                'gel-1130': 'Asics',
                'club c': 'Reebok',
                'classic leather': 'Reebok'
            }
            
            found_brand = False
            # Сначала ищем по моделям (более специфично)
            for model, br in model_to_brand.items():
                if model in title_lower:
                    brand = br
                    found_brand = True
                    break
            
            # Если не нашли по модели, ищем по списку брендов
            if not found_brand:
                for k, v in known_brands.items():
                    if k in title_lower:
                        brand = v
                        found_brand = True
                        break
            
            # Если не нашли известный бренд, и первое слово не Brand, берем его
            if not found_brand:
                parts = title.split()
                if parts and parts[0].lower() != 'brand':
                    brand = parts[0]
                elif len(parts) > 1 and parts[0].lower() == 'brand':
                    pass

        # 2. Определение категории по названию (если текущая "Каталог" или "Товар")
        category = current_category
        if category.lower() in ['каталог', 'товар', 'одежда', 'обувь']:
            category_map = {
                'socks': 'Носки',
                't-shirt': 'Футболка',
                'tee': 'Футболка',
                'hoodie': 'Худи',
                'jacket': 'Куртка',
                'coat': 'Пальто',
                'pants': 'Брюки',
                'trousers': 'Брюки',
                'shorts': 'Шорты',
                'sweatshirt': 'Свитшот',
                'sweater': 'Свитер',
                'bag': 'Сумка',
                'backpack': 'Рюкзак',
                'cap': 'Кепка',
                'hat': 'Шапка',
                'beanie': 'Шапка',
                'sandal': 'Сандалии',
                'slide': 'Шлепанцы',
                'slippers': 'Тапочки',
                'boot': 'Ботинки',
                'sneaker': 'Кроссовки',
                'shoe': 'Обувь',
                'low': 'Кроссовки', # Часто в названиях кроссовок (Dunk Low)
                'mid': 'Кроссовки',
                'high': 'Кроссовки',
                'retro': 'Кроссовки',
                'og': 'Кроссовки',
                'court': 'Кроссовки',
                'air': 'Кроссовки',
                'storm-fit': 'Куртка',
                'down': 'Пуховик',
                'parka': 'Парка',
                'windrunner': 'Ветровка'
            }
            
            # Ищем совпадения
            for eng, rus in category_map.items():
                # Проверяем слово целиком или как часть
                if eng in title_lower:
                    category = rus
                    break
            
            # Если категория все еще не определена, но мы нашли обувной бренд, ставим Кроссовки
            # ВАЖНО: Только если в названии нет явных признаков одежды!
            clothing_keywords = [
                'jacket', 'coat', 'hoodie', 't-shirt', 'pants', 'shorts', 'sweatshirt', 'sweater', 
                'vest', 'parka', 'down', 'fleece', 'top', 'shirt', 'storm-fit', 'dri-fit', 
                'therma-fit', 'tech fleece', 'aeroloft', 'tracksuit', 'joggers', 'leggings', 
                'tights', 'bra', 'skirt', 'dress', 'windrunner', 'anorak'
            ]
            is_clothing = any(k in title_lower for k in clothing_keywords)
            
            if category.lower() in ['каталог', 'товар', 'одежда', 'обувь'] and not is_clothing and brand in ['Nike', 'Adidas', 'Jordan', 'New Balance', 'Asics', 'Puma', 'Reebok', 'Vans', 'Converse']:
                 category = 'Кроссовки'
            
            # Если это одежда, но категория все еще "Товар", попробуем уточнить
            if category.lower() in ['каталог', 'товар', 'одежда'] and is_clothing:
                if 'jacket' in title_lower or 'coat' in title_lower or 'parka' in title_lower or 'storm-fit' in title_lower or 'windrunner' in title_lower or 'anorak' in title_lower:
                    category = 'Куртка'
                elif 'hoodie' in title_lower or 'sweatshirt' in title_lower or 'tech fleece' in title_lower:
                    category = 'Худи'
                elif 't-shirt' in title_lower or 'tee' in title_lower:
                    category = 'Футболка'
                elif 'pants' in title_lower or 'trousers' in title_lower or 'joggers' in title_lower or 'leggings' in title_lower:
                    category = 'Брюки'
                elif 'shorts' in title_lower:
                    category = 'Шорты'
            
        # 3. Очистка названия
        # Разбиваем на слова
        words = title.split()
        
        # Слова, которые нужно удалить из начала (бренд, категория, мусор)
        remove_words = set()
        if brand:
            # Добавляем части бренда по отдельности
            for part in brand.lower().split():
                remove_words.add(part)
            remove_words.add(brand.lower())
            
            # Специфичные сокращения брендов
            if brand.lower() == 'new balance':
                remove_words.add('nb')
            if brand.lower() == 'the north face':
                remove_words.add('tnf')
            if brand.lower() == 'yeezy':
                remove_words.add('yz')
            
        if category:
            remove_words.add(category.lower())
            # Добавляем отдельные слова из категории
            for part in category.lower().split():
                if len(part) > 2: # Не удаляем предлоги типа "и"
                    remove_words.add(part)
            
        remove_words.add('brand')
        remove_words.add('тапки')
        remove_words.add('товар')
        remove_words.add('каталог')
        remove_words.add('кроссовки')
        remove_words.add('кеды')
        remove_words.add('обувь')
        remove_words.add('одежда')
        remove_words.add('куртка')
        remove_words.add('ветровка')
        remove_words.add('пуховик')
        remove_words.add('футболка')
        remove_words.add('худи')
        remove_words.add('толстовка')
        remove_words.add('брюки')
        remove_words.add('штаны')
        remove_words.add('шорты')
        remove_words.add('носки')
        remove_words.add('сумка')
        remove_words.add('рюкзак')
        remove_words.add('кепка')
        remove_words.add('шапка')
        remove_words.add('и')
        remove_words.add('&')
        remove_words.add('+')
        
        # Удаляем слова из начала
        # Проверяем первое слово
        while words:
            first_word = words[0].lower()
            should_remove = False
            
            if first_word in remove_words:
                should_remove = True
            
            # Проверка на части бренда (например "The" из "The North Face")
            if brand and first_word in brand.lower().split():
                should_remove = True
                
            if should_remove:
                words.pop(0)
            else:
                break
            
        clean_title = " ".join(words)
        
        return clean_title, brand, category

    def update_product(self, product_id, product_data=None):
        if product_data:
            product = product_data
        else:
            print(f"Getting product {product_id}...")
            product = self.get_product(product_id)
            
        if not product:
            print("Product not found or error.")
            return

        with print_lock:
            print(f"=== Обновление товара {product_id} ===")
            print(f"Текущее название: {product['name']}")
        
        logger.info(f"=== Обновление товара {product_id} ===")
        logger.info(f"Текущее название: {product['name']}")
        
        # Проверка даты (если нужно массово, но сейчас для теста одного товара)
        date_created = datetime.strptime(product['date_created'], "%Y-%m-%dT%H:%M:%S")
        logger.info(f"Дата создания: {date_created}")
        
        # 1. Подготовка данных
        attributes = product.get('attributes', [])
        
        # Извлекаем категорию
        category = "Товар"
        if product.get('categories'):
            # Пытаемся найти наиболее специфичную категорию
            ignored_cats = ['каталог', 'товар', 'одежда', 'обувь', 'brands', 'бренды', 'новинки', 'скидки']
            found_specific = False
            for cat in product['categories']:
                if cat['name'].lower() not in ignored_cats:
                    category = cat['name']
                    found_specific = True
                    break
            
            # Если не нашли специфичную, берем первую (или оставляем Товар)
            if not found_specific and product['categories']:
                category = product['categories'][0]['name']
            
        # Извлекаем артикул
        sku = product.get('sku', '')
        
        # Анализируем и очищаем данные
        clean_title_text, brand, category = self.analyze_product_data(product['name'], attributes, category)
        
        logger.info(f"Определен бренд: {brand}")
        logger.info(f"Определена категория: {category}")
        logger.info(f"Очищенное название модели: {clean_title_text}")
        
        with print_lock:
            print(f"Определен бренд: {brand}")
            print(f"Определена категория: {category}")
            print(f"Очищенное название модели: {clean_title_text}")
        
        # Извлекаем цвет и материал для промпта
        color = ""
        material = ""
        for attr in attributes:
            name = attr['name'].lower()
            if 'цвет' in name or 'color' in name:
                color = attr['options'][0]
            if 'материал' in name or 'material' in name:
                material = attr['options'][0]

        # 2. Генерация SEO контента
        with print_lock:
            print(f"Генерация SEO контента для {product_id}...")
        logger.info("Генерация SEO контента...")
        
        # Подготавливаем атрибуты в формате для OpenAIService
        seo_attributes = []
        if color: seo_attributes.append({'name': 'Color', 'value': color})
        if material: seo_attributes.append({'name': 'Material', 'value': material})
        
        # Если категория слишком общая, не используем её в SEO промпте, чтобы не получить "Каталог Nike..."
        seo_category = category
        if seo_category.lower() in ['каталог', 'товар', 'brands', 'бренды', 'новинки', 'скидки', 'одежда', 'обувь']:
            seo_category = ""

        seo_data = self.openai.translate_and_generate_seo(
            title=clean_title_text,
            description="", # Не используем старое описание
            category=seo_category,
            brand=brand,
            attributes=seo_attributes,
            article_number=sku
        )
        
        if not seo_data:
            with print_lock:
                print(f"Не удалось сгенерировать SEO контент для {product_id}.")
            logger.error("Не удалось сгенерировать SEO контент. Пропускаем обновление контента.")
            tokens_used = 0
        else:
            tokens_used = seo_data.get('tokens', 0)
            with print_lock:
                print(f"SEO контент сгенерирован для {product_id}. Потрачено токенов: {tokens_used}")
        
        # 3. Обработка изображений
        with print_lock:
            print(f"Обработка изображений для {product_id}...")
        logger.info("Обработка изображений...")
        new_images, old_image_ids = self.process_images(product)
        with print_lock:
            print(f"Обработано изображений для {product_id}: {len(new_images)}")
        
        # 4. Формирование обновления
        update_data = {}
        
        # Обновление атрибута Бренд
        # Ищем существующий атрибут бренда в товаре
        brand_attribute_found = False
        new_attributes = []
        
        for attr in attributes:
            # Копируем атрибут
            new_attr = attr.copy()
            
            # Если это бренд - обновляем его
            if attr['name'].lower() in ['бренд', 'brand', 'pa_brand']:
                new_attr['options'] = [brand]
                brand_attribute_found = True
                # print(f"Обновляем атрибут бренда на: {brand}")
            
            new_attributes.append(new_attr)
            
        # Если атрибута бренда не было, но мы его определили - добавляем?
        # Лучше не добавлять, если не уверены в ID глобального атрибута.
        # Но если он был (а он был "Brand"), мы его обновили.
        
        if brand_attribute_found:
            update_data['attributes'] = new_attributes
        
        if seo_data:
            # Обработка ключевых слов
            raw_keywords = seo_data.get('keywords', '')
            
            # Убираем "Теги:" и прочее
            clean_keywords = raw_keywords
            if clean_keywords.lower().startswith('теги:'):
                clean_keywords = clean_keywords[5:].strip()
            elif clean_keywords.lower().startswith('tags:'):
                clean_keywords = clean_keywords[5:].strip()
                
            # Заменяем запятые на точки с запятой, если нужно
            # Пользователь просил "через точку с запятой"
            # Если там уже запятые, меняем их
            if ',' in clean_keywords:
                parts = [k.strip() for k in clean_keywords.split(',')]
                clean_keywords = "; ".join(parts)
            
            update_data.update({
                'name': seo_data['title_ru'],
                'description': seo_data['full_description'],
                'short_description': seo_data['short_description'],
                'meta_data': [
                    {'key': '_yoast_wpseo_title', 'value': seo_data['seo_title']},
                    {'key': '_yoast_wpseo_metadesc', 'value': seo_data['meta_description']},
                    {'key': '_yoast_wpseo_focuskw', 'value': clean_keywords}
                ]
            })
            
            # Обновляем теги - только бренд
            update_data['tags'] = [{'name': brand}]

        if new_images:
            update_data['images'] = new_images
            
        # 5. Отправка обновления
        if update_data:
            with print_lock:
                print(f"Отправка обновления для {product_id} в WooCommerce...")
            try:
                url = f"{self.wc.url}/wp-json/wc/v3/products/{product_id}"
                response = requests.put(url, auth=self.wc.auth, json=update_data, verify=False, timeout=60)
                response.raise_for_status()
                with print_lock:
                    print(f"Товар {product_id} успешно обновлен.")
                logger.info(f"✅ Товар {product_id} успешно обновлен")
                
                # 6. Удаление старых изображений (только после успешного обновления!)
                if old_image_ids:
                    with print_lock:
                        print(f"Удаление {len(old_image_ids)} старых изображений для {product_id}...")
                    logger.info(f"Удаление {len(old_image_ids)} старых изображений...")
                    for img_id in old_image_ids:
                        self.delete_image(img_id)
                    with print_lock:
                        print(f"Старые изображения для {product_id} удалены.")
                        
            except Exception as e:
                with print_lock:
                    print(f"Ошибка при обновлении товара {product_id}: {e}")
                logger.error(f"Ошибка при обновлении товара в WordPress: {e}")
        else:
            with print_lock:
                print(f"Нет данных для обновления {product_id}.")
            logger.warning("Нет данных для обновления")
            
        return tokens_used

    def process_single_product_safe(self, product, total_products, total_pages, current_page):
        try:
            # Call the existing update logic
            tokens = self.update_product(product['id'], product_data=product)
            if tokens is None: tokens = 0
            
            with print_lock:
                self.stats['processed'] += 1
                self.stats['tokens'] += tokens
                
                elapsed_time = time.time() - self.stats['start_time']
                avg_time = elapsed_time / self.stats['processed'] if self.stats['processed'] > 0 else 0
                
                # Estimate remaining based on total found in this query
                # Note: total_products is the total matching the 'before' filter.
                # Since we process page by page, and we don't know how many we processed in previous runs (if any),
                # we can only estimate based on what we see.
                # But actually, if we run the script, we start from page 1.
                # So remaining = total_products - self.stats['processed'] is a fair estimate for THIS run.
                remaining_products = total_products - self.stats['processed']
                if remaining_products < 0: remaining_products = 0
                
                est_remaining_time = remaining_products * avg_time
                
                print(f"\n[СТАТИСТИКА]")
                print(f"Обработано товаров: {self.stats['processed']}")
                print(f"Потрачено токенов: {self.stats['tokens']}")
                print(f"Среднее время на товар: {avg_time:.1f} сек")
                print(f"Осталось товаров (примерно): {remaining_products}")
                print(f"Осталось времени (примерно): {est_remaining_time/60:.1f} мин")
                print("-" * 30)
                
        except Exception as e:
            logger.error(f"Error in process_single_product_safe for {product['id']}: {e}")

    def update_all_old_products(self, cutoff_date_str="2025-11-12", start_page=1):
        cutoff_date = datetime.strptime(cutoff_date_str, "%Y-%m-%d")
        page = start_page
        per_page = 10 
        
        # Reset stats
        self.stats = {
            'processed': 0,
            'tokens': 0,
            'start_time': time.time()
        }
        
        total_products_header = 0
        
        # Use ThreadPoolExecutor for parallel processing
        # max_workers=5 is a safe bet to avoid rate limits
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            while True:
                print(f"Загрузка страницы {page}...")
                try:
                    params = {
                        "per_page": per_page, 
                        "page": page,
                        "before": f"{cutoff_date_str}T00:00:00",
                        "order": "desc",
                        "orderby": "date"
                    }
                    
                    url = f"{self.wc.url}/wp-json/wc/v3/products"
                    response = requests.get(url, auth=self.wc.auth, params=params, verify=False, timeout=60)
                    
                    if response.status_code != 200:
                        print(f"Ошибка получения списка товаров: {response.status_code}")
                        break
                    
                    products = response.json()
                    if not products:
                        print("Товары закончились.")
                        break
                    
                    total_products_header = int(response.headers.get('X-WP-Total', 0))
                    total_pages = int(response.headers.get('X-WP-TotalPages', 0))
                    
                    print(f"Найдено {len(products)} товаров на странице {page} (Всего: {total_products_header}, Страниц: {total_pages}).")
                    
                    # Submit tasks
                    future_to_product = {executor.submit(self.process_single_product_safe, p, total_products_header, total_pages, page): p for p in products}
                    
                    for future in concurrent.futures.as_completed(future_to_product):
                        product = future_to_product[future]
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"Exception processing product {product['id']}: {e}")
                    
                    page += 1
                    
                except Exception as e:
                    print(f"Критическая ошибка в цикле: {e}")
                    break

def main():
    print("Main started...")
    updater = ProductUpdater()
    
    # Массовое обновление
    print("Запуск массового обновления товаров, загруженных до 12.11.2025...")
    # Start from page 14 as requested
    updater.update_all_old_products("2025-11-12", start_page=45)
    print("Done.")

if __name__ == "__main__":
    main()
