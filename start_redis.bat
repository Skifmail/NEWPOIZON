@echo off
chcp 65001 >nul
echo ======================================
echo   УСТАНОВКА И ЗАПУСК REDIS
echo ======================================
echo.

REM Проверка наличия Redis
where redis-server >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Redis найден, запускаю...
    echo.
    echo 📝 Redis будет работать на порту 6379
    echo 💡 Для остановки нажмите Ctrl+C
    echo.
    redis-server
    exit /b 0
)

echo ❌ Redis не установлен
echo.
echo ========================================
echo   УСТАНОВКА REDIS ДЛЯ WINDOWS
echo ========================================
echo.
echo Redis обеспечивает быстрое кеширование и очереди задач.
echo Это ОПЦИОНАЛЬНО - приложение работает и без Redis.
echo.
echo 📝 Варианты установки:
echo.
echo 1. Memurai (рекомендуется для Windows):
echo    https://www.memurai.com/get-memurai
echo    - Бесплатная версия Developer Edition
echo    - Простая установка
echo.
echo 2. Redis для Windows (WSL):
echo    - Установите WSL2: wsl --install
echo    - В WSL: sudo apt install redis-server
echo    - Запуск: redis-server
echo.
echo 3. Docker Desktop:
echo    docker run -d -p 6379:6379 redis:latest
echo.
echo 4. Работать без Redis:
echo    Приложение автоматически использует файловый кеш
echo.
echo ========================================
echo.
pause
