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
			body .woocommerce-page .woocommerce-ordering select { padding-right: 20px; }
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

// Задаем количество выводимого товара на страницах архива и категорий, т.к. стандартные настройки не работают
function sa_custom_products_per_page($query) {
	if (!is_admin() && $query->is_main_query() && ($query->is_post_type_archive('product') || $query->is_tax('product_cat') || $query->is_tax('product_tag'))) {
		$query->set('posts_per_page', 24);
	}
}
add_action('pre_get_posts', 'sa_custom_products_per_page');