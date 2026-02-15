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
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_VIEWPORT = {"width": 1920, "height": 1080}
DEFAULT_HEADERS = {
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"Windows"'
}

def save_session(context, path=SESSION_PATH):
    """
    Saves the current browser context state (cookies, local storage) to a file.
    """
    context.storage_state(path=path)
    print(f"Session saved to {path}")



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
        # If we are on mobile site, we consider ourselves "not logged in (for desktop requirements)"
        # to trigger the login() flow which handles mobile-to-desktop transition
        if "m.dhlottery.co.kr" in page.url:
            return False

        if check_logged_in_elements(page, timeout=2000):
            return True
        
        # If we are on the login page itself, we are likely NOT logged in
        if "/login" in page.url or "method=login" in page.url:
             return False

        # Try to navigate to a page that requires login and see if it redirects
        if page.url == "about:blank" or "dhlottery.co.kr" not in page.url or "common.do?method=main" not in page.url:
            # Use 'commit' to bypass slow scripts during the identity check
            page.goto("https://www.dhlottery.co.kr/common.do?method=main", timeout=15000, wait_until="commit")
        
        if check_logged_in_elements(page, timeout=5000):
            return True
        
        # Additional check: if login link is visible, we are definitely NOT logged in
        if page.get_by_role("link", name=re.compile("로그인")).first.is_visible(timeout=2000):
            return False
            
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
    
    # 2. Go to login page
    print("Navigating to login page...")
    try:
        # Use wait_until="commit" to return immediately after navigation is accepted,
        # then we wait for the specific selector we need. This bypasses slow scripts/resources.
        page.goto("https://www.dhlottery.co.kr/login", timeout=30000, wait_until="commit")
        
        # Now wait for the form to be ready
        print("Waiting for login form to appear...")
        page.wait_for_selector("#inpUserId", timeout=20000)
    except Exception as e:
        print(f"Initial navigation or selector wait failed: {e}")
        # Take a screenshot to see what's wrong
        screenshot_path = f"login_nav_failed_{int(time.time())}.png"
        try:
            page.screenshot(path=screenshot_path)
            print(f"Saved navigation failure screenshot to {screenshot_path}")
        except:
            pass
        
        # If we are on mobile site, we can try to proceed
        if "m.dhlottery.co.kr" in page.url:
            print("Detected mobile site during navigation. Proceeding to mobile handling...")
        else:
             # If it's a real timeout and we're not on the right page, re-raise if not logged in
             if not check_logged_in_elements(page, timeout=3000):
                 raise e
    
    # Check for persistent mobile redirection
    if "m.dhlottery.co.kr" in page.url:
        print(f"Warning: Still redirected to mobile site: {page.url}")
    # 3. Check if we were redirected away from login (means already logged in)
    if "/login" not in page.url and "method=login" not in page.url:
        if check_logged_in_elements(page, timeout=5000):
            # If we are on desktop and logged in, we are good
            if "m.dhlottery.co.kr" not in page.url:
                print("Already logged in (redirected from login page)")
                return
            else:
                print("Logged in on mobile site. Attempting to switch to desktop...")
                page.goto("https://www.dhlottery.co.kr/common.do?method=main", timeout=10000)
                if "m.dhlottery.co.kr" not in page.url:
                    return

    # 4. Fill login form
    try:
        print(f"Checking login form at {page.url}...")
        
        # Wait for selector with improved error message
        try:
            page.wait_for_selector("#inpUserId", timeout=10000)
        except Exception as e:
            if "m.dhlottery.co.kr" in page.url:
                print("Mobile site detected. Trying mobile selectors...")
                # Mobile selectors (based on typical mobile dhlottery pattern)
                # Usually it's still #userId or similar
                if page.locator("#userId").is_visible(timeout=2000):
                    page.locator("#userId").fill(USER_ID)
                    page.locator("#userPwd").fill(PASSWD)
                    page.click(".btn_login") # typical mobile login button class
                    return
            
            # Diagnostic info
            print(f"Selector #inpUserId not found. Current URL: {page.url}")
            print(f"Page content snippet: {page.content()[:500]}...")
            raise e

        # Fill ID
        page.locator("#inpUserId").fill(USER_ID)
        # Fill Password
        page.locator("#inpUserPswdEncn").fill(PASSWD)
        
        # Click login button
        print("Clicking login button...")
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
    
    # NEW: Sync session with the game subdomain (el.dhlottery.co.kr)
    # This prevents the 'Timeout' or 'Session lost' issues when moving between subdomains.
    try:
        print("Synchronizing session with game subdomain...")
        # Use wait_until="commit" for fast cross-domain redirection
        page.goto("https://el.dhlottery.co.kr/common.do?method=sso", timeout=15000, wait_until="commit")
        # Often visiting a key page helps stabilize the session
        page.goto("https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40", timeout=15000, wait_until="commit")
        print("Subdomain session synced.")
    except Exception as e:
        print(f"Subdomain sync warning: {e}")
    
    # Return to main page
    try:
        page.goto("https://www.dhlottery.co.kr/common.do?method=main", timeout=15000, wait_until="commit")
    except:
        pass


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
            browser = playwright.chromium.launch(headless=HEADLESS)
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

