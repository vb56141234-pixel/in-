@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto needs_setup
".venv\Scripts\python.exe" "launcher.py" --setup-key
if errorlevel 1 echo API 키 설정에 실패했습니다. 위 오류를 확인하세요.
pause
goto end
:needs_setup
echo 먼저 START_HERE.cmd를 실행하여 설치를 완료하세요.
echo 설치 후 앱을 종료하고 이 파일을 다시 실행하세요.
pause
:end
endlocal
