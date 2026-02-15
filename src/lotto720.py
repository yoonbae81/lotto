#!/usr/bin/env python3
import json
import time
import re
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT, setup_dialog_handler

import sys
import traceback
from script_reporter import ScriptReporter

# .env loading is handled by login module import


def run(playwright: Playwright, sr: ScriptReporter) -> None:
    """
    연금복권 720+를 구매합니다.
    '모든 조'를 선택하여 임의의 번호로 5매(5,000원)를 구매합니다.
    """
    GAME_URL = "https://el.dhlottery.co.kr/game_mobile/pension720/game.jsp"
    
    # Create browser, context, and page
    HEADLESS = environ.get('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(headless=HEADLESS)

    # Load session if exists
    storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None
    context = browser.new_context(
        storage_state=storage_state,
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT,
        extra_http_headers=DEFAULT_HEADERS
    )
    
    try:
        page = context.new_page()
        setup_dialog_handler(page)

        # 1. Session Check & Login
        from login import is_logged_in
        sr.stage("CHECK_SESSION")
        if not is_logged_in(page):
            print("Session expired or missing. Logging in...")
            sr.stage("LOGIN")
            login(page)
        else:
            print("Session is valid.")
        
        # 2. Navigate to Game Page
        sr.stage("NAVIGATE")
        print(f"Navigating to Lotto 720 game: {GAME_URL}")
        try:
            # Use domcontentloaded for faster loading
            page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
            
            # Final check if redirected
            if "/login" in page.url or "method=login" in page.url:
                print("Session lost during navigation. Re-logging in...")
                login(page)
                page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            page.screenshot(path=f"lotto720_nav_failed_{int(time.time())}.png")
            raise e

        # Give a small moment for components to initialize
        time.sleep(1)
        
        # 3. Purchase Flow
        sr.stage("PURCHASE_PROCESS")
        
        # Step 1: Open Number Selection
        print("Opening selection options...")
        select_btn = page.locator("a.btn_gray_st1.large.full, a:has-text('번호 선택하기')").visible=True
        try:
            page.wait_for_selector("a.btn_gray_st1.large.full, a:has-text('번호 선택하기')", state="visible", timeout=GLOBAL_TIMEOUT)
            page.locator("a.btn_gray_st1.large.full, a:has-text('번호 선택하기')").first.click()
        except Exception as e:
            print(f"Selection button not found/clickable: {e}")
            page.screenshot(path=f"lotto720_select_btn_failed_{int(time.time())}.png")
            raise e
        
        time.sleep(1) # Wait for animation

        # Step 2: Ensure 'All Jo' is selected & Click Automatic
        print("Ensuring 'All Jo' (모든조) is selected and clicking 'Automatic' (자동번호)...")
        try:
            # Select 'All Jo'
            all_jo = page.locator("li:has-text('모든조'), span.group.all").first
            if all_jo.is_visible(timeout=2000):
                all_jo.click()
                time.sleep(0.3)
            
            # Click 'Automatic'
            page.locator("a.btn_wht.xsmall:has-text('자동번호'), a:has-text('자동번호')").first.click()
            
            # Wait for any spinner to disappear
            page.wait_for_selector("text=통신중입니다", state="hidden", timeout=5000)
            time.sleep(0.5)
        except Exception as e:
            print(f"Automatic selection failed: {e}")
            page.screenshot(path=f"lotto720_auto_failed_{int(time.time())}.png")
            raise e
        
        # Step 3: Confirm Selection
        print("Confirming selection...")
        page.locator("a.btn_blue.full.large:has-text('선택완료'), a:has-text('선택완료')").first.click()
        time.sleep(0.8)

        # Step 4: Final Purchase
        print("Clicking 'Purchase' (구매하기)...")
        page.locator("a.btn_blue.large.full:has-text('구매하기'), a:has-text('구매하기')").first.click()
        
        # Step 5: Verify Result
        print("Verifying success...")
        try:
            # Wait for results modal or confirmation
            # The dialog handler should have accepted the initial 'Are you sure?' alert.
            # Now we look for the final confirm button in the result popup.
            final_confirm = page.locator("a.btn_lgray.medium:has-text('확인'), a.btn_blue:has-text('확인'), a:has-text('확인')").first
            if final_confirm.is_visible(timeout=10000):
                final_confirm.click()
                print("Lotto 720: Purchase successful.")
            else:
                print("Result confirmation button not visible, assuming success if no error alert shown.")
        except Exception:
             print("Result confirmation timeout. Login/Balance may need check.")

    except Exception as e:
        print(f"Purchase flow interrupted: {e}")
        try:
            page.screenshot(path=f"lotto720_error_{int(time.time())}.png")
        except:
             pass
        raise
    finally:
        context.close()
        browser.close()

if __name__ == "__main__":
    sr = ScriptReporter("Lotto 720")
    try:
        with sync_playwright() as playwright:
            run(playwright, sr)
            sr.success({"processed_count": 5})
    except Exception:
        sr.fail(traceback.format_exc())
        sys.exit(1)
