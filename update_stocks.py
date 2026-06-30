"""
종목 목록 자동 갱신 — 국장 주식 + 국장 ETF + 미장(미국).
이름→코드(티커) 사전을 JSON 으로 저장합니다. (추가 라이브러리 불필요)

실행:  python update_stocks.py

생성 파일:
- krx_stocks.json : 국장 주식 (KOSPI/KOSDAQ)  출처: 한국거래소 KIND 상장법인목록
- kr_etf.json     : 국장 ETF                  출처: 네이버 금융 ETF 목록
- us_stocks.json  : 미장 주식/ETF             출처: NASDAQ Trader 심볼 디렉터리

신규 상장/이름 변경 시 다시 실행하면 갱신됩니다.
"""

import os
import re
import html
import json
import urllib.request

DIR = os.path.dirname(os.path.abspath(__file__))

KIND_URL = ("http://kind.krx.co.kr/corpgeneral/corpList.do"
            "?method=download&searchType=13")
NAVER_ETF_URL = "https://finance.naver.com/api/sise/etfItemList.nhn"
US_NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
US_OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


def _get(url: str, encoding: str = "utf-8") -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=40).read().decode(encoding, "replace")


def _txt(cell: str) -> str:
    return html.unescape(re.sub(r"<.*?>", "", cell)).strip()


# ── 1) 국장 주식 (KRX KIND) ──
def fetch_kr_stocks() -> dict:
    raw = _get(KIND_URL, "euc-kr")
    out: dict[str, str] = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", raw, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 3:
            continue
        name, market, code = _txt(tds[0]), _txt(tds[1]), _txt(tds[2])
        if not name or not re.fullmatch(r"[0-9A-Z]{6}", code):
            continue
        if market == "코넥스":
            continue
        out[name] = code
    return out


# ── 2) 국장 ETF (네이버 금융) ──
def fetch_kr_etf() -> dict:
    raw = _get(NAVER_ETF_URL, "euc-kr")
    data = json.loads(raw)
    out: dict[str, str] = {}
    for it in data.get("result", {}).get("etfItemList", []):
        name, code = it.get("itemname"), it.get("itemcode")
        if name and re.fullmatch(r"[0-9A-Z]{6}", code or ""):
            out[name] = code
    return out


# ── 3) 미장 (NASDAQ Trader) ──
def _clean_us(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    for suf in (" Common Stock", " Common Shares", " Ordinary Shares",
                " American Depositary Shares", " Depositary Shares"):
        if name.endswith(suf):
            name = name[: -len(suf)]
    return name.strip(" -")


def fetch_us() -> dict:
    out: dict[str, str] = {}
    # nasdaqlisted: Symbol|Security Name|Market Category|Test Issue|...|ETF|...
    for line in _get(US_NASDAQ_URL).splitlines()[1:]:
        f = line.split("|")
        if len(f) < 8 or f[0].startswith("File Creation"):
            continue
        sym, name, test = f[0], f[1], f[3]
        if test != "N" or not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", sym):
            continue
        out[_clean_us(name)] = sym
    # otherlisted: ACT Symbol|Security Name|Exchange|CQS|ETF|Lot|Test Issue|NASDAQ
    for line in _get(US_OTHER_URL).splitlines()[1:]:
        f = line.split("|")
        if len(f) < 8 or f[0].startswith("File Creation"):
            continue
        sym, name, test = f[0], f[1], f[6]
        if test != "N" or not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", sym):
            continue
        out.setdefault(_clean_us(name), sym)
    return out


def _save(name: str, data: dict):
    path = os.path.join(DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=0)
    print(f"✔ {len(data):>5}개 → {name}")


def main():
    print("종목 목록 갱신 중...")
    try:
        _save("krx_stocks.json", fetch_kr_stocks())
    except Exception as e:
        print(f"  ✗ 국장 주식 실패: {e}")
    try:
        _save("kr_etf.json", fetch_kr_etf())
    except Exception as e:
        print(f"  ✗ 국장 ETF 실패: {e}")
    try:
        _save("us_stocks.json", fetch_us())
    except Exception as e:
        print(f"  ✗ 미장 실패: {e}")
    print("완료. (cli.py 에서 바로 한글/영문 검색 가능)")


if __name__ == "__main__":
    main()
