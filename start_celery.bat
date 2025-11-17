@echo off
chcp 65001 >nul
echo ======================================
echo   ЗАПУСК CELERY WORKER
echo ======================================
echo.

REM Проверка виртуального окружения
if not exist "venv\Scripts\activate.bat" (
    echo ❌ ОШИБКА: Виртуальное окружение не найдено!
    echo.
    echo Сначала запустите install.bat
    pause
    exit /b 1
)

REM Активация виртуального окружения
call venv\Scripts\activate.bat

echo ℹ️  Celery Worker - фоновый обработчик задач
echo.
echo 📝 Это ОПЦИОНАЛЬНО:
echo    - Без Celery: товары обрабатываются в основном потоке (медленнее)
echo    - С Celery: товары обрабатываются в фоне (быстрее, до 1000 товаров)
echo.
echo ⚠️  ТРЕБОВАНИЯ:
echo    - Redis должен быть запущен (start_redis.bat)
echo    - Или настроен другой брокер сообщений
echo.

REM Проверка доступности Redis
python -c "import redis; r = redis.Redis(host='localhost', port=6379); r.ping()" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Redis недоступен!
    echo.
    echo Сначала запустите Redis (start_redis.bat)
    echo Или приложение будет работать без Celery
    echo.
    pause
    exit /b 1
)

echo ✅ Redis доступен
echo.
echo 🚀 Запускаю Celery Worker...
echo.
echo 💡 Для остановки нажмите Ctrl+C
echo.
echo ========================================
echo.

REM Запуск Celery Worker
celery -A celery_tasks worker --loglevel=info --pool=solo

pause
