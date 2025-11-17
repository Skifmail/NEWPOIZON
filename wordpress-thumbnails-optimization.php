<?php
/**
 * ИНСТРУКЦИЯ ПО УСТАНОВКЕ:
 * 
 * СПОСОБ 1 - Через админку WordPress (РЕКОМЕНДУЕТСЯ):
 * 1. Войдите в админку WordPress (ваш-сайт.ru/wp-admin)
 * 2. Перейдите: Внешний вид → Редактор тем → functions.php
 * 3. Скопируйте ВСЁ содержимое этого файла (кроме первой строки <?php если она уже есть)
 * 4. Вставьте код В КОНЕЦ файла functions.php вашей активной темы
 * 5. Нажмите "Обновить файл"
 * 6. Установите плагин "Regenerate Thumbnails" и запустите пересоздание для старых картинок
 * 
 * СПОСОБ 2 - Через FTP/SSH на хостинге reg.ru:
 * 1. Подключитесь к хостингу через FileZilla или SSH
 * 2. Откройте файл: /wp-content/themes/ваша-тема/functions.php
 * 3. Добавьте код в конец файла
 * 4. Сохраните
 * 
 * ВАЖНО: После добавления этого кода ВСЕ НОВЫЕ изображения будут создаваться 
 * только в 3 размерах вместо 15!
 * 
 * Для очистки старых thumbnails используйте плагин "Media Cleaner"
 */

// ========================================================================
// ОПТИМИЗАЦИЯ РАЗМЕРОВ ИЗОБРАЖЕНИЙ WOOCOMMERCE
// Уменьшает количество генерируемых thumbnails с 15 до 3
// Экономия: ~80% файлов изображений
// Добавлено: <?php echo date('Y-m-d H:i:s'); ?>

// ========================================================================

/**
 * Отключаем ненужные стандартные размеры WordPress
 */
function optimize_disable_default_image_sizes() {
    // Отключаем встроенные размеры WordPress
    remove_image_size('medium_large'); // 768px (не используется в WooCommerce)
    remove_image_size('large');        // 1024px (слишком большой, у нас есть 600px)
    remove_image_size('1536x1536');    // 2x размер (не нужен)
    remove_image_size('2048x2048');    // 2x размер (не нужен)
}
add_action('init', 'optimize_disable_default_image_sizes');

/**
 * Оставляем только необходимые размеры WooCommerce
 * ВНИМАНИЕ: Оставляем только 3 размера вместо 15!
 */
function optimize_woocommerce_image_sizes($sizes) {
    // Удаляем ВСЕ размеры, кроме необходимых
    return array(
        // 1. Миниатюра для админки WordPress (150x150)
        'thumbnail' => array(
            'width'  => 150,
            'height' => 150,
            'crop'   => 1,
        ),
        
        // 2. Размер для каталога/списка товаров (300x300)
        'woocommerce_thumbnail' => array(
            'width'  => 300,
            'height' => 300,
            'crop'   => 1,
        ),
        
        // 3. Размер для карточки товара (600x600) - основной
        'woocommerce_single' => array(
            'width'  => 600,
            'height' => 600,
            'crop'   => 1,
        ),
    );
}
add_filter('intermediate_image_sizes_advanced', 'optimize_woocommerce_image_sizes');

/**
 * Отключаем генерацию дополнительных размеров от темы
 */
function optimize_remove_theme_image_sizes($sizes) {
    // Удаляем размеры, добавленные темой (если есть)
    unset($sizes['post-thumbnail']);
    unset($sizes['shop_catalog']);
    unset($sizes['shop_single']);
    unset($sizes['shop_thumbnail']);
    unset($sizes['woocommerce_gallery_thumbnail']);
    
    return $sizes;
}
add_filter('intermediate_image_sizes_advanced', 'optimize_remove_theme_image_sizes', 99);

/**
 * Отключаем создание дополнительных размеров для WooCommerce Gallery
 */
add_filter('woocommerce_gallery_thumbnail_size', function() {
    return 'woocommerce_thumbnail'; // Используем существующий размер 300x300
});

// ========================================================================
// КОНЕЦ ОПТИМИЗАЦИИ
// РЕЗУЛЬТАТ: С 15 размеров на изображение → 3 размера (экономия 80% файлов!)
// ========================================================================

/**
 * РЕЗУЛЬТАТ ОПТИМИЗАЦИИ:
 * 
 * ДО:
 * - 15 размеров на изображение (thumbnail, medium, large, woocommerce_thumbnail, 
 *   woocommerce_single, woocommerce_gallery_thumbnail, и т.д.)
 * - Товар с 5 изображениями = 5 × 15 = 75 файлов
 * 
 * ПОСЛЕ:
 * - 3 размера на изображение (только необходимые)
 * - Товар с 5 изображениями = 5 × 3 = 15 файлов
 * 
 * ЭКОНОМИЯ: 80% файлов! (75 → 15)
 * 
 * ДЛЯ 10,000 ТОВАРОВ:
 * - Было: 10,000 × 75 = 750,000 файлов
 * - Стало: 10,000 × 15 = 150,000 файлов (ТОЧНО В ЛИМИТ ХОСТИНГА!)
 */

/**
 * ЧТО ДЕЛАТЬ ПОСЛЕ УСТАНОВКИ:
 * 
 * 1. Установите плагин "Regenerate Thumbnails":
 *    - Плагины → Добавить новый → Найти "Regenerate Thumbnails"
 *    - Установить и активировать
 * 
 * 2. Запустите пересоздание thumbnails для СУЩЕСТВУЮЩИХ изображений:
 *    - Инструменты → Regenerate Thumbnails
 *    - Нажмите "Regenerate Thumbnails For All Attachments"
 *    - Подождите окончания (может занять время для 2000+ товаров)
 * 
 * 3. (Опционально) Удалите старые неиспользуемые thumbnails:
 *    - Установите плагин "Media Cleaner"
 *    - Запустите сканирование
 *    - Удалите неиспользуемые файлы (освободит ~50% места)
 * 
 * 4. Проверьте что сайт работает корректно:
 *    - Откройте любой товар
 *    - Убедитесь что изображения отображаются
 *    - Проверьте каталог товаров
 */
