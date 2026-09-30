@echo off
chcp 65001 >nul
echo ============================================
echo   CLOUDFLARE TUNNEL - Quick Start
echo   Bien localhost:8000 thanh URL cong khai
echo ============================================
echo.
echo Dang khoi tao tunnel...
echo Sau khi chay, ban se nhan duoc 1 URL dang:
echo   https://xxxxx.trycloudflare.com
echo.
echo Copy URL do va them /api/webhook/email vao cuoi,
echo roi cap nhat vao Cloudflare Email Worker.
echo.
echo Vi du: https://xxxxx.trycloudflare.com/api/webhook/email
echo.
echo Nhan Ctrl+C de dung tunnel.
echo ============================================
echo.

"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
