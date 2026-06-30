<div align="center">

# 📈 Toss Stock CLI

**토스증권 Open API 기반 터미널 주식 트레이딩 클라이언트**

국장 · 미장 시세 조회부터 매수 · 매도까지, 모든 기능을 터미널에서.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Toss Open API](https://img.shields.io/badge/Toss-Open%20API%20v1.1.5-0064FF)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

## ✨ 주요 기능

| | 기능 |
|---|---|
| 💰 **계좌 · 자산** | 보유주식(내 주식) · 매수가능금액 · 매매수수료 |
| 📊 **시세** | 현재가 · 호가 · 체결내역 · 캔들 · 상/하한가 · 종목정보 · 매수유의 |
| 🛒 **주문** | 매수 · 매도 · 정정 · 취소 · 미체결/체결 조회 · 판매가능수량 |
| 🌐 **시장정보** | 환율 · 국내/미국 장운영 캘린더 |
| 🔎 **종목 검색** | **국장 주식·ETF + 미장** 16,000여 종목을 한글/티커로 검색 |
| 📈 **터미널 차트** | 캔들 차트(빨강 상승/파랑 하락), 최대 120봉 |
| 🎨 **테마 · 모드** | 컬러 / 연한색 / **흑백(스텔스)** · 쉬움 / 어려움 모드 |
| 🔐 **보안** | Secret Key 런타임 입력(화면 비표시), 주문 전 확인 절차 |

---

## 🖥️ 미리보기

```
━━ 시세 ━━
삼성전자 (005930)  종가 68,875  -2,327 (-3.27%)  [40봉]
    72,922 │             │  ██│ │  │██││
    71,463 ││││███ │ │██│ │   ███│   ██████
    70,977 │██████████││██  │     ││ │   ││███
    70,004 ││ │     ││         │ │██│││ │
           └────────────────────────────────────────
            2026-05-21                    2026-06-29
```

> 🕵️ **흑백(스텔스) 테마** 를 켜면 색을 빼고 흐릿한 회색조로 그려져, 평범한 로그 출력처럼 보입니다.

---

## 🚀 빠른 시작

```bash
# 1. 의존성 설치
pip install httpx textual

# 2. 실행 — 실행 즉시 API Key / Secret Key 입력 프롬프트가 뜹니다
python cli.py

# (선택) API 키 없이 가상 데이터로 체험
python cli.py --mock
```

```text
🪪 API Key(client_id) 입력: tsck_live_...
🔑 Secret Key 입력: ********        ← 화면에 표시되지 않습니다
━━ 화면 설정 ━━
  테마 선택 [1]: 3   (회사용 흑백)
  모드 선택 [2]: 1   (쉬움)
● LIVE 모드 인증 성공
```

> **API 키 발급**: 토스증권 앱 → 오픈 API 사전 신청 → 승인 후 PC 웹([tossinvest.com](https://tossinvest.com))에서 발급

---

## 🔐 보안

> 💵 **실제 돈이 오가는 LIVE 트레이딩** 도구입니다. 보안을 최우선으로 설계했습니다.

- **API Key · Secret Key 모두 코드에 하드코딩하지 않습니다.** 실행 시 입력받으며,
  특히 **Secret Key 는 `getpass` 로 화면 비표시 · 메모리에만** 보관합니다. (명령 히스토리에도 남지 않음)
- 매번 입력이 번거로우면 환경변수로 주입할 수 있습니다 (이 경우 프롬프트 생략):
  ```bash
  # Windows (PowerShell)
  $env:TOSS_CLIENT_ID="..."; $env:TOSS_CLIENT_SECRET="..."; python cli.py
  # macOS / Linux
  TOSS_CLIENT_ID=... TOSS_CLIENT_SECRET=... python cli.py
  ```
- **모든 매수 · 매도 · 정정 · 취소는 전송 전 내용을 보여주고 `y/N` 확인**을 받습니다.
- 주문 시 코드/티커가 **실제 어떤 종목인지 API 로 재확인**해 보여주어 오주문을 막습니다.
- 국장 종목을 **장 시간 외**에 주문하면 사전 경고합니다.

---

## 📚 사용법

### CLI 메뉴 (`python cli.py`)

```
1) 계좌/자산   2) 시세   3) 주문   4) 시장정보   9) 설정   0) 종료
```

### 종목 검색 — 이름만 치면 됩니다

| 분류 | 종목 수 | 입력 예시 |
|---|---:|---|
| 🇰🇷 국장 주식 | ~2,600 | `삼성전자` `한화오션` `심텍` |
| 🇰🇷 국장 ETF | ~1,100 | `KODEX 200` `코덱스레버리지` `TIGER 미국S&P500` |
| 🇺🇸 미장 | ~12,000 | `애플` `엔비디아`(한글) · `AAPL` `QQQ` `SCHD`(티커) |

- 6자리 숫자 → 국장 코드 / 영문 → 미국 티커 / 한글·영문명 → 자동 변환
- 여러 종목이 검색되면 번호로 선택, 미국 주식 한글 별칭 내장(애플·엔비디아·테슬라 등)
- 목록 갱신: `python update_stocks.py` (국장 주식·ETF, 미장 자동 다운로드)

### 테마 · 모드 · 차트

- **테마**: `1` 컬러(기본) · `2` 연한색 · `3` 흑백(스텔스) — 언제든 `9) 설정` 에서 변경
- **모드**: `1` 쉬움(핵심 기능만) · `2` 어려움(전체 기능)
- **차트**: 시세 → `8) 📈 차트`, 봉 단위(일/분) · 개수(최대 120) 선택

### TUI 대시보드 (`python app.py`)

`1~4` 탭 전환 · `r` 새로고침 · `q` 종료 — 시세/포트폴리오/주문/주문내역을 시각화

---

## 🗂️ 프로젝트 구조

```
toss-stock/
├── cli.py             # cmd 인터랙티브 CLI (메인)
├── app.py             # Textual TUI 대시보드
├── toss_api.py        # 토스증권 API 클라이언트 (실제 20개 엔드포인트 + Mock)
├── stocks.py          # 종목명 → 코드/티커 검색 (국장 + 미장)
├── update_stocks.py   # 종목 목록 갱신 스크립트 (3종 자동 다운로드)
├── krx_stocks.json    # 국장 주식 데이터
├── kr_etf.json        # 국장 ETF 데이터
└── us_stocks.json     # 미장 주식/ETF 데이터
```

---

## 🔗 데이터 출처

- **시세 · 주문**: [토스증권 Open API](https://developers.tossinvest.com/docs) (OpenAPI 3.1.0 / v1.1.5)
- **국장 종목**: [한국거래소 KIND 상장법인목록](https://kind.krx.co.kr/corpgeneral/corpList.do)
- **국장 ETF**: 네이버 금융 ETF 목록
- **미장 종목**: [NASDAQ Trader Symbol Directory](https://www.nasdaqtrader.com/Trader.aspx?id=symboldirdefs)

---

## ⚠️ 면책 조항

본 프로젝트는 **토스증권 비공식** 클라이언트입니다. 실제 자산 거래가 발생하며,
사용에 따른 모든 투자 손익과 책임은 **사용자 본인**에게 있습니다.
코드는 "있는 그대로(AS IS)" 제공되며 어떠한 보증도 하지 않습니다. 투자에 유의하세요.

> 국내 주식 매매 수수료: **2026년 6월까지 무료** (이후 KRX 0.015%)

---

## 📄 라이선스

[MIT](./LICENSE) © 2026 TaeWoongYoun
