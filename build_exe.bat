@echo off
REM ============================================================
REM  Toss Stock CLI  -  Windows .exe 빌드 (배포자용)
REM  결과물:  dist\toss-stock.exe  (파이썬 설치 없이 실행되는 단일 파일)
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Build toss-stock.exe

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [!] 파이썬이 필요합니다. https://www.python.org/downloads/
  pause
  exit /b 1
)

REM 빌드 전용 가상환경
if not exist ".venv-build\Scripts\python.exe" (
  echo [*] 빌드용 가상환경 생성...
  %PY% -m venv .venv-build
)
set "BPY=.venv-build\Scripts\python.exe"

echo [*] 빌드 도구 설치...
"%BPY%" -m pip install --upgrade pip -q
"%BPY%" -m pip install -r requirements.txt pyinstaller -q

echo [*] exe 빌드 중... (수 분 소요)
"%BPY%" -m PyInstaller --clean --noconfirm toss-stock.spec
if errorlevel 1 (
  echo [!] 빌드 실패.
  pause
  exit /b 1
)

echo.
echo [완료] dist\toss-stock.exe 생성됨.
echo        이 파일 하나만 배포하면 됩니다. (종목 데이터 내장)
echo.
pause
endlocal
