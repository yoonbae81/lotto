# 🎰 Lotto Auto Purchase

동행복권 자동구매 시스템 - 로또 6/45 및 연금복권 720 자동화

> [!IMPORTANT]
> 동행복권 구매지원 도구이며, 자동구매 설정시 신중한 확인 필요
> **모든 구매 결과 및 예치금 사용 책임은 사용자 본인에게 있음**
>
> **복권 과몰입 및 중독 예방 제도 준수**
> 동행복권 제공 제도(구매 한도, 충전 제한, 이용 시간 등) 범위 내에서만 동작하도록 설계됨. 해당 제도를 우회하거나 무력화하는 기능 미포함.

## 📋 목차

- [기능](#-기능)
- [운영 방식](#-운영-방식-github-actions)
- [GitHub 설정 (Secrets / Variables)](#-github-설정-secrets--variables)
- [실행 확인 및 수동 실행](#-실행-확인-및-수동-실행)
- [로컬 실행 (테스트)](#-로컬-실행-테스트)
- [프로젝트 구조](#-프로젝트-구조)
- [환경 변수](#-환경-변수)
- [스크립트 설명](#-스크립트-설명)
- [주의사항](#-주의사항)
- [트러블슈팅](#-트러블슈팅)

## ✨ 기능

### 자동화된 구매 워크플로우
1. **로그인** - 세션 저장 후 이후 단계에서 재사용
2. **잔액 확인** - 구매가능 금액 조회 (화면 값이 채워질 때까지 대기)
3. **조건부 충전** - 구매가능 금액이 10,000원 미만일 때만 간편충전 10,000원
4. **연금복권 720 구매** - 자동 구매 (5,000원)
5. **로또 6/45 구매** - 자동/수동 번호 선택 구매 (최대 5게임)
6. **구매 한도 감지** - 주간 구매 한도 도달 시 자동 중단 및 알림

### 주요 기능
- ✅ **완전 자동화** - Playwright 기반 브라우저 자동화
- ✅ **GitHub Actions 스케줄 실행** - 서버 없이 매주 월요일 09:00 (KST) 자동 실행
- ✅ **OCR 키패드 인식** - 랜덤 키패드 자동 입력 (Tesseract)
- ✅ **결제 금액 및 영수증 검증** - 구매 전 금액 확인 및 구매 후 최종 영수증 확인
- ✅ **원격 환경 대응** - 로그인 제출 재시도, 이동(goto) 재시도, 타임아웃 배율 조정
- ✅ **실패 진단** - 실패 시 화면 캡처를 Actions 아티팩트로 보관
- ✅ **알림** - Discord 웹훅 (선택)

## ☁️ 운영 방식 (GitHub Actions)

이 프로젝트는 **GitHub Actions 러너에서 직접 실행**합니다. 별도 서버, systemd 타이머, 배포 워크플로는 사용하지 않습니다.

| 항목 | 내용 |
|------|------|
| 워크플로 | `.github/workflows/purchase.yml` (`Lotto Purchase (Run on GitHub)`) |
| 실행 시점 | 매주 월요일 09:00 KST (`cron: '0 0 * * 1'`, UTC 기준) 및 수동 실행 |
| 실행 환경 | `ubuntu-24.04`, Python 3.14, Playwright Chromium, Tesseract OCR |
| 사용 액션 | `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` (Node 24) |
| 커밋 시 동작 | 없음 (`push` 트리거 없음, 스케줄과 수동 실행만) |
| 실행 스크립트 | `scripts/run.sh` |

> [!NOTE]
> - GitHub 스케줄은 예약 시각보다 몇 분에서 수십 분 늦게 시작될 수 있음. cron을 바꾼 직후에는 반영에 시간이 걸려 해당 주기를 건너뛸 수 있음.
> - 공개 저장소는 60일 동안 저장소 활동이 없으면 스케줄이 자동 비활성화됨. 비활성화되면 Actions 탭에서 다시 활성화.
> - Fork한 저장소는 Actions가 기본 비활성화 상태이므로 Actions 탭에서 먼저 활성화 필요.

## 🔐 GitHub 설정 (Secrets / Variables)

워크플로는 계정 정보는 **Secrets**, 구매 설정과 알림 주소는 **Variables**에서 읽어 환경변수로 주입합니다. `.env` 파일은 러너에서 사용하지 않습니다.

### 등록 항목

| 종류 | 이름 | 필수 | 설명 | 예시 |
|------|------|------|------|------|
| Secret | `USER_ID` | ✅ | 동행복권 아이디 | `your_id` |
| Secret | `PASSWD` | ✅ | 동행복권 비밀번호 | `your_password` |
| Secret | `CHARGE_PIN` | ✅ | 간편충전 PIN 6자리 | `123456` |
| Variable | `AUTO_GAMES` | 선택 | 로또 6/45 자동 게임 수 (0~5) | `2` |
| Variable | `MANUAL_NUMBERS` | 선택 | 로또 6/45 수동 번호 (JSON, 게임당 6개) | `[[1,2,3,4,5,6],[7,8,9,10,11,12]]` |
| Variable | `REPORTER_DISCORD_WEBHOOK` | 선택 | Discord 웹훅 주소 (알림용) | `https://discord.com/api/webhooks/...` |

- `AUTO_GAMES`와 `MANUAL_NUMBERS`를 합쳐 **최대 5게임**까지 구매됩니다. 미설정 시 기본값(`0`, `[]`)이 적용됩니다.
- 웹훅 주소는 노출되면 누구나 해당 채널에 글을 올릴 수 있습니다. 저장소가 공개이거나 협업자가 많다면 Variable 대신 **Secret**으로 등록하고 `purchase.yml`의 `vars.REPORTER_DISCORD_WEBHOOK`를 `secrets.REPORTER_DISCORD_WEBHOOK`로 바꾸세요.

### 방법 1: 웹 UI

저장소 **Settings → Secrets and variables → Actions**

- **Secrets 탭** → `New repository secret` → `USER_ID`, `PASSWD`, `CHARGE_PIN` 등록
- **Variables 탭** → `New repository variable` → `AUTO_GAMES`, `MANUAL_NUMBERS`, `REPORTER_DISCORD_WEBHOOK` 등록

> Secret은 `secrets.*`, Variable은 `vars.*`로만 읽힙니다. 탭을 잘못 고르면 값이 비어 있는 채로 실행됩니다.

### 방법 2: GitHub CLI (`gh`)

```bash
REPO=OWNER/lotto        # 본인 저장소

# Secrets (값은 표준입력으로 전달하면 셸 기록에 남지 않음)
printf '%s' 'your_id'       | gh secret set USER_ID    -R "$REPO"
printf '%s' 'your_password' | gh secret set PASSWD     -R "$REPO"
printf '%s' '123456'        | gh secret set CHARGE_PIN -R "$REPO"

# Variables
gh variable set AUTO_GAMES     -R "$REPO" --body '2'
gh variable set MANUAL_NUMBERS -R "$REPO" --body '[[1,2,3,4,5,6],[7,8,9,10,11,12]]'
gh variable set REPORTER_DISCORD_WEBHOOK -R "$REPO" --body 'https://discord.com/api/webhooks/...'

# 확인 (Secret 값은 조회되지 않고 이름만 표시)
gh secret list   -R "$REPO"
gh variable list -R "$REPO"
```

이미 `.env`가 있다면 Secret 3개는 파일에서 바로 읽어 등록할 수 있습니다.

```bash
grep -E '^(USER_ID|PASSWD|CHARGE_PIN)=' .env > .secrets.env
gh secret set -f .secrets.env -R "$REPO"
rm .secrets.env
```

### 워크플로 환경변수 (선택 조정)

`purchase.yml`의 `env:`에서 조정합니다.

| 변수 | 워크플로 값 | 기본값 | 설명 |
|------|-------------|--------|------|
| `GLOBAL_TIMEOUT_MS` | `60000` | `10000` | 페이지 이동/대기 타임아웃 (ms) |
| `TIMEOUT_SCALE` | `3` | `1` | 소스의 모든 고정 타임아웃에 곱하는 배율 |
| `TZ` | `Asia/Seoul` | - | 러너 시간대 |
| `HEADLESS` | 미설정 (`true`) | `true` | 브라우저 헤드리스 여부 |

## 🔎 실행 확인 및 수동 실행

- **자동 실행**: 매주 월요일 09:00 KST. 결과는 저장소 **Actions** 탭에서 확인
- **수동 실행**: Actions 탭 → `Lotto Purchase (Run on GitHub)` → `Run workflow`

```bash
gh workflow run purchase.yml -R "$REPO" --ref main
gh run list -R "$REPO" -w purchase.yml -L 5
gh run watch -R "$REPO"          # 진행 상황
gh run view <run-id> -R "$REPO" --log-failed   # 실패 로그
```

> [!WARNING]
> 수동 실행도 **실제로 충전과 구매를 수행**합니다. 테스트 목적이라도 잔액이 10,000원 미만이면 충전이 일어납니다. 로또 6/45는 주간 구매 한도가 차면 구매하지 않고 종료합니다.

- **실패 시**: `failure-screenshots` 아티팩트에 로그인/이동 실패 화면이 3일간 보관됩니다.
- **일시 중지**: `gh workflow disable purchase.yml -R "$REPO"` / 재개는 `enable`

## 💻 로컬 실행 (테스트)

동행복권은 해외 IP에서 접속이 불안정할 수 있어, 러너에서 문제가 있으면 로컬(국내 IP)에서 같은 스크립트를 실행해 원인을 구분할 수 있습니다.

```bash
git clone https://github.com/yoonbae81/lotto.git && cd lotto
cp .env.example .env          # 값 입력 (커밋 금지)
cd scripts && ./setup-env.sh && cd ..
source .venv/bin/activate

./src/balance.py               # 잔액만 조회 (구매/충전 없음)
./scripts/run.sh               # 전체 워크플로우 (실제 충전/구매 수행)
./scripts/run.sh --645         # 로또 6/45만
./scripts/run.sh --720         # 연금복권 720만
```

로컬 실행에는 Tesseract OCR이 필요합니다 (`brew install tesseract` / `sudo apt-get install tesseract-ocr`).

> [!NOTE]
> `scripts/install-systemd.sh`, `scripts/systemd/`, `scripts/deploy.sh`는 서버 상시 운영을 위한 **레거시 스크립트**입니다. 현재 운영에서는 사용하지 않으며, 서버 방식으로 되돌릴 때만 참고하세요.

## 📁 프로젝트 구조

```
lotto/
├── .github/workflows/
│   └── purchase.yml             # 스케줄/수동 구매 워크플로 (Actions)
├── src/                          # Python 스크립트
│   ├── balance.py               # 잔액 조회
│   ├── charge.py                # 예치금 충전 (간편 충전)
│   ├── login.py                 # 로그인 모듈 (성공 판별/재시도/goto 재시도)
│   ├── lotto645.py              # 로또 6/45 구매
│   ├── pension720.py            # 연금복권 720 구매
│   └── tscale.py                # 타임아웃 배율 (TIMEOUT_SCALE)
├── scripts/
│   ├── run.sh                   # 메인 워크플로우 스크립트
│   ├── setup-env.sh             # 로컬 환경 설정 (venv, pip, 브라우저)
│   ├── deploy.sh                # (레거시) 서버 배포
│   ├── install-systemd.sh       # (레거시) Systemd 타이머 설치
│   └── systemd/                 # (레거시) 서비스/타이머 정의
├── .env.example                  # 로컬 실행용 환경 변수 예시
├── requirements.txt              # Python 의존성 (버전 미고정: 실행 시 최신 설치)
└── README.md
```

## 🔧 환경 변수

스크립트는 프로세스 환경변수를 우선 사용하고, 없으면 `.env`를 읽습니다 (`python-dotenv`는 기존 환경변수를 덮어쓰지 않음). GitHub Actions에서는 Secrets/Variables가 환경변수로 주입됩니다.

### 필수

| 변수 | 설명 |
|------|------|
| `USER_ID` | 동행복권 아이디 |
| `PASSWD` | 동행복권 비밀번호 |
| `CHARGE_PIN` | 간편충전 PIN 6자리 |

### 선택

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `AUTO_GAMES` | 로또 6/45 자동 게임 수 | `0` |
| `MANUAL_NUMBERS` | 로또 6/45 수동 번호 (JSON) | `[]` |
| `REPORTER_DISCORD_WEBHOOK` | Discord 알림 웹훅 | (없음) |
| `GLOBAL_TIMEOUT_MS` | 페이지 이동/대기 타임아웃 (ms) | `10000` |
| `TIMEOUT_SCALE` | 고정 타임아웃 배율 | `1` |
| `HEADLESS` | 헤드리스 실행 여부 | `true` |
| `TESSERACT_PATH` | Tesseract 실행 파일 경로 | 자동 탐색 |

### .env 예시 (로컬 실행용)

```env
USER_ID=myid
PASSWD=mypassword
CHARGE_PIN=123456

AUTO_GAMES=2
MANUAL_NUMBERS=[[1,2,3,4,5,6],[7,8,9,10,11,12]]

# 알림 (선택)
# REPORTER_DISCORD_WEBHOOK=https://discord.com/api/webhooks/your_webhook_url
```

## 📜 스크립트 설명

### Python 스크립트 (`src/`)

#### `balance.py`
- 예치금 잔액 및 구매가능 금액 조회
- 화면 금액은 페이지 로딩 후 JS로 채워지므로, 0이 아닌 값이 나타날 때까지 최대 20초 대기하고 끝까지 0이면 새로고침 후 한 번 더 확인
- 반환값: `{'deposit_balance': int, 'available_amount': int}`

#### `charge.py`
- 간편충전 기능 (가상계좌 입금 아님)
- OCR 활용 랜덤 키패드 자동 인식, 지연 클릭을 통한 PIN 입력 신뢰성 확보

#### `login.py`
- 공통 로그인 모듈 (타 스크립트 import 사용)
- 로그인 성공 판별: 로그아웃 요소 또는 `/login` 이탈(30초 대기), 제출이 무시되면 최대 2회 재시도
- 이미 로그인된 세션이면 `/login`이 메인으로 리다이렉트되므로 로그인 생략
- `page.goto` 네트워크 오류(`ERR_*`, Timeout) 시 최대 3회 재시도

#### `lotto645.py`
- 로또 6/45 구매
- 자동/수동 번호 선택 및 장바구니 관리 (최대 5게임)
- 주간 구매 한도 및 예치금 부족 감지, 최종 구매 결과 검증

#### `pension720.py`
- 연금복권 720 구매
- 임의 번호 모든 조(組) 자동 선택, 고정 금액 5,000원, 결제 금액 검증

#### `tscale.py`
- `TIMEOUT_SCALE` 환경변수로 소스의 모든 고정 타임아웃(ms)을 배율 조정

### Shell 스크립트 (`scripts/`)

#### `run.sh`
메인 워크플로우 스크립트:
1. 로그인 및 세션 저장
2. 잔액 확인
3. 조건부 충전 (구매가능 10,000원 미만 시)
4. 연금복권 720 구매
5. 로또 6/45 구매

`--645`, `--720` 옵션으로 한쪽만 구매할 수 있습니다.

#### `setup-env.sh`
로컬 환경 설정: Python 가상환경, 의존성, Playwright 브라우저, `.env` 생성

## 🛠️ 기술 스택

- **Python 3.14** (Actions), 로컬은 3.10+ 권장
- **Playwright** - 브라우저 자동화
- **Tesseract OCR** - 키패드 숫자 인식
- **Pillow**, **python-dotenv**, **script-reporter**(알림)
- **GitHub Actions** - 스케줄 실행

## ⚠️ 주의사항

1. **간편 충전 사용**: [간편충전] 기능 사용, [가상계좌 입금] 미지원
2. **충전 조건**: 구매가능 금액이 10,000원 미만일 때만 충전. 잔액 판독이 실패하면 불필요한 충전이 반복될 수 있으므로, 러너 실행 결과의 `Balance Summary` 로그를 처음 몇 번은 확인 권장
3. **주간 구매 한도**: 로또 6/45는 동행복권 모바일 사이트 정책에 따른 주간 구매 한도를 초과하면 구매를 시도하지 않고 종료
4. **OCR 정확도**: 키패드 숫자 인식률 약 90-95%, 실패 시 재시도 또는 수동 확인 요망
5. **해외 IP 접속**: GitHub 러너는 해외 데이터센터 IP라 로그인 제출 무시, 응답 지연, 연결 끊김이 간헐적으로 발생할 수 있음 (재시도 로직으로 대부분 흡수)
6. **보안**: `.env` 커밋 금지 (.gitignore 포함). 계정 정보는 Secrets에만 저장
7. **테스트**: 실제 사용 전 로컬에서 `balance.py`로 조회 테스트 권장

## 🐛 트러블슈팅

### 로그인이 계속 실패
- Actions 로그의 `Still on login page; retrying submit` 여부 확인
- 아티팩트 `failure-screenshots`의 화면 확인 (아이디/비밀번호 오류 문구, 보안 절차 여부)
- `TIMEOUT_SCALE`, `GLOBAL_TIMEOUT_MS`를 더 늘려 재시도

### 매번 충전됨
- 로그의 `Balance Summary`가 실제 잔액과 다른지 확인 (`deposit`이 0이고 `available`이 실제 값일 수 있음)
- 구매가능 금액이 `0원`으로 반복되면 `balance.py`의 선택자/대기 시간 점검

### OCR 인식 실패
```bash
# 로컬 재설치 (macOS)
brew reinstall tesseract
# Ubuntu/Debian
sudo apt-get install --reinstall tesseract-ocr
```

### Playwright 브라우저 오류 (로컬)
```bash
.venv/bin/playwright install chromium
```

### 스케줄이 실행되지 않음
- Actions 탭에서 워크플로가 `disabled`인지 확인 (`gh workflow enable purchase.yml`)
- cron은 UTC 기준: 월요일 09:00 KST = `0 0 * * 1`
- 예약 직전에 cron을 바꾸면 그 주기를 건너뛸 수 있음
- 60일간 저장소 활동이 없으면 자동 비활성화됨
