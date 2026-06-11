@echo off

cd /d D:\Pradeep\Project\shareholding

echo ===================================
echo Updating GitHub
echo ===================================

git add .

git commit -m "Auto Update"

git push origin main

echo.
echo Done.
pause
