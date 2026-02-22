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
GLOBAL_TIMEOUT = 10000 # 10 seconds global timeout for better reliability

def save_session(context, path=SESSION_PATH):
    """
    Saves the current browser context state (cookies, local storage) to a file.
    """
    context.storage_state(path=path)
    print(f"Session saved to {path}")

def setup_dialog_handler(page: Page):
    """
    Sets up a robust handler to automatically accept any alerts/dialogs.
    Avoids 'already handled' errors if multiple handlers are registered.
    """
    def handle_dialog(dialog):
        try:
            # Check if dialog is already being handled to avoid errors
            dialog.accept()
        except Exception as e:
            # Ignore "already handled" errors which occur if multiple listeners are active
            if "already handled" in str(e).lower():
                pass
            else:
                print(f"Dialog handling error: {e}")
    
    # Mark the page so we don't attach the same handler multiple times
    if not getattr(page, "_dialog_handler_active", False):
        page.on("dialog", handle_dialog)
        setattr(page, "_dialog_handler_active", True)

def dismiss_popups(page: Page):
    """Dismiss common mobile popups that might block clicks."""
    try:
        # On mobile, popups often have specific close buttons
        # visible=true is a bit slow, so we use a faster selector first
        close_buttons = page.locator(".btn_close, .close, .btn_pop_close, button:has-text('닫기'), a:has-text('오늘 하루 보지 않기')")
        count = close_buttons.count()
        for i in range(count):
            try:
                btn = close_buttons.nth(i)
                if btn.is_visible(timeout=500):
                    btn.click(timeout=1000)
            except:
                pass
    except Exception:
        pass



def check_logged_in_elements(page: Page, timeout: int = 2000) -> bool:
    """Helper to check for visual indicators of being logged in."""
    try:
        # 1. Check for logout indicators (strongly indicates logged in)
        if page.locator("#logoutBtn, .btn_logout, .btn-logout, a:has-text('로그아웃')").first.is_visible(timeout=timeout):
            return True
            
        # 2. Check for login indicators (strongly indicates NOT logged in)
        if page.locator("#btnLogin, .btn_login, .btn-login, a:has-text('로그인')").first.is_visible(timeout=timeout):
            return False
            
        return False
    except Exception:
        return False


def is_logged_in(page: Page) -> bool:
    """
    Check if the user is currently logged in.
    This is a non-intrusive check.
    """
    try:
        # First check current page without navigation
        if check_logged_in_elements(page, timeout=1000):
            return True
        
        # If we are on a page that strongly indicates login/logout state, trust it
        if "/login" in page.url:
             return False
        if "/mypage" in page.url:
             return True

        # If not sure, go to a page that uniquely identifies login state
        if page.url == "about:blank" or "dhlottery.co.kr" not in page.url:
            print("Navigating to check session state...")
            # Use 'commit' to catch the initial headers/redirect
            response = page.goto("https://m.dhlottery.co.kr/login", timeout=GLOBAL_TIMEOUT, wait_until="commit")
            # If we were redirected away from login to main or mypage, we ARE logged in
            if "/login" not in page.url and ("main" in page.url or "mypage" in page.url):
                print(f"Redirected from login to {page.url} - session is active.")
                return True
        
        # Final visual check
        return check_logged_in_elements(page, timeout=2000)
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
    setup_dialog_handler(page)

    # 1. Quick check if already logged in
    if is_logged_in(page):
        print("Already logged in. Skipping login.")
        return

    print('Starting login process...')
    
    # 2. Go directly to login page if not already there
    target_url = "https://m.dhlottery.co.kr/login"
    if target_url not in page.url:
        print(f"Navigating to login page: {target_url}")
        try:
            # Use 'domcontentloaded' – we don't need all images/tracking to fill a login form
            page.goto(target_url, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation to login page failed: {e}")
            page.screenshot(path=f"login_nav_failed_{int(time.time())}.png")
            raise e
    
    # Ensure page is ready
    try:
        dismiss_popups(page)
        
        # Wait for form fields - use visible=True for reliability
        page.wait_for_selector("#inpUserId", state="visible", timeout=GLOBAL_TIMEOUT)
    except Exception as e:
        print(f"Login form not ready: {e}")
        page.screenshot(path=f"login_form_failed_{int(time.time())}.png")
        raise e
    
    # 3. Fill and submit login form
    try:
        print(f"Logging in as {USER_ID[:3]}***...")
        
        # Clear fields just in case
        page.locator("#inpUserId").fill("")
        page.locator("#inpUserId").fill(USER_ID)
        
        page.locator("#inpUserPswdEncn").fill("")
        page.locator("#inpUserPswdEncn").fill(PASSWD)
        
        # Click login button
        page.click("#btnLogin")
    except Exception as e:
        print(f"Form submission failed: {e}")
        screenshot_path = f"login_submit_failed_{int(time.time())}.png"
        page.screenshot(path=screenshot_path)
        
        # Final fallback check
        if check_logged_in_elements(page, timeout=3000):
            print("Detected login success despite submission error")
            return
        raise Exception(f"Login click failed: {e}")

    # 5. Wait for success indicator
    print("Verifying login...")
    try:
        # Wait up to 10s for login to finalize
        success = False
        start_t = time.time()
        while time.time() - start_t < 10:
            if check_logged_in_elements(page, timeout=500):
                success = True
                break
            # If we see an error message, stop early
            if page.get_by_text("아이디 또는 비밀번호가 일치하지 않습니다").is_visible(timeout=100):
                raise Exception("Invalid credentials.")
            time.sleep(0.5)
            
        if success:
            print('Login successful')
        else:
            # Check URL as fallback
            if "login" not in page.url and "dhlottery" in page.url:
                print(f"Login likely successful (Redirected to {page.url})")
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
        is_mobile=True,
        has_touch=True,
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

