@echo off
title GitHub Update Utility

cd /d D:\Pradeep\Project\shareholding

echo.
echo =====================================
echo        Git Status
echo =====================================
git status

echo.
choice /M "Continue with GitHub update"

if errorlevel 2 exit

echo.
set /p msg=Commit Message:

git add .

git commit -m "%msg%"

if errorlevel 1 (
echo.
echo Nothing to commit.
pause
exit
)

git push origin main

echo.
echo Push completed.
pause
