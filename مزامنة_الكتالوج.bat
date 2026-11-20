@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   ڤايات طحينة - مزامنة كتالوج واتساب
echo ============================================
echo.
python sync_catalog.py
echo.
pause
