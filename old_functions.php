<?php
/**
 * Astra functions and definitions
 *
 * @link https://developer.wordpress.org/themes/basics/theme-functions/
 *
 * @package Astra
 * @since 1.0.0
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // Exit if accessed directly.
}

/**
 * Define Constants
 */
define( 'ASTRA_THEME_VERSION', '4.11.12' );
define( 'ASTRA_THEME_SETTINGS', 'astra-settings' );
define( 'ASTRA_THEME_DIR', trailingslashit( get_template_directory() ) );
define( 'ASTRA_THEME_URI', trailingslashit( esc_url( get_template_directory_uri() ) ) );
define( 'ASTRA_THEME_ORG_VERSION', file_exists( ASTRA_THEME_DIR . 'inc/w-org-version.php' ) );

/**
 * Minimum Version requirement of the Astra Pro addon.
 * This constant will be used to display the notice asking user to update the Astra addon to the version defined below.
 */
define( 'ASTRA_EXT_MIN_VER', '4.11.6' );

/**
 * Load in-house compatibility.
 */
if ( ASTRA_THEME_ORG_VERSION ) {
	require_once ASTRA_THEME_DIR . 'inc/w-org-version.php';
}

/**
 * Setup helper functions of Astra.
 */
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-theme-options.php';
require_once ASTRA_THEME_DIR . 'inc/core/class-theme-strings.php';
require_once ASTRA_THEME_DIR . 'inc/core/common-functions.php';
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-icons.php';

define( 'ASTRA_WEBSITE_BASE_URL', 'https://wpastra.com' );

/**
 * Deprecate constants in future versions as they are no longer used in the codebase.
 */
define( 'ASTRA_PRO_UPGRADE_URL', ASTRA_THEME_ORG_VERSION ? astra_get_pro_url( '/pricing/', 'free-theme', 'dashboard', 'upgrade' ) : 'https://woocommerce.com/products/astra-pro/' );
define( 'ASTRA_PRO_CUSTOMIZER_UPGRADE_URL', ASTRA_THEME_ORG_VERSION ? astra_get_pro_url( '/pricing/', 'free-theme', 'customizer', 'upgrade' ) : 'https://woocommerce.com/products/astra-pro/' );

/**
 * Update theme
 */
require_once ASTRA_THEME_DIR . 'inc/theme-update/astra-update-functions.php';
require_once ASTRA_THEME_DIR . 'inc/theme-update/class-astra-theme-background-updater.php';

/**
 * Fonts Files
 */
require_once ASTRA_THEME_DIR . 'inc/customizer/class-astra-font-families.php';
if ( is_admin() ) {
	require_once ASTRA_THEME_DIR . 'inc/customizer/class-astra-fonts-data.php';
}

require_once ASTRA_THEME_DIR . 'inc/lib/webfont/class-astra-webfont-loader.php';
require_once ASTRA_THEME_DIR . 'inc/lib/docs/class-astra-docs-loader.php';
require_once ASTRA_THEME_DIR . 'inc/customizer/class-astra-fonts.php';

require_once ASTRA_THEME_DIR . 'inc/dynamic-css/custom-menu-old-header.php';
require_once ASTRA_THEME_DIR . 'inc/dynamic-css/container-layouts.php';
require_once ASTRA_THEME_DIR . 'inc/dynamic-css/astra-icons.php';
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-walker-page.php';
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-enqueue-scripts.php';
require_once ASTRA_THEME_DIR . 'inc/core/class-gutenberg-editor-css.php';
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-wp-editor-css.php';
require_once ASTRA_THEME_DIR . 'inc/dynamic-css/block-editor-compatibility.php';
require_once ASTRA_THEME_DIR . 'inc/dynamic-css/inline-on-mobile.php';
require_once ASTRA_THEME_DIR . 'inc/dynamic-css/content-background.php';
require_once ASTRA_THEME_DIR . 'inc/dynamic-css/dark-mode.php';
require_once ASTRA_THEME_DIR . 'inc/class-astra-dynamic-css.php';
require_once ASTRA_THEME_DIR . 'inc/class-astra-global-palette.php';

// Enable NPS Survey only if the starter templates version is < 4.3.7 or > 4.4.4 to prevent fatal error.
if ( ! defined( 'ASTRA_SITES_VER' ) || version_compare( ASTRA_SITES_VER, '4.3.7', '<' ) || version_compare( ASTRA_SITES_VER, '4.4.4', '>' ) ) {
	// NPS Survey Integration
	require_once ASTRA_THEME_DIR . 'inc/lib/class-astra-nps-notice.php';
	require_once ASTRA_THEME_DIR . 'inc/lib/class-astra-nps-survey.php';
}

/**
 * Custom template tags for this theme.
 */
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-attr.php';
require_once ASTRA_THEME_DIR . 'inc/template-tags.php';

require_once ASTRA_THEME_DIR . 'inc/widgets.php';
require_once ASTRA_THEME_DIR . 'inc/core/theme-hooks.php';
require_once ASTRA_THEME_DIR . 'inc/admin-functions.php';
require_once ASTRA_THEME_DIR . 'inc/class-astra-memory-limit-notice.php';
require_once ASTRA_THEME_DIR . 'inc/core/sidebar-manager.php';

/**
 * Markup Functions
 */
require_once ASTRA_THEME_DIR . 'inc/markup-extras.php';
require_once ASTRA_THEME_DIR . 'inc/extras.php';
require_once ASTRA_THEME_DIR . 'inc/blog/blog-config.php';
require_once ASTRA_THEME_DIR . 'inc/blog/blog.php';
require_once ASTRA_THEME_DIR . 'inc/blog/single-blog.php';

/**
 * Markup Files
 */
require_once ASTRA_THEME_DIR . 'inc/template-parts.php';
require_once ASTRA_THEME_DIR . 'inc/class-astra-loop.php';
require_once ASTRA_THEME_DIR . 'inc/class-astra-mobile-header.php';

/**
 * Functions and definitions.
 */
require_once ASTRA_THEME_DIR . 'inc/class-astra-after-setup-theme.php';

// Required files.
require_once ASTRA_THEME_DIR . 'inc/core/class-astra-admin-helper.php';

require_once ASTRA_THEME_DIR . 'inc/schema/class-astra-schema.php';

/* Setup API */
require_once ASTRA_THEME_DIR . 'admin/includes/class-astra-api-init.php';

if ( is_admin() ) {
	/**
	 * Admin Menu Settings
	 */
	require_once ASTRA_THEME_DIR . 'inc/core/class-astra-admin-settings.php';
	require_once ASTRA_THEME_DIR . 'admin/class-astra-admin-loader.php';
	require_once ASTRA_THEME_DIR . 'inc/lib/astra-notices/class-astra-notices.php';
}

/**
 * Metabox additions.
 */
require_once ASTRA_THEME_DIR . 'inc/metabox/class-astra-meta-boxes.php';
require_once ASTRA_THEME_DIR . 'inc/metabox/class-astra-meta-box-operations.php';
require_once ASTRA_THEME_DIR . 'inc/metabox/class-astra-elementor-editor-settings.php';

/**
 * Customizer additions.
 */
require_once ASTRA_THEME_DIR . 'inc/customizer/class-astra-customizer.php';

/**
 * Astra Modules.
 */
require_once ASTRA_THEME_DIR . 'inc/modules/posts-structures/class-astra-post-structures.php';
require_once ASTRA_THEME_DIR . 'inc/modules/related-posts/class-astra-related-posts.php';

/**
 * Compatibility
 */
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-gutenberg.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-jetpack.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/woocommerce/class-astra-woocommerce.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/edd/class-astra-edd.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/lifterlms/class-astra-lifterlms.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/learndash/class-astra-learndash.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-beaver-builder.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-bb-ultimate-addon.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-contact-form-7.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-visual-composer.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-site-origin.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-gravity-forms.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-bne-flyout.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-ubermeu.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-divi-builder.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-amp.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-yoast-seo.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/surecart/class-astra-surecart.php';
require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-starter-content.php';
require_once ASTRA_THEME_DIR . 'inc/addons/transparent-header/class-astra-ext-transparent-header.php';
require_once ASTRA_THEME_DIR . 'inc/addons/breadcrumbs/class-astra-breadcrumbs.php';
require_once ASTRA_THEME_DIR . 'inc/addons/scroll-to-top/class-astra-scroll-to-top.php';
require_once ASTRA_THEME_DIR . 'inc/addons/heading-colors/class-astra-heading-colors.php';
require_once ASTRA_THEME_DIR . 'inc/builder/class-astra-builder-loader.php';

// Elementor Compatibility requires PHP 5.4 for namespaces.
if ( version_compare( PHP_VERSION, '5.4', '>=' ) ) {
	require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-elementor.php';
	require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-elementor-pro.php';
	require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-web-stories.php';
}

// Beaver Themer compatibility requires PHP 5.3 for anonymous functions.
if ( version_compare( PHP_VERSION, '5.3', '>=' ) ) {
	require_once ASTRA_THEME_DIR . 'inc/compatibility/class-astra-beaver-themer.php';
}

require_once ASTRA_THEME_DIR . 'inc/core/markup/class-astra-markup.php';

/**
 * Load deprecated functions
 */
require_once ASTRA_THEME_DIR . 'inc/core/deprecated/deprecated-filters.php';
require_once ASTRA_THEME_DIR . 'inc/core/deprecated/deprecated-hooks.php';
require_once ASTRA_THEME_DIR . 'inc/core/deprecated/deprecated-functions.php';

// Добавляем текст о возврате после краткого описания
function add_return_policy_notice() {
    // Проверяем, что находимся на странице товара
    if ( is_product() ) {
        // Получаем текущий продукт
        global $product;
        // Выводим плашку с информацией о возврате
        echo '<div class="return-policy-notice">
                <p style="margin-top: 20px; padding: 15px; background-color: #4169e1; border-radius: 5px; color: #ffffff;">
                    <strong>Важно:</strong> Возврат в течение 14 рабочих дней, даже если не подошел размер
                </p>
            </div>';
    }
}
// Подключаем функцию к нужному хуку
add_action( 'woocommerce_single_product_summary', 'add_return_policy_notice', 35 );

/**
 * Добавляет кнопку "Таблица размеров" после атрибутов и перед кнопкой "В корзину"
 */
add_action('woocommerce_before_add_to_cart_button', 'add_size_table_button_before_cart', 5);

function add_size_table_button_before_cart() {
    if (!is_product()) {
        return;
    }
    
    $size_table_url = home_url('/size/');
    
	echo '<div class="size-table-notice" style="margin-bottom: 15px;">';
    echo '<a href="' . esc_url($size_table_url) . '" class="button alt" style="font-size: 14px; padding: 8px 12px;" target="_blank">';
    echo '📏 Таблица размеров';
    echo '</a>';
    echo '</div>';
}

/**
 * Устанавливаем количество товаров на странице каталога: 8 товаров (2 строки по 4)
 */
add_filter('loop_shop_per_page', 'set_products_per_page', 20);

function set_products_per_page($products_per_page) {
    // Устанавливаем 8 товаров на страницу
    return 8;
}

/**
 * Меняем количество колонок в каталоге на 4
 */
add_filter('loop_shop_columns', 'set_shop_columns', 20);

function set_shop_columns($columns) {
    // Устанавливаем 4 колонки
    return 4;
}

/**
 * Убираем пагинацию если товаров меньше или равно 8
 */
add_filter('woocommerce_product_loop_start', 'custom_products_per_page_control');

function custom_products_per_page_control($loop_start) {
    global $wp_query;
    
    // Если товаров 8 или меньше, скрываем пагинацию
    if ($wp_query->found_posts <= 8) {
        remove_action('woocommerce_after_shop_loop', 'woocommerce_pagination', 10);
    }
    
    return $loop_start;
}

// Добавляем шаблон баннера на страницы каталога, а на странице товара убираем метки
function sa_show_banner_in_catalog() {
	echo '<style>
		.site-content .ast-container { flex-wrap: wrap; }
		@media screen and (max-width: 993px) {
			.sa-catalog-banner-section { order: 3; }
		}
	</style>';
	echo do_shortcode('[elementor-template id="23746"]');
	echo '<script>
		document.querySelectorAll(".sa-catalog-banner").forEach(function(element) {
			element.parentElement.classList.add("sa-catalog-banner-section");
		});
	</script>';
	if (is_product()) {
		echo '<style>
			.product_meta span.tagged_as { display: none !important; }
		</style>';
	}
}
add_action('woocommerce_before_main_content', 'sa_show_banner_in_catalog', 5);

// Фильтр для мобильой версии
function sa_wp_footer_functions() {
	if ( is_shop() || is_product_category() || is_product() ) { ?>
		<style>
			.sa-top-filter-block, .sa-top-filter-content { display: none; }
			@media screen and (max-width: 768px) {
				.sa-top-filter-block { display: flex; gap: 10px; width: 100%; }
				.sa-top-filter-block-left { width: 100%; }
				.sa-top-filter-block-right { width: calc(50% - 5px); max-width: calc(50% - 5px); min-width: calc(50% - 5px); }
				.sa-top-filter-block-left .button { width: 100%; cursor: pointer; text-align: center; }
				.sa-top-filter-close { font-weight: 600; font-size: 14px; margin-top: 20px; border-bottom: 1px solid grey; color: grey; cursor: pointer; width: fit-content; }
				.woocommerce-page .woocommerce-ordering select { font-size: 14px; }
				.woocommerce .woocommerce-ordering, .woocommerce-page .woocommerce-ordering { margin-bottom: 0; }
			}
			@media screen and (max-width: 768px) {
				.woocommerce-page .woocommerce-ordering select { font-size: 12px; }
			}
		</style>
		<script>
			jQuery(document).ready(function($) {
				if ($(window).width() < 768) {
					$('.woocommerce-products-header').after('<div class="sa-top-filter-block"><div class="sa-top-filter-block-left"><div class="button">Фильтр</div></div><div class="sa-top-filter-block-right"></div></div><div class="sa-top-filter-content"><div class="sa-top-filter-close">Скрыть фильтр</div></div>');
					$('#woof_widget-3').prependTo($('.sa-top-filter-content'));
					if ($('form.woocommerce-ordering').length > 0) {
						$('.woocommerce-ordering').appendTo($('.sa-top-filter-block-right'));
					} else {
						$('.sa-top-filter-block-right').remove();
					}
					$('.sa-top-filter-block-left .button').click(function() {
						if ($('.sa-top-filter-content').hasClass('active')) {
							$('.sa-top-filter-content').removeClass('active');
							$('.sa-top-filter-content').slideUp('slow');
							$(this).text('Фильтр');
						} else {
							$('.sa-top-filter-content').addClass('active');
							$('.sa-top-filter-content').slideDown('slow');
							$(this).text('Скрыть');
						}
					});
					$('.sa-top-filter-close').click(function() {
						$('.sa-top-filter-content').removeClass('active');
						$('.sa-top-filter-content').slideUp('slow');
						$('.sa-top-filter-block-left .button').text('Фильтр');
					});
				}
			});
		</script>
	<? }
}
add_action('wp_footer', 'sa_wp_footer_functions');


function sa_custom_products_per_page($query) {
	if (!is_admin() && $query->is_main_query() && ($query->is_post_type_archive('product') || $query->is_tax('product_cat') || $query->is_tax('product_tag'))) {
		$query->set('posts_per_page', 48);
	}
}
add_action('pre_get_posts', 'sa_custom_products_per_page');


/**
 * Отключаем ненужные стандартные размеры WordPress
 */
function optimize_disable_default_image_sizes() {
    // Отключаем встроенные размеры WordPress
    remove_image_size('medium_large');
    remove_image_size('large');
    remove_image_size('1536x1536');
    remove_image_size('2048x2048');
}
add_action('init', 'optimize_disable_default_image_sizes');


function optimize_woocommerce_image_sizes($sizes) {
    
    // Обновляем параметры для стандартных размеров, не удаляя остальные
    $sizes['thumbnail'] = array(
        'width'  => 150,
        'height' => 150,
        'crop'   => 1,
    );
    
    $sizes['woocommerce_thumbnail'] = array(
        'width'  => 300,
        'height' => 300,
        'crop'   => 1,
    );
    
    $sizes['woocommerce_single'] = array(
        'width'  => 600,
        'height' => 600,
        'crop'   => 1,
    );
    
    $sizes['woocommerce_gallery_thumbnail'] = array(
        'width'  => 150,
        'height' => 150,
        'crop'   => 1,
    );
	
	$sizes['woocommerce_thumbnail_preview'] = array(
        'width'  => 150,
        'height' => 150,
        'crop'   => 1,
    );

    return $sizes;
}
add_filter('intermediate_image_sizes_advanced', 'optimize_woocommerce_image_sizes');
function optimize_remove_theme_image_sizes($sizes) {
    unset($sizes['post-thumbnail']);
    unset($sizes['shop_catalog']);
    unset($sizes['shop_single']);
    unset($sizes['shop_thumbnail']);
    return $sizes;
}

add_filter('jpeg_quality', function() { return 95; });
add_filter('wp_editor_set_quality', function() { return 95; });


add_action('after_setup_theme', function () {
    add_theme_support('woocommerce');

    // Включаем галерею под главным фото
    add_theme_support('wc-product-gallery-zoom');
    add_theme_support('wc-product-gallery-lightbox');
    add_theme_support('wc-product-gallery-slider');
    add_image_size('woocommerce_gallery_thumbnail', 150, 150, true); // миниатюры под фото
    add_image_size('woocommerce_thumbnail', 300, 300, true);         // сетка каталога
    add_image_size('woocommerce_single', 600, 600, true);            // карточка товара
	add_image_size('woocommerce_thumbnail_preview', 150, 150, true); // Для мобильного приложения

});

add_filter('woocommerce_get_image_size_gallery_thumbnail', function ($size) {
    return array('width' => 150, 'height' => 150, 'crop' => 1);
});
add_filter('woocommerce_get_image_size_thumbnail', function ($size) {
    return array('width' => 300, 'height' => 300, 'crop' => 1);
});
add_filter('woocommerce_get_image_size_single', function ($size) {
    return array('width' => 600, 'height' => 600, 'crop' => 1);
});
add_filter('woocommerce_get_image_size_woocommerce_thumbnail_preview', function ($size) {
    return array('width' => 150, 'height' => 150, 'crop' => 1);
});

add_filter('jpeg_quality', fn() => 95);
add_filter('wp_editor_set_quality', fn() => 95);

// Информационный блок в карточке товара
function sa_info_block_in_priduct() { ?>
<style>
.sa-custom-info { border: 1px solid #4169e1; border-radius: 5px; }
.sa-custom-info .sa-custom-info-item { padding: 16px; display: flex; border-bottom: 1px solid #4169e1; align-items: center; gap: 12px; }
	.sa-custom-info .sa-custom-info-item:last-child { border-bottom: none; }
	.sa-custom-icon { display: flex; align-items: center; }
	.sa-custom-text { width: 100%; }
	.sa-open-conditions { opacity: .6; transition: .5s; cursor: pointer; }
	.sa-open-conditions:hover { opacity: 1; }
</style>
	<div class="sa-custom-info">
		<div class="sa-custom-info-item">
			<div class="sa-custom-icon"><svg version="1.0" xmlns="http://www.w3.org/2000/svg" width="1280.000000pt" height="899.000000pt" viewBox="0 0 1280.000000 899.000000" preserveAspectRatio="xMidYMid meet" style="width: 24px; height: 24px;"><g transform="translate(0.000000,899.000000) scale(0.100000,-0.100000)" fill="#4169e1" stroke="none"><path d="M866 8974 c-141 -34 -282 -144 -350 -273 -71 -135 -66 102 -66 -2969 0 -2749 0 -2773 20 -2812 11 -21 36 -51 57 -67 l36 -28 3144 -3 c3139 -2 3144 -2 3183 18 22 11 52 39 67 62 l28 42 3 2768 c2 2429 0 2777 -13 2841 -39 187 -166 333 -353 406 l-67 26 -2815 2 c-2404 1 -2824 -1 -2874 -13z"/><path d="M7790 7846 c-138 -40 -221 -119 -262 -248 -17 -58 -18 -160 -18 -2694 l0 -2634 -1410 0 -1409 0 51 -47 c210 -197 376 -496 435 -785 l18 -88 1487 0 1487 0 6 38 c78 457 379 868 792 1080 667 341 1471 147 1907 -462 133 -186 208 -368 262 -634 l4 -22 753 0 753 0 50 25 c28 14 60 40 74 62 l25 36 3 316 c2 203 -1 329 -7 352 -15 49 -45 86 -92 109 -35 18 -59 20 -283 20 l-245 0 -4 1348 c-3 1498 2 1374 -72 1599 -47 142 -100 243 -228 433 -572 853 -1102 1630 -1159 1698 -203 242 -497 413 -835 484 -107 22 -113 23 -1073 25 -770 2 -974 -1 -1010 -11z m2207 -1005 c36 -20 108 -119 490 -660 246 -350 458 -656 470 -680 27 -52 29 -97 8 -148 -21 -50 -42 -72 -90 -94 -38 -18 -96 -19 -1213 -19 -1033 0 -1177 2 -1209 15 -50 21 -72 42 -94 90 -17 38 -19 81 -19 708 0 728 -2 704 58 760 61 58 43 57 832 54 l725 -2 42 -24z"/><path d="M105 2253 c-47 -24 -73 -53 -90 -97 -13 -35 -15 -90 -13 -362 l3 -321 25 -37 c15 -22 45 -47 75 -61 l50 -25 1034 2 1034 3 18 87 c56 271 191 525 387 729 l94 99 -1293 0 c-1160 -1 -1297 -2 -1324 -17z"/><path d="M3520 2255 c-240 -40 -481 -170 -641 -343 -418 -455 -407 -1145 26 -1577 125 -126 276 -219 443 -275 414 -139 871 -27 1172 286 143 148 236 311 288 502 24 88 26 114 26 287 1 178 -1 196 -27 289 -121 437 -469 753 -911 831 -105 18 -271 18 -376 0z m329 -570 c182 -43 342 -196 402 -385 28 -85 30 -230 5 -315 -58 -196 -215 -348 -411 -400 -69 -18 -182 -20 -257 -4 -184 38 -357 193 -420 377 -30 89 -32 258 -4 342 63 189 215 335 397 384 71 19 208 19 288 1z"/><path d="M9462 2255 c-225 -41 -431 -145 -591 -299 -244 -236 -362 -532 -348 -870 22 -528 390 -954 922 -1068 81 -17 332 -17 420 1 606 120 1008 694 910 1300 -39 237 -145 443 -319 617 -173 172 -374 277 -610 319 -106 18 -283 18 -384 0z m392 -589 c223 -85 366 -293 366 -531 0 -152 -58 -292 -166 -399 -290 -291 -783 -184 -930 200 -32 84 -44 234 -25 322 44 199 209 372 411 427 88 24 257 15 344 -19z"/></g></svg></div>
			<div class="sa-custom-text">Бесплатная доставка 6‑16 дней</div>
		</div>
		<div class="sa-custom-info-item">
			<div class="sa-custom-icon"><svg fill="#4169e1" width="800px" height="800px" viewBox="-4 -1.5 24 24" style="width: 24px; height: 24px;" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMinYMin"><path d='M.649 3.322L8 .565l7.351 2.757a1 1 0 0 1 .649.936v4.307c0 3.177-1.372 6.2-3.763 8.292L8 20.565l-4.237-3.708A11.019 11.019 0 0 1 0 8.565V4.258a1 1 0 0 1 .649-.936z' /></svg></div>
			<div class="sa-custom-text">Условия возврата</div>
			<div class="sa-custom-right sa-open-conditions"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" type="mono" config="[object Object]" style="width: 24px; height: 24px;"><path fill="#4169e1" d="M11 7h2v2h-2zm0 5a1 1 0 1 1 2 0v4a1 1 0 1 1-2 0zm1-10C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2m0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8"></path></svg></div>
		</div>
		<div class="sa-custom-info-item">
			<div class="sa-custom-icon"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" type="mono" class="icon___OznRH" config="[object Object]" style="width: 24px; height: 24px;"><path fill="#4169e1" d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2m-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2M9 8V6c0-1.66 1.34-3 3-3s3 1.34 3 3v2z"></path></svg></div>
			<div class="sa-custom-text">Надежные платежи (СБП, карта, Сплит, Долями)</div>
			<div class="sa-custom-right"></div>
		</div>
		<div class="sa-custom-info-item">
			<div class="sa-custom-icon"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" type="mono" class="icon___OznRH" config="[object Object]" style="width: 24px; height: 24px;"><path fill="#4169e1" d="M20 2c1.1 0 2 .9 2 2v18l-4-4H4c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2zM7 11a1 1 0 1 0 0 2h7a1 1 0 1 0 0-2zm0-4a1 1 0 0 0 0 2h10a1 1 0 1 0 0-2z"></path></svg></div>
			<div class="sa-custom-text">Поддержка отвечает быстро</div>
			<div class="sa-custom-right"></div>
		</div>
	</div>
<?php }
add_action('woocommerce_share', 'sa_info_block_in_priduct', 90);

// Убираем кнопку "Добавить в корзину" в цикле WooCommerce
add_filter('woocommerce_loop_add_to_cart_link', '__return_empty_string');

/**
 * Добавляет кастомный размер изображения woocommerce_thumbnail_preview в REST API WooCommerce
 * для мобильного приложения
 */
add_filter('woocommerce_rest_prepare_product_object', function ($response, $product, $request) {
    $data = $response->get_data();
    
    if (!empty($data['images'])) {
        foreach ($data['images'] as $key => $image) {
            $attachment_id = $image['id'];
            $image_meta = wp_get_attachment_metadata($attachment_id);
            
            // Добавляем URL для woocommerce_thumbnail_preview, если размер существует
            if (isset($image_meta['sizes']['woocommerce_thumbnail_preview'])) {
                $upload_dir = wp_upload_dir();
                $file_path = dirname($image_meta['file']) . '/' . $image_meta['sizes']['woocommerce_thumbnail_preview']['file'];
                $data['images'][$key]['woocommerce_thumbnail_preview'] = $upload_dir['baseurl'] . '/' . $file_path;
            }
        }
        
        $response->set_data($data);
    }
    
    return $response;
}, 10, 3);