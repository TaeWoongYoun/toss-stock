"""
종목명 → 종목코드/티커 검색.  (국장 주식 + 국장 ETF + 미장)

데이터 (update_stocks.py 로 생성/갱신):
- krx_stocks.json : 국장 주식 (KOSPI/KOSDAQ)
- kr_etf.json     : 국장 ETF
- us_stocks.json  : 미장 주식/ETF (영문명 → 티커)

추가: 아래 ALIASES — 줄임말/한글 별칭 (예: 삼전, 애플, 엔비디아) 과 거래소 목록에 없는 항목.

토스증권 Open API 는 '이름 검색' 기능이 없어 코드/티커만 받습니다. 그래서 로컬에서 변환합니다.
목록이 오래되면  `python update_stocks.py`  로 갱신하세요.
"""

import os
import sys
import json

# PyInstaller 로 빌드된 .exe 에서는 데이터 파일이 임시 폴더(_MEIPASS)에 풀립니다.
# 일반 실행 시에는 이 소스 파일과 같은 폴더에서 읽습니다.
if getattr(sys, "frozen", False):
    _DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))


def _load(fname: str) -> dict:
    try:
        with open(os.path.join(_DIR, fname), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_KR = _load("krx_stocks.json")
_KR_ETF = _load("kr_etf.json")
_US = _load("us_stocks.json")

# 미국 주식/ETF 한글 별칭 + 자주 쓰는 줄임말
ALIASES: dict[str, str] = {
    # ── 국장 줄임말 ──
    "삼전": "005930", "네이버": "035420", "하이닉스": "000660", "삼바": "207940",
    "카뱅": "323410", "한전": "015760", "SKT": "017670",
    "엘지엔솔": "373220", "엘앤에솔": "373220", "현대자동차": "005380",
    "포스코": "005490", "HYBE": "352820", "JYP": "035900",
    "LS ELECTRIC": "010120", "LS일렉트릭": "010120",
    # ── 미장 한글명 ──
    "애플": "AAPL", "엔비디아": "NVDA", "테슬라": "TSLA",
    "마이크로소프트": "MSFT", "마소": "MSFT", "아마존": "AMZN",
    "구글": "GOOGL", "알파벳": "GOOGL", "메타": "META", "페이스북": "META",
    "넷플릭스": "NFLX", "브로드컴": "AVGO", "팔란티어": "PLTR",
    "인텔": "INTC", "퀄컴": "QCOM", "마이크론": "MU", "코카콜라": "KO",
    "디즈니": "DIS", "스타벅스": "SBUX", "나이키": "NKE", "맥도날드": "MCD",
    "보잉": "BA", "버크셔": "BRK.B", "제이피모건": "JPM", "비자카드": "V",
    "마스터카드": "MA", "페이팔": "PYPL", "우버": "UBER", "에어비앤비": "ABNB",
    "코인베이스": "COIN", "로빈후드": "HOOD", "일라이릴리": "LLY", "릴리": "LLY",
    "유나이티드헬스": "UNH", "존슨앤존슨": "JNJ", "화이자": "PFE", "모더나": "MRNA",
    "엑슨모빌": "XOM", "셰브론": "CVX", "월마트": "WMT", "오라클": "ORCL",
    "세일즈포스": "CRM", "어도비": "ADBE", "팔로알토": "PANW",
    "티에스엠씨": "TSM", "알리바바": "BABA", "마이크로스트래티지": "MSTR",
    "슈퍼마이크로": "SMCI", "포드": "F", "아이온큐": "IONQ",
    # ── 미장 ETF 한글/별칭 ──
    "스파이": "SPY", "나스닥100": "QQQ", "슈드": "SCHD",
    "테크": "TQQQ", "속슬": "SOXL",
    # ── 국장 ETF 음차 별칭 ──
    "코덱스200": "069500", "코덱스레버리지": "122630", "코덱스인버스": "114800",
    "타이거미국S&P500": "360750", "타이거나스닥100": "133690",
    "타이거미국나스닥100": "133690",
}

# 전체 병합 (별칭이 최우선)
STOCK_NAMES: dict[str, str] = {**_US, **_KR_ETF, **_KR, **ALIASES}

# 미국 티커 집합 (티커 직접입력 판별용)
US_TICKERS: set[str] = set(_US.values()) | {v for v in ALIASES.values() if v[:1].isalpha()}


def find_stocks(query: str) -> list[tuple[str, str]]:
    """이름(부분일치)으로 (이름, 코드) 목록 반환. 정확일치 시 그것만. 같은 코드 중복 제거."""
    nq = query.replace(" ", "").lower()
    if not nq:
        return []
    # 1) 정확히 일치하면 그것만
    for name, code in STOCK_NAMES.items():
        if name.replace(" ", "").lower() == nq:
            return [(name, code)]
    # 2) 부분 일치
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name, code in STOCK_NAMES.items():
        if nq in name.replace(" ", "").lower() and code not in seen:
            seen.add(code)
            out.append((name, code))
    out.sort(key=lambda x: (not x[0].replace(" ", "").lower().startswith(nq), len(x[0])))
    return out
