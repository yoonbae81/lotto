#!/usr/bin/env python3
import os
import time
import re
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Page, Playwright
import sys
import traceback
from script_reporter import ScriptReporter

# Robustly match .env file
def load_environment():
    """
    .env 파일을 찾아 로드합니다.
    우선순위:
    1. src/ 상위 디렉토리 (프로젝트 루트)
    2. 현재 작업 디렉토리
    """
    # 1. Check project root (relative to this file)
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / '.env'
    
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        return

    # 2. Check current working directory
    cwd_env = Path.cwd() / '.env'
    if cwd_env.exists():
        load_dotenv(dotenv_path=cwd_env)
        return
        
    # 3. Last fallback: try default load_dotenv (searches up tree)
    load_dotenv()

load_environment()

USER_ID = environ.get('USER_ID')
PASSWD = environ.get('PASSWD')

# Constants
SESSION_PATH = "/tmp/dhlotto_session.json"
DEFAULT_USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1"
DEFAULT_VIEWPORT = {"width": 393, "height": 852}
DEFAULT_HEADERS = {
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-CH-UA-Mobile": "?1",
    "Sec-CH-UA-Platform": '"iOS"'
}
GLOBAL_TIMEOUT = 5000 # 5 seconds global timeout

def save_session(context, path=SESSION_PATH):
    """
    Saves the current browser context state (cookies, local storage) to a file.
    """
    context.storage_state(path=path)
    print(f"Session saved to {path}")

def dismiss_popups(page: Page):
    """Dismiss common mobile popups that might block clicks."""
    try:
        # On mobile, popups often have specific close buttons
        close_buttons = page.locator(".btn_close, .close, button:has-text('닫기'), a:has-text('오늘 하루 보지 않기')").locator("visible=true")
        for i in range(close_buttons.count()):
            try:
                close_buttons.nth(i).click(timeout=1000)
            except:
                pass
    except Exception:
        pass



def check_logged_in_elements(page: Page, timeout: int = 2000) -> bool:
    """Helper to check for visual indicators of being logged in."""
    try:
        # 1. Check for logout indicators (strongly indicates logged in)
        if page.locator("#logoutBtn, .btn_logout, .btn-logout").first.is_visible(timeout=timeout):
            return True
            
        if page.get_by_text("로그아웃", exact=False).first.is_visible(timeout=timeout):
            return True

        # 2. Check for login indicators (strongly indicates NOT logged in)
        # We check both the text and the common login link classes
        if page.get_by_role("link", name=re.compile("로그인")).first.is_visible(timeout=timeout):
            return False
        
        if page.locator(".btn_login, .btn-login, #btnLogin").first.is_visible(timeout=timeout):
            return False
            
        # 3. Fallback: If we don't see login but see mypage (less reliable but okay as secondary)
        # Note: on dhlottery, 'MY' link is visible even when logged out, so we skip general href check
        
        return False
    except Exception:
        return False


def is_logged_in(page: Page) -> bool:
    """
    Check if the user is currently logged in.
    This is a non-intrusive check.
    """
    try:
        if check_logged_in_elements(page, timeout=2000):
            return True
        
        # If we are on the login page itself, we are likely NOT logged in
        if "/login" in page.url or "method=login" in page.url:
             return False

        # Try to navigate or check current page for identity
        if page.url == "about:blank" or "dhlottery.co.kr" not in page.url:
            # Use 'commit' for speed
            print("Navigating directly to login page for session check...")
            page.goto("https://m.dhlottery.co.kr/login", timeout=GLOBAL_TIMEOUT, wait_until="commit")
        
        if check_logged_in_elements(page, timeout=3000):
            return True
        
        return False
    except Exception:
        return False


def login(page: Page) -> None:
    """
    동행복권 사이트에 로그인합니다.
    이미 로그인되어 있는 경우를 체크하고, 알림창(alert)을 자동으로 처리합니다.
    """
    if not USER_ID or not PASSWD:
        raise ValueError("USER_ID or PASSWD not found in environment variables.")
    
    # Setup alert handler to automatically accept any alerts
    page.on("dialog", lambda dialog: dialog.accept())

    # 1. Quick check if already logged in (now returns False on mobile site)
    if is_logged_in(page):
        print("Already logged in. Skipping login process.")
        return

    print('Starting login process...')
    
    # 2. Go directly to login page to establish session
    print("Navigating directly to login page...")
    target_url = "https://m.dhlottery.co.kr/login"
    try:
        page.goto(target_url, timeout=GLOBAL_TIMEOUT, wait_until="load")
        print(f"Current URL: {page.url}")
        
        # New: Dismiss any popups that might block the login form
        dismiss_popups(page)
        
        print(f"Current URL (login page): {page.url}")
        # Now wait for the form to be ready - wait for visible inputs
        print("Waiting for login form fields to appear (visible)...")
        page.wait_for_selector("#inpUserId", state="visible", timeout=GLOBAL_TIMEOUT)
    except Exception as e:
        print(f"Navigation or selector wait failed: {e}")
        # Capture state on failure
        page.screenshot(path=f"login_navigation_failed_{int(time.time())}.png")
        raise e
    
    # 3. Fill login form
    try:
        print(f"Filling login form at {page.url}...")
        
        # Mobile specific input IDs
        id_selector = "#inpUserId"
        pw_selector = "#inpUserPswdEncn"
        
        print(f"Entering User ID: {USER_ID[:3]}***")
        page.locator(id_selector).fill(USER_ID)
        
        print("Entering Password: ***")
        page.locator(pw_selector).fill(PASSWD)
        
        print("Clicking login button (#btnLogin)...")
        page.click("#btnLogin")
    except Exception as e:
        # Debugging: Capture state on failure
        print(f"Login process interrupted: {e}")
        screenshot_path = f"login_failed_{int(time.time())}.png"
        try:
            page.screenshot(path=screenshot_path)
            print(f"Saved failure screenshot to {screenshot_path}")
        except:
            pass
        
        # If we can't find the input, maybe we ARE logged in but visibility check failed
        if check_logged_in_elements(page, timeout=5000) or "mypage" in page.url:
            print("Already logged in (detected after error)")
            return
        raise Exception(f"Login failed: {e}")

    # 5. Wait for navigation and verify login
    try:
        print("Waiting for login completion...")
        # Simple wait for logout button presence
        start_time = time.time()
        while time.time() - start_time < 15:
            if check_logged_in_elements(page, timeout=1000):
                print('Logged in successfully')
                break
            time.sleep(0.5)
        else:
             raise TimeoutError("Login verification timed out")

    except Exception:
        print("Login verification timed out. Checking content...")
        if check_logged_in_elements(page, timeout=2000):
             print('Logged in successfully (detected via check helper)')
        else:
             content = page.content()
             if "아이디 또는 비밀번호가 일치하지 않습니다" in content:
                 raise Exception("Login failed: Invalid ID or password.")
             else:
                 if "/login" in page.url:
                      raise Exception(f"Login failed: Still on login page ({page.url})")
                 print(f"Assuming login might have worked (URL: {page.url})")

    # Give a bit more time for session cookies to be stable
    time.sleep(2)
    
    # Synchronize session with the game subdomain if needed
    try:
        print("Synchronizing session with game subdomains...")
        sync_url = "https://el.dhlottery.co.kr/common_mobile/do_sso.jsp"
        page.goto(sync_url, timeout=GLOBAL_TIMEOUT, wait_until="commit")
        print("Session synchronization complete.")
    except Exception as e:
        print(f"Subdomain sync warning: {e}")
    

def main():
    """
    Standalone login script that saves the session for other scripts to use.
    """
    from playwright.sync_api import sync_playwright
    sr = ScriptReporter("Login Session")
    
    with sync_playwright() as playwright:
        try:
            print("Launching browser for initial login...")
            HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'
            browser = playwright.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 500)
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport=DEFAULT_VIEWPORT,
                extra_http_headers=DEFAULT_HEADERS
            )
            page = context.new_page()
            
            sr.stage("LOGIN")
            login(page)
            
            sr.stage("SAVE_SESSION")
            save_session(context)
            
            print("Login successful and session persisted.")
            sr.success({"session_path": SESSION_PATH})
            
            context.close()
            browser.close()
        except Exception:
            sr.fail(traceback.format_exc())
            sys.exit(1)

if __name__ == "__main__":
    main()

