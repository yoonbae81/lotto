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
- [실행 방식 선택](#-실행-방식-선택)
- [Option A: 서버 (systemd 타이머)](#️-option-a-서버-systemd-타이머)
- [Option B: GitHub Actions](#️-option-b-github-actions)
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
- ✅ **두 가지 실행 방식** - 내 서버(systemd 타이머) 또는 GitHub Actions 중 선택
- ✅ **OCR 키패드 인식** - 랜덤 키패드 자동 입력 (Tesseract)
- ✅ **결제 금액 및 영수증 검증** - 구매 전 금액 확인 및 구매 후 최종 영수증 확인
- ✅ **원격 환경 대응** - 로그인 제출 재시도, 이동(goto) 재시도, 타임아웃 배율 조정
- ✅ **알림** - Discord 웹훅 (선택)

## 🚀 실행 방식 선택

같은 코드(`scripts/run.sh`)를 **어디에서 실행할지**만 다릅니다. 상황에 맞는 방식 **하나만** 선택하세요.

| | Option A: 서버 (systemd) | Option B: GitHub Actions |
|---|---|---|
| 실행 위치 | 내 Linux 서버/홈서버 (국내 IP) | GitHub 러너 (해외 데이터센터 IP) |
| 스케줄 | systemd 타이머 (매주 월요일 09:00 KST) | `cron: '0 0 * * 1'` (매주 월요일 09:00 KST) |
| 계정 정보 | 서버의 `.env` 파일 | GitHub Secrets / Variables |
| 필요한 것 | 상시 켜진 Linux 서버 | GitHub 계정 (서버 불필요) |
| 장점 | 국내 IP라 사이트 접속이 안정적 | 서버 관리 불필요 |
| 단점 | 서버 운영/관리 필요 | 해외 IP라 로그인 제출 무시, 응답 지연, 연결 끊김이 간헐적으로 발생할 수 있음 (재시도 로직으로 대부분 흡수) |

> [!WARNING]
> **두 방식을 동시에 켜지 마세요.** 같은 시각에 두 곳에서 실행되어 연금복권이 중복 구매되고 충전도 중복될 수 있습니다. 방식을 바꿀 때는 이전 방식을 먼저 끄세요 (아래 각 옵션의 "끄기" 참고).

---

## 🖥️ Option A: 서버 (systemd 타이머)

내 Linux 서버(EC2, 홈서버 등)에서 systemd 사용자 타이머로 매주 자동 실행합니다.

### 1. 설치

```bash
git clone https://github.com/yoonbae81/lotto.git
cd lotto
cd scripts && ./setup-env.sh && cd ..
```
Python 가상환경 생성, 의존성 설치, 브라우저 설치, `.env` 파일 자동 생성. Tesseract OCR은 별도 설치가 필요합니다.

```bash
sudo apt-get install tesseract-ocr     # Ubuntu/Debian
brew install tesseract                 # macOS
```

### 2. 환경 변수 설정

`.env` 파일을 편집해 계정 정보와 구매 설정을 입력합니다 ([환경 변수](#-환경-변수) 참고).

```bash
nano .env
chmod 600 .env
```

### 3. 수동 실행 (테스트)

```bash
source .venv/bin/activate

./src/balance.py               # 잔액만 조회 (충전/구매 없음)
./scripts/run.sh               # 전체 워크플로우 (실제 충전/구매 수행)
./scripts/run.sh --645         # 로또 6/45만 구매 (연금복권 스킵)
./scripts/run.sh --720         # 연금복권 720만 구매 (로또 스킵)
```

### 4. systemd 타이머 설치

```bash
cd scripts
./install-systemd.sh
```

서비스/타이머 파일 설치, 경로 자동 치환(`{{PROJECT_ROOT}}`), `loginctl enable-linger`, 타이머 활성화까지 수행합니다. 타이머는 `OnCalendar=Mon *-*-* 09:00:00 Asia/Seoul`입니다.

```bash
systemctl --user status lotto.timer       # 상태 확인
systemctl --user list-timers lotto.timer  # 다음 실행 시간 확인
journalctl --user -u lotto.service -f     # 로그 확인
systemctl --user start lotto.service      # 지금 바로 실행 (실제 구매 수행)
```

### 끄기 / 제거

```bash
systemctl --user disable --now lotto.timer     # 타이머 중지 (Option B로 옮길 때)
rm ~/.config/systemd/user/lotto.{service,timer}
systemctl --user daemon-reload
```

---

## ☁️ Option B: GitHub Actions

서버 없이 GitHub 러너에서 직접 실행합니다.

| 항목 | 내용 |
|------|------|
| 워크플로 | `.github/workflows/purchase.yml` (`Lotto Purchase (Run on GitHub)`) |
| 실행 시점 | 매주 월요일 09:00 KST (`cron: '0 0 * * 1'`, UTC 기준) 및 수동 실행 |
| 실행 환경 | `ubuntu-24.04`, Python 3.14, Playwright Chromium, Tesseract OCR |
| 사용 액션 | `actions/checkout@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` (Node 24) |
| 커밋 시 동작 | 없음 (`push` 트리거 없음, 스케줄과 수동 실행만) |

> [!NOTE]
> - GitHub 스케줄은 예약 시각보다 몇 분에서 수십 분 늦게 시작될 수 있음. cron을 바꾼 직후에는 반영에 시간이 걸려 해당 주기를 건너뛸 수 있음.
> - 공개 저장소는 60일 동안 저장소 활동이 없으면 스케줄이 자동 비활성화됨. 비활성화되면 Actions 탭에서 다시 활성화.
> - Fork한 저장소는 Actions가 기본 비활성화 상태이므로 Actions 탭에서 먼저 활성화 필요.

### 1. Fork 하기

이 저장소를 본인의 GitHub 계정으로 **Fork** 하고, Actions 탭에서 워크플로를 활성화합니다.

### 2. Secrets / Variables 등록

워크플로는 계정 정보는 **Secrets**, 구매 설정과 알림 주소는 **Variables**에서 읽어 환경변수로 주입합니다. 러너에서는 `.env`를 사용하지 않습니다.

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

#### 방법 1: 웹 UI

저장소 **Settings → Secrets and variables → Actions**

- **Secrets 탭** → `New repository secret` → `USER_ID`, `PASSWD`, `CHARGE_PIN` 등록
- **Variables 탭** → `New repository variable` → `AUTO_GAMES`, `MANUAL_NUMBERS`, `REPORTER_DISCORD_WEBHOOK` 등록

> Secret은 `secrets.*`, Variable은 `vars.*`로만 읽힙니다. 탭을 잘못 고르면 값이 비어 있는 채로 실행됩니다.

#### 방법 2: GitHub CLI (`gh`)

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

### 3. 실행 확인 및 수동 실행

- **자동 실행**: 매주 월요일 09:00 KST. 결과는 저장소 **Actions** 탭에서 확인
- **수동 실행**: Actions 탭 → `Lotto Purchase (Run on GitHub)` → `Run workflow`

```bash
gh workflow run purchase.yml -R "$REPO" --ref main
gh run list -R "$REPO" -w purchase.yml -L 5
gh run watch -R "$REPO"                          # 진행 상황
gh run view <run-id> -R "$REPO" --log-failed     # 실패 로그
```

> [!WARNING]
> 수동 실행도 **실제로 충전과 구매를 수행**합니다. 테스트 목적이라도 구매가능 금액이 10,000원 미만이면 충전이 일어납니다. 로또 6/45는 주간 구매 한도가 차면 구매하지 않고 종료합니다.

- **실패 시**: `failure-screenshots` 아티팩트에 로그인/이동 실패 화면이 3일간 보관됩니다.

### 4. 워크플로 환경변수 (선택 조정)

`purchase.yml`의 `env:`에서 조정합니다.

| 변수 | 워크플로 값 | 기본값 | 설명 |
|------|-------------|--------|------|
| `GLOBAL_TIMEOUT_MS` | `60000` | `10000` | 페이지 이동/대기 타임아웃 (ms) |
| `TIMEOUT_SCALE` | `3` | `1` | 소스의 모든 고정 타임아웃에 곱하는 배율 |
| `TZ` | `Asia/Seoul` | - | 러너 시간대 |
| `HEADLESS` | 미설정 (`true`) | `true` | 브라우저 헤드리스 여부 |

### 끄기

```bash
gh workflow disable purchase.yml -R "$REPO"    # 일시 중지 (재개는 enable)
```

---

## 📁 프로젝트 구조

```
lotto/
├── .github/workflows/
│   └── purchase.yml             # (Option B) 스케줄/수동 구매 워크플로
├── src/                          # Python 스크립트
│   ├── balance.py               # 잔액 조회
│   ├── charge.py                # 예치금 충전 (간편 충전)
│   ├── login.py                 # 로그인 모듈 (성공 판별/재시도/goto 재시도)
│   ├── lotto645.py              # 로또 6/45 구매
│   ├── pension720.py            # 연금복권 720 구매
│   └── tscale.py                # 타임아웃 배율 (TIMEOUT_SCALE)
├── scripts/
│   ├── run.sh                   # 메인 워크플로우 스크립트 (A/B 공통)
│   ├── setup-env.sh             # (Option A) 환경 설정 (venv, pip, 브라우저)
│   ├── install-systemd.sh       # (Option A) systemd 타이머 설치
│   ├── deploy.sh                # (Option A) 서버 배포
│   └── systemd/                 # (Option A) 서비스/타이머 정의
│       ├── lotto.service
│       └── lotto.timer          # 매주 월요일 09:00 KST
├── .env.example                  # (Option A) 환경 변수 예시
├── requirements.txt              # Python 의존성 (버전 미고정: 실행 시 최신 설치)
└── README.md
```

## 🔧 환경 변수

스크립트는 프로세스 환경변수를 우선 사용하고, 없으면 `.env`를 읽습니다 (`python-dotenv`는 기존 환경변수를 덮어쓰지 않음). Option A는 `.env`, Option B는 Secrets/Variables가 환경변수로 주입됩니다.

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

### .env 예시 (Option A)

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
메인 워크플로우 스크립트 (Option A/B 공통):
1. 로그인 및 세션 저장
2. 잔액 확인
3. 조건부 충전 (구매가능 10,000원 미만 시)
4. 연금복권 720 구매
5. 로또 6/45 구매

`--645`, `--720` 옵션으로 한쪽만 구매할 수 있습니다.

#### `setup-env.sh`
Option A 환경 설정: Python 가상환경, 의존성, Playwright 브라우저, `.env` 생성

#### `install-systemd.sh`
Option A systemd 타이머 설치: 서비스/타이머 파일 복사, 경로 치환, linger 활성화, 타이머 시작

## 🛠️ 기술 스택

- **Python** - Option B는 3.14, Option A는 3.10+ 권장
- **Playwright** - 브라우저 자동화
- **Tesseract OCR** - 키패드 숫자 인식
- **Pillow**, **python-dotenv**, **script-reporter**(알림)
- **systemd** (Option A) / **GitHub Actions** (Option B) - 스케줄링

## ⚠️ 주의사항

1. **한 가지 방식만 사용**: systemd 타이머와 GitHub Actions 스케줄을 동시에 켜면 중복 구매/충전 발생
2. **간편 충전 사용**: [간편충전] 기능 사용, [가상계좌 입금] 미지원
3. **충전 조건**: 구매가능 금액이 10,000원 미만일 때만 충전. 잔액 판독이 실패하면 불필요한 충전이 반복될 수 있으므로, 처음 몇 번은 로그의 `Balance Summary`를 실제 잔액과 대조 권장
4. **주간 구매 한도**: 로또 6/45는 동행복권 모바일 사이트 정책에 따른 주간 구매 한도를 초과하면 구매를 시도하지 않고 종료
5. **OCR 정확도**: 키패드 숫자 인식률 약 90-95%, 실패 시 재시도 또는 수동 확인 요망
6. **Option A는 Linux 전용**: systemd 타이머는 Linux 전용, macOS는 launchd 필요
7. **보안**: `.env` 커밋 금지 (.gitignore 포함). Option B는 계정 정보를 Secrets에만 저장
8. **테스트**: 실제 사용 전 `./src/balance.py`로 조회 테스트 권장

## 🐛 트러블슈팅

### 로그인이 계속 실패
- (Option B) Actions 로그의 `Still on login page; retrying submit` 여부 확인
- (Option B) 아티팩트 `failure-screenshots`의 화면 확인 (아이디/비밀번호 오류 문구, 보안 절차 여부)
- `TIMEOUT_SCALE`, `GLOBAL_TIMEOUT_MS`를 늘려 재시도. 러너에서 계속 불안정하면 Option A(국내 IP 서버) 고려

### 매번 충전됨
- 로그의 `Balance Summary`가 실제 잔액과 다른지 확인 (`deposit`이 0이고 `available`이 실제 값일 수 있음)
- 구매가능 금액이 `0원`으로 반복되면 `balance.py`의 선택자/대기 시간 점검

### OCR 인식 실패
```bash
# Tesseract 재설치 (macOS)
brew reinstall tesseract
# Ubuntu/Debian
sudo apt-get install --reinstall tesseract-ocr
```

### Playwright 브라우저 오류 (Option A)
```bash
.venv/bin/playwright install chromium
```

### 환경 변수 로드 안됨 (Option A)
```bash
ls -la .env        # 위치 확인
chmod 600 .env     # 권한 확인
```

### systemd 타이머 작동 안함 (Option A)
```bash
loginctl enable-linger $USER          # 로그아웃 후에도 실행
systemctl --user daemon-reload
systemctl --user restart lotto.timer
```

### GitHub 스케줄이 실행되지 않음 (Option B)
- Actions 탭에서 워크플로가 `disabled`인지 확인 (`gh workflow enable purchase.yml`)
- cron은 UTC 기준: 월요일 09:00 KST = `0 0 * * 1`
- 예약 직전에 cron을 바꾸면 그 주기를 건너뛸 수 있음
- 60일간 저장소 활동이 없으면 자동 비활성화됨
