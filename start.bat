@echo off
REM ============================================================
REM  Toss Stock CLI  -  Windows 원클릭 실행
REM  더블클릭하면: 파이썬 확인 -> 가상환경 생성 -> 패키지 설치 -> 실행
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Toss Stock CLI

REM --- 파이썬 찾기 (py 런처 우선, 없으면 python) ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )

if not defined PY (
  echo.
  echo [!] 파이썬이 설치되어 있지 않습니다.
  echo     https://www.python.org/downloads/  에서 Python 3.11 이상을 설치하세요.
  echo     설치 시 "Add Python to PATH" 체크를 꼭 켜주세요.
  echo.
  pause
  exit /b 1
)

REM --- 가상환경(.venv) 없으면 생성 ---
if not exist ".venv\Scripts\python.exe" (
  echo [*] 최초 실행 - 가상환경을 만드는 중입니다...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [!] 가상환경 생성 실패. 파이썬 설치를 확인하세요.
    pause
    exit /b 1
  )
)

set "VENV_PY=.venv\Scripts\python.exe"

REM --- 패키지 설치 (최초 1회만; 완료 표시 파일로 판단) ---
if not exist ".venv\.deps-ok" (
  echo [*] 필요한 패키지를 설치하는 중입니다... 잠시만 기다려주세요.
  "%VENV_PY%" -m pip install --upgrade pip -q
  "%VENV_PY%" -m pip install -r requirements.txt -q
  if errorlevel 1 (
    echo [!] 패키지 설치 실패. 인터넷 연결을 확인하세요.
    pause
    exit /b 1
  )
  echo ok> ".venv\.deps-ok"
)

REM --- 실행 ---
cls
"%VENV_PY%" cli.py %*

echo.
echo [프로그램이 종료되었습니다]
pause
endlocal
