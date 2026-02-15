#!/usr/bin/env python3
import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright, Page
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT

import sys
import traceback
from script_reporter import ScriptReporter


def get_balance(page: Page) -> dict:
    """
    마이페이지에서 예치금 잔액과 구매가능 금액을 조회합니다.
    """
    print("Navigating to My Page...")
    try:
        page.goto("https://m.dhlottery.co.kr/mypage/home", timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
    except Exception as e:
        print(f"Navigation to My Page failed: {e}")
        page.screenshot(path=f"balance_nav_failed_{int(time.time())}.png")
        raise e

    print(f"Current URL: {page.url}")
    
    # Check if redirected to login or error
    if "/login" in page.url or "method=login" in page.url or "/errorPage" in page.url:
        print("Not logged in. Redirected to login/error page. Attempting login...")
        login(page)
        # Re-navigate after login
        page.goto("https://m.dhlottery.co.kr/mypage/home", timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
    
    # Try to find balance information
    try:
        # Wait for either total amount or deposit amount to be visible
        page.wait_for_selector("#navTotalAmt, .pntDpstAmt, .header_money", state="visible", timeout=GLOBAL_TIMEOUT)
    except Exception as e:
        print(f"Balance elements not visible: {e}")
        page.screenshot(path=f"balance_elements_failed_{int(time.time())}.png")
        # Final check if we are actually logged in
        if "/login" in page.url:
             raise Exception("Authentication required to view balance.")

    # 1. Get deposit balance (예치금 잔액)
    # Mobile Specific: #navTotalAmt is common for total, .pntDpstAmt for deposit
    deposit_selectors = ["#navTotalAmt", ".pntDpstAmt", ".header_money"]
    deposit_text = "0"
    for selector in deposit_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=1000):
                deposit_text = el.inner_text().strip()
                print(f" -> Found balance: '{deposit_text}' (via {selector})")
                break
        except:
            continue
    
    # 2. Extract specifically 'Available' if possible, otherwise use the found balance
    # Often on mobile, the total deposit is what's displayed.
    available_selectors = ["#divCrntEntrsAmt", ".totalAmt", ".pntDpstAmt"]
    available_text = deposit_text # Default to same if not found separately
    for selector in available_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=500):
                available_text = el.inner_text().strip()
                break
        except:
            continue
    
    # Parse amounts (remove non-digits)
    deposit_balance = int(re.sub(r'[^0-9]', '', deposit_text) or "0")
    available_amount = int(re.sub(r'[^0-9]', '', available_text) or "0")
    
    return {
        'deposit_balance': deposit_balance,
        'available_amount': available_amount
    }


def run(playwright: Playwright, sr: ScriptReporter) -> dict:
    """로그인 후 잔액 정보를 조회합니다."""
    # Create browser, context, and page
    HEADLESS = os.environ.get('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(headless=HEADLESS)

    # Load session if exists
    storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None
    
    # Use context managers for clean exit
    context = browser.new_context(
        storage_state=storage_state,
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT,
        extra_http_headers=DEFAULT_HEADERS
    )
    
    try:
        page = context.new_page()
        
        # Perform login only if needed
        from login import is_logged_in
        sr.stage("CHECK_SESSION")
        if not is_logged_in(page):
            print("Session expired or missing. Logging in...")
            sr.stage("LOGIN")
            login(page)
        else:
            print("Session is valid.")
        
        # Get balance information
        sr.stage("GET_BALANCE")
        balance_info = get_balance(page)
        
        print(f"Balance Summary: {balance_info['deposit_balance']:,}원 (구매가능: {balance_info['available_amount']:,}원)")
        
        return balance_info
        
    except Exception as e:
        print(f"Execution Error: {e}")
        raise
    finally:
        context.close()
        browser.close()


if __name__ == "__main__":
    sr = ScriptReporter("Balance Check")
    try:
        with sync_playwright() as playwright:
            balance_info = run(playwright, sr)
            sr.success(balance_info)
    except Exception as e:
        sr.fail(traceback.format_exc())
        sys.exit(1)
