# AGENTS.md - Codebase Guide for Agents

## Project Overview

**Project:** Lotto Auto Purchase System
**Purpose:** Automated lottery (Lotto 6/45 & Pension 720) purchasing via browser automation
**Language:** Python 3.9+
**Primary Tech:** Playwright (browser automation), Tesseract OCR (keypad recognition)

## Project Structure

```
lotto/
├── src/                    # Python automation scripts
│   ├── login.py            # Shared login module & session management
│   ├── balance.py          # Check account balance
│   ├── charge.py           # Charge account (with OCR keypad parsing)
│   ├── lotto645.py         # Lotto 6/45 purchase
│   └── pension720.py         # Pension 720+ purchase
├── scripts/                # Shell orchestration scripts
│   ├── run.sh              # Main workflow (login → balance → charge → purchase)
│   ├── setup-env.sh        # Environment setup (venv, deps, browser)
│   └── install-systemd.sh  # Systemd timer setup for auto-scheduling
├── .github/workflows/      # GitHub Actions CI
├── requirements.txt        # Python dependencies
└── .env.example           # Environment variable template
```

## Build/Install/Run Commands

### Environment Setup
```bash
# Initial setup (creates venv, installs deps, installs Playwright browser)
cd scripts && ./setup-env.sh
```

### Running Scripts
```bash
# Activate virtual environment
source .venv/bin/activate

# Run individual scripts
python src/login.py           # Login and save session
python src/balance.py         # Check balance
python src/charge.py 10000    # Charge 10,000 KRW
python src/pension720.py        # Buy Pension 720
python src/lotto645.py 3000   # Buy 3 games of Lotto 6/45 (auto mode)

# Run main workflow
bash scripts/run.sh           # Full workflow (login, balance, charge, buy)
bash scripts/run.sh --645     # Lotto 6/45 only
bash scripts/run.sh --720     # Pension 720 only
```

### Testing
```bash
# No formal test suite exists. Tests are manual runs:
python src/balance.py        # Verify balance retrieval works
python src/login.py           # Verify login works
```

### Playwright Browser
```bash
# Reinstall Playwright browser if needed
.venv/bin/playwright install chromium

# Install system dependencies (Linux)
sudo .venv/bin/playwright install-deps chromium
```

## Code Style Guidelines

### Import Order
1. Standard library imports
2. External packages (playwright, dotenv, etc.)
3. Local imports (from login import ...)
```python
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Page, Playwright
from login import login, SESSION_PATH
```

### Naming Conventions
- **Functions:** `snake_case` - `get_balance()`, `charge_deposit()`
- **Constants:** `UPPERCASE_SNAKE_CASE` - `SESSION_PATH`, `DEFAULT_USER_AGENT`, `GLOBAL_TIMEOUT`
- **Variables:** `snake_case` - `page`, `browser`, `context`
- **Classes:** (None in this codebase, but would use `PascalCase`)

### Type Hints
- Use `:` for parameters and `->` for return types
```python
def get_balance(page: Page) -> dict:
    def charge_deposit(page: Page, amount: int) -> bool:
```

### Environment Variables
- **File:** `.env` at project root
- **Loading:** Loaded once in `login.py` via `python-dotenv`, then imported
- **Access:** `os.environ.get('VAR_NAME', 'default_value')`
```python
USER_ID = environ.get('USER_ID')
PASSWD = environ.get('PASSWD')
HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'
```

### Error Handling & Debugging
- Always use try/except for Playwright operations
- Take screenshots on failure with timestamp in filename
```python
try:
    page.goto(url, timeout=GLOBAL_TIMEOUT)
except Exception as e:
    print(f"Navigation failed: {e}")
    page.screenshot(path=f"nav_failed_{int(time.time())}.png")
    raise e
```

### Playwright Patterns
- **Sync API:** Always use `from playwright.sync_api import Page, Playwright, sync_playwright`
- **Context:** Use `with sync_playwright() as playwright:`
- **Timeout:** Use `GLOBAL_TIMEOUT = 10000` (10 seconds) constant
- **Wait Strategies:**
  - `page.wait_for_selector(selector, state="visible", timeout=GLOBAL_TIMEOUT)`
  - `page.goto(url, wait_until="domcontentloaded")` (faster than default `load`)
  - `page.goto(url, wait_until="commit")` (for initial header/redirect catch)
- **Mobile Simulation:** Always use mobile user agent and viewport
```python
DEFAULT_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) ..."
DEFAULT_VIEWPORT = {"width": 393, "height": 852}
```
- **Session Persistence:** Save/load via storage_state
```python
context.storage_state(path=SESSION_PATH)  # Save
storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None  # Load
context = browser.new_context(storage_state=storage_state, ...)
```

- **PIN Entry Reliability:**
  - Avoid `page.touchscreen.tap` for security PINs as it may be too fast for the site's debouncing.
  - Use `page.mouse.click(x, y, delay=150)` to simulate a reliable hold-and-release tap.
  - Include `time.sleep(0.8)` between digit entries to ensure UI registration.

### Dialog/Alert Handling
- Set up dialog handler before any operations
- Handle "already handled" errors gracefully
```python
def setup_dialog_handler(page: Page):
    def handle_dialog(dialog):
        try:
            dialog.accept()
        except Exception as e:
            if "already handled" not in str(e).lower():
                print(f"Dialog error: {e}")
    if not getattr(page, "_dialog_handler_active", False):
        page.on("dialog", handle_dialog)
        setattr(page, "_dialog_handler_active", True)
```

### Login Module
- **Never** implement login separately in other scripts
- Import from `login.py`: `from login import login, is_logged_in, SESSION_PATH, ...`
- Check if already logged in before attempting login: `if not is_logged_in(page): login(page)`

### ScriptReporter
- Use for structured output and success/failure tracking
```python
from script_reporter import ScriptReporter
sr = ScriptReporter("Task Name")
sr.stage("STAGE_NAME")
try:
    # do work
    sr.success({"key": "value"})
except Exception:
    sr.fail(traceback.format_exc())
    sys.exit(1)
```

### Shebang
- All Python scripts must have: `#!/usr/bin/env python3`
- All shell scripts must be executable: `chmod +x scripts/run.sh`

### Docstrings
- Use Korean for user-facing descriptions (matches project language)
- Use English for implementation details
```python
def get_balance(page: Page) -> dict:
    """
    마이페이지에서 예치금 잔액과 구매가능 금액을 조회합니다.

    Returns:
        dict: {'deposit_balance': int, 'available_amount': int}
    """
```

### Selectors
- Use specific IDs when available: `#inpUserId`, `#btnLogin`
- Fallback to classes for mobile selectors: `.btn_blue.large.full`
- Use `page.locator().first` when multiple elements may exist
- Chain selectors: `a:has-text('로그인')`
- **Exact Text Match:** Use `xpath=//div[text()='1']` or `locator("text='1'")` instead of `has-text('1')` to avoid matching '10', '11', etc.

## Key Constants (from login.py)
- `SESSION_PATH = "/tmp/dhlotto_session.json"` - Session storage location
- `DEFAULT_USER_AGENT` - Mobile user agent string
- `DEFAULT_VIEWPORT = {"width": 393, "height": 852}` - Mobile viewport size
- `DEFAULT_HEADERS` - Mobile-specific HTTP headers
- `GLOBAL_TIMEOUT = 10000` - Default timeout in milliseconds

## Special Notes
- **OCR:** Tesseract used for keypad number recognition in `charge.py`
- **Mobile-First:** All automation targets mobile site (`m.dhlottery.co.kr`)
- **Lotto 6/45 Precautions:**
  - **Cart Counting:** Visible `.myNum-box` count is the most reliable. Auto games show `*` while Manual show numbers.
  - **Manual Entry:** Must click `"번호 선택하기"` and use `"초기화"` (`#btnInit`) before each game to prevent duplicate alerts.
  - **Weekly Limit:** Purchase limit (5,000 KRW/week) triggers `#popupLayerConfirm` or `#popupLayerAlert` with "구매한도" text.
  - **Verification:** Successful purchase receipt has container ID `#report`.
- **Sleeps:** Short sleeps (0.1-0.8s) used after clicks for animation handling
- **Korean Site:** Selectors and logic assume Korean lottery site structure
- **Session Reuse:** Login once, reuse session across scripts
- **No Tests:** This is a production automation script, no formal test suite
- **Headless Default:** HEADLESS=true by default, can be set to 'false' for debugging
