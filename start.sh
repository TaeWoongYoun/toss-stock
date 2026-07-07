#!/usr/bin/env bash
# ============================================================
#  Toss Stock CLI  -  macOS / Linux 원클릭 실행
#  실행:  ./start.sh   (처음 한 번:  chmod +x start.sh)
#  하는 일: 파이썬 확인 -> 가상환경 생성 -> 패키지 설치 -> 실행
# ============================================================
set -e
cd "$(dirname "$0")"

# --- 파이썬 찾기 ---
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo
  echo "[!] 파이썬이 설치되어 있지 않습니다."
  echo "    macOS:  brew install python   또는  https://www.python.org/downloads/"
  echo "    Linux:  sudo apt install python3 python3-venv   (배포판에 맞게)"
  echo
  exit 1
fi

# --- 가상환경(.venv) 없으면 생성 ---
if [ ! -x ".venv/bin/python" ]; then
  echo "[*] 최초 실행 - 가상환경을 만드는 중입니다..."
  "$PY" -m venv .venv
fi

VENV_PY=".venv/bin/python"

# --- 패키지 설치 (최초 1회만) ---
if [ ! -f ".venv/.deps-ok" ]; then
  echo "[*] 필요한 패키지를 설치하는 중입니다... 잠시만 기다려주세요."
  "$VENV_PY" -m pip install --upgrade pip -q
  "$VENV_PY" -m pip install -r requirements.txt -q
  echo ok > ".venv/.deps-ok"
fi

# --- 실행 ---
clear 2>/dev/null || true
exec "$VENV_PY" cli.py "$@"
