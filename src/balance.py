#!/usr/bin/env python3
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright, Page
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT

import sys
import traceback
from script_reporter import ScriptReporter

# .env loading is handled by login module import


def get_balance(page: Page) -> dict:
    """
    마이페이지에서 예치금 잔액과 구매가능 금액을 조회합니다.
    """
    print("Navigating to My Page...")
    page.goto("https://m.dhlottery.co.kr/mypage/home", timeout=GLOBAL_TIMEOUT, wait_until="commit")
    print(f"Current URL: {page.url}")
    
    # Check if redirected to login or error
    if "/login" in page.url or "method=login" in page.url or "/errorPage" in page.url:
        print("Redirection to login or error page detected. Attempting to log in again...")
        login(page)
        page.goto("https://m.dhlottery.co.kr/mypage/home", timeout=GLOBAL_TIMEOUT, wait_until="commit")
        print(f"Current URL: {page.url}")
    
    print("Waiting for balance elements...")
    try:
        page.wait_for_selector("#navTotalAmt, .pntDpstAmt", timeout=GLOBAL_TIMEOUT)
    except Exception as e:
        print(f"Balance selectors not found immediately. Current page: {page.url}")
        if page.get_by_role("link", name=re.compile("로그인")).first.is_visible():
            raise Exception("Not logged in. Cannot retrieve balance.")

    # 1. Get deposit balance (예치금 잔액)
    # On mobile My Page home, balance is often inside #navTotalAmt or a span with class pntDpstAmt
    deposit_selectors = ["#navTotalAmt", ".pntDpstAmt", ".header_money"]
    deposit_text = "0"
    for selector in deposit_selectors:
        el = page.locator(selector).first
        if el.is_visible():
            deposit_text = el.inner_text().strip()
            print(f" -> Found deposit balance: '{deposit_text}' (via {selector})")
            break
    
    # 2. Get available amount (구매가능)
    available_selectors = ["#divCrntEntrsAmt", ".totalAmt", ".header_money"]
    available_text = "0"
    for selector in available_selectors:
        el = page.locator(selector).first
        if el.is_visible():
            available_text = el.inner_text().strip()
            print(f" -> Found available amount: '{available_text}' (via {selector})")
            break
    
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
    
    try:
        # Perform login only if needed
        from login import is_logged_in
        if not is_logged_in(page):
            sr.stage("LOGIN")
            login(page)
        else:
            print("Already logged in. Skipping login stage.")
        
        # Get balance information
        sr.stage("GET_BALANCE")
        balance_info = get_balance(page)
        
        # Print results in a clean format
        print(f"Deposit Balance: {balance_info['deposit_balance']:,} won")
        print(f"Available Amount: {balance_info['available_amount']:,} won")
        
        return balance_info
        
    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        # Cleanup
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
