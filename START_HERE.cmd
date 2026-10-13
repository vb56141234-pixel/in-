@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if errorlevel 1 goto path_error
if exist ".venv\Scripts\python.exe" goto install
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto use_py
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto use_python
echo Python 3.10 이상을 찾을 수 없습니다.
echo https://www.python.org/downloads/ 에서 Python을 설치하세요.
echo 설치 시 Add python.exe to PATH를 선택한 뒤 다시 실행하세요.
goto failed
:use_py
py -3 -m venv ".venv"
if errorlevel 1 goto failed
goto install
:use_python
python -m venv ".venv"
if errorlevel 1 goto failed
:install
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" "launcher.py"
if errorlevel 1 goto failed
goto end
:path_error
echo 프로그램 폴더에 접근할 수 없습니다. 압축을 완전히 풀고 다시 실행하세요.
:failed
echo.
echo 실행하지 못했습니다. 위 오류를 확인하고 README_KO.md를 읽어 주세요.
echo 관리자 권한은 필요하지 않습니다.
pause
:end
endlocal
