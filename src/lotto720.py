#!/usr/bin/env python3
import json
import time
import re
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT

import sys
import traceback
from script_reporter import ScriptReporter

# .env loading is handled by login module import


def run(playwright: Playwright, sr: ScriptReporter) -> None:
    """
    연금복권 720+를 구매합니다.
    '모든 조'를 선택하여 임의의 번호로 5매(5,000원)를 구매합니다.
    
    Args:
        playwright: Playwright 객체
    """
    GAME_URL = "https://el.dhlottery.co.kr/game_mobile/pension720/game.jsp"
    
    # Create browser, context, and page
    HEADLESS = environ.get('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 500)

    # Load session if exists
    storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None
    context = browser.new_context(
        storage_state=storage_state,
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT,
        extra_http_headers=DEFAULT_HEADERS
    )
    page = context.new_page()
    
    # Setup alert handler to automatically accept any alerts
    page.on("dialog", lambda dialog: dialog.accept())

    # Perform login only if needed
    from login import is_logged_in
    if not is_logged_in(page):
        sr.stage("LOGIN")
        login(page)
    else:
        print("Already logged in. Skipping login stage.")
    
    sr.stage("NAVIGATE")
    
    # 1. Prime the session on the main domain first
    # This ensures that cookies are 'active' before hitting the game subdomain
    try:
        print("Priming session on main domain...")
        page.goto("https://www.dhlottery.co.kr/common.do?method=main", timeout=GLOBAL_TIMEOUT, wait_until="commit")
    except Exception as e:
        print(f"Priming warning: {e}")

    try:
        # Navigate to the Game Page directly
        print(f"Navigating to Lotto 720 mobile game page: {GAME_URL}")
        page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="commit", referer="https://m.dhlottery.co.kr/")
        print(f"Current URL: {page.url}")
        
        # Check if we were redirected to login page (session lost)
        if "/login" in page.url or "method=login" in page.url:
            print(f"Redirection detected (URL: {page.url}). Attempting to log in again...")
            login(page)
            page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="commit")
            print(f"Current URL: {page.url}")

        # Give it a moment to load components
        time.sleep(2)
        
        # ----------------------------------------------------
        # Verify Session & Balance
        # ----------------------------------------------------
        
        # On mobile, we might not have the hidden inputs, so check UI
        print("Checking balance...")
        balance_selectors = ["#curdeposit", ".lpdeposit", "#payAmt", ".totalAmt"]
        current_balance = 0
        for selector in balance_selectors:
            el = page.locator(selector).first
            if el.is_visible(timeout=GLOBAL_TIMEOUT):
                val = el.inner_text() if not el.get_attribute("value") else el.get_attribute("value")
                current_balance = int(re.sub(r'[^0-9]', '', val) or '0')
                print(f"Current Balance: {current_balance:,} KRW (via {selector})")
                break
        
        # If balance check failed but we are on the game page, we might still proceed
        # or it might be 0.
        
        if current_balance == 0:
            raise Exception("Deposit is 0 KRW. Cannot proceed with purchase. Please charge your account.")

        # Dismiss popup if present
        if page.locator("#popupLayerAlert").is_visible():
            page.locator("#popupLayerAlert").get_by_role("button", name="확인").click()

        # Wait for the game UI to load
        # Mobile selectors might differ. Common one for auto: .btn_auto, .lotto720_btn_auto_number
        auto_btn = page.locator(".lotto720_btn_auto_number, .btn_auto, #btnAuto").first
        auto_btn.wait_for(state="visible", timeout=GLOBAL_TIMEOUT)

        # Remove all intercepting pause layer popups using JavaScript
        # These elements block clicks even when they're not supposed to be visible
        page.evaluate("""
            () => {
                const doc = document;
                // Hide all known pause layer elements
                const selectors = [
                    '#pause_layer_pop_02',
                    '#ele_pause_layer_pop02',
                    '.pause_layer_pop',
                    '.pause_bg'
                ];
                
                selectors.forEach(selector => {
                    const elements = doc.querySelectorAll(selector);
                    elements.forEach(el => {
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                        el.style.pointerEvents = 'none';
                    });
                });
            }
        """)

        # [자동번호] 클릭
        sr.stage("PURCHASE_SELECTION")
        print("Clicking 'Automatic Number' (자동번호)...")
        auto_btn.click(force=True)
        
        time.sleep(1)
        
        # [선택완료] 클릭
        print("Clicking 'Confirm Selection' (선택완료)...")
        confirm_btn = page.locator(".lotto720_btn_confirm_number, .btn_confirm, #btnConfirm").first
        confirm_btn.click()
        
        time.sleep(1)
 
        # [구매하기] 클릭
        print("Clicking 'Purchase' (구매하기)...")
        buy_btn = page.locator("a:has-text('구매하기'), .btn_buy, #btnBuy").first
        buy_btn.click()
        
        # Handle Confirmation Popup
        print("Waiting for final confirmation popup...")
        confirm_popup = page.locator("#lotto720_popup_confirm, #popupLayerConfirm").first
        confirm_popup.wait_for(state="visible", timeout=GLOBAL_TIMEOUT)
        
        # Click Final Purchase Button
        print("Confirming final purchase...")
        confirm_popup.locator("a.btn_blue, .btn_confirm_ok, input[value='확인']").first.click()
        
        time.sleep(2)
        print("Lotto 720: All sets purchased successfully!")
        

    except Exception as e:
        print(f"An error occurred: {e}")
        raise # Re-raise the exception to be caught by the main block
    finally:
        # Cleanup
        context.close()
        browser.close()

if __name__ == "__main__":
    sr = ScriptReporter("Lotto 720")
    try:
        with sync_playwright() as playwright:
            run(playwright, sr)
            sr.success({"processed_count": 5}) # Fixed at 5 games as per script logic
    except Exception:
        sr.fail(traceback.format_exc())
        sys.exit(1)
