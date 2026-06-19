# 토스증권 TUI 클라이언트

터미널에서 토스증권 오픈 API를 바로 사용할 수 있는 TUI(Terminal UI) 앱입니다.
API 키 없이도 **Mock 모드**로 바로 실행 가능합니다.

## 실행 방법

### 1. 의존성 설치
```bash
pip install textual httpx
```

### 2. 실행

**Mock 모드** (API 키 없이 바로 실행)
```bash
python app.py
```

**Live 모드** (토스증권 오픈 API 키 발급 후)
```bash
TOSS_CLIENT_ID=your_id TOSS_CLIENT_SECRET=your_secret python app.py
```

## API 키 발급 방법

1. 토스증권 앱 → 오픈 API 사전 신청
2. 승인 후 PC 웹(tossinvest.com)에서 API 키 발급
3. 공식 문서: https://developers.tossinvest.com/docs

## 주요 기능

| 탭 | 단축키 | 기능 |
|----|--------|------|
| 시세 | `1` | 실시간 주가, KOSPI 요약, 상승/하락 1위 |
| 포트폴리오 | `2` | 잔고, 평가금액, 손익률 |
| 주문 | `3` | 차트 + 매수/매도 주문 실행 |
| 주문내역 | `4` | 체결/대기 주문 이력 + 로그 |

## 키보드 단축키

- `1~4` — 탭 전환
- `r` — 새로고침
- `q` — 종료

## 파일 구조

```
toss-tui/
├── app.py        # TUI 메인 앱 (Textual 기반)
└── toss_api.py   # 토스증권 API 클라이언트 (Mock 포함)
```

## 참고

- 국내 주식 매매 수수료: **2026년 6월까지 무료** (이후 KRX 0.015%)
- 현재 사전 신청자 대상 순차 개방 중 (2026.06 기준)
