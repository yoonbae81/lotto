#!/usr/bin/env python3
import json
import time
import re
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT

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
    # Create browser, context, and page
    browser = playwright.chromium.launch(headless=True)

    # Load session if exists
    storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None
    context = browser.new_context(
        storage_state=storage_state,
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT
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

    try:
        # Navigate to the Wrapper Page (TotalGame.jsp) which handles session sync correctly
        print("Navigating to Lotto 720 Wrapper page...")
        page.goto("https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LP72", timeout=30000)
        
        # Check if we were redirected to mobile or login page (session lost)
        if "/login" in page.url or "method=login" in page.url or "m.dhlottery.co.kr" in page.url:
            print(f"Redirection detected (URL: {page.url}). Attempting to log in again...")
            login(page)
            page.goto("https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LP72", timeout=30000)

        # Check for logout state on the wrapper page itself
        # The wrapper page usually has a "로그인" button if session is invalid
        if page.get_by_text("로그인", exact=True).first.is_visible(timeout=3000):
             print("Wrapper page shows 'Login' button. Re-logging in...")
             login(page)
             page.goto("https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LP72", timeout=30000)

        # Access the game iframe
        # The actual game UI is loaded inside this iframe
        print("Waiting for game iframe to load...")
        # Wait for the iframe element to be visible on the main page
        try:
            # Wait for either #ifrm_tab or the main game container
            page.wait_for_selector("#ifrm_tab", state="attached", timeout=20000)
            print("Iframe #ifrm_tab found")
        except Exception:
            print("Iframe #ifrm_tab not visible. Current URL:", page.url)
            # Take a screenshot for debugging if possible (optional)
            # page.screenshot(path="lotto720_error.png")
            
        frame = page.frame_locator("#ifrm_tab")
        
        # Wait for an element inside the frame explicitly to ensure it's ready
        try:
             # Wait for either the hidden balance input OR the visible balance text
             # Increase timeout for slow iframe loads
             frame.locator("#curdeposit, .lpdeposit").first.wait_for(state="attached", timeout=30000)
        except Exception as e:
             print(f"Timeout waiting for iframe content ({e}). Retrying navigation...")
             page.reload(wait_until="networkidle")
             page.wait_for_selector("#ifrm_tab", state="visible", timeout=20000)
             frame.locator("#curdeposit, .lpdeposit").first.wait_for(state="attached", timeout=30000)

        print('Navigated to Lotto 720 Game Frame')
        
        # ----------------------------------------------------
        # Verify Session & Balance (Inside Frame)
        # ----------------------------------------------------
        time.sleep(1)

        # 1. Check Login Session (via hidden input in frame)
        user_id_val = frame.locator("input[name='USER_ID']").get_attribute("value")
        if not user_id_val:
            raise Exception("Session lost: Not logged in on Game Frame (USER_ID empty).")
        
        print(f"Login ID on Game Page: {user_id_val}")

        # 2. Check Balance (via hidden input #curdeposit in frame)
        balance_val = frame.locator("#curdeposit").get_attribute("value")
        
        # Fallback to UI element if hidden input isn't populated
        if not balance_val:
            balance_text = frame.locator(".lpdeposit").first.inner_text() 
            balance_val = balance_text.replace(",", "").replace("원", "").strip()
            
        try:
            current_balance = int(balance_val)
        except ValueError:
            current_balance = 0
            print(f"Could not parse balance value: '{balance_val}', assuming 0.")

        print(f"Current Balance on Game Page: {current_balance:,} KRW")

        if current_balance == 0:
            raise Exception("Deposit is 0 KRW. Cannot proceed with purchase. Please charge your account.")

        # Dismiss popup if present (inside frame)
        if frame.locator("#popupLayerAlert").is_visible():
            frame.locator("#popupLayerAlert").get_by_role("button", name="확인").click()

        # Wait for the game UI to load
        frame.locator(".lotto720_btn_auto_number").wait_for(state="visible", timeout=15000)

        # Remove all intercepting pause layer popups using JavaScript (in iframe context)
        # These elements block clicks even when they're not supposed to be visible
        page.evaluate("""
            () => {
                const iframe = document.querySelector('#ifrm_tab');
                if (iframe && iframe.contentDocument) {
                    const doc = iframe.contentDocument;
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
            }
        """)

        # [자동번호] 클릭 - use force to bypass any remaining intercepting elements
        sr.stage("PURCHASE")
        frame.locator(".lotto720_btn_auto_number").click(force=True)
        
        time.sleep(2)

        # [선택완료] 클릭
        frame.locator(".lotto720_btn_confirm_number").click()
        
        time.sleep(2)

        # Verify Amount
        payment_amount_el = frame.locator(".lotto720_price.lpcurpay")
        time.sleep(1)
        
        payment_amount_text = payment_amount_el.inner_text().strip()
        payment_val = int(re.sub(r'[^0-9]', '', payment_amount_text) or '0')

        if payment_val != 5000:
            print(f"Error: Payment mismatch (Expected 5000, Displayed {payment_val})")
            return

        # [구매하기] 클릭
        frame.locator("a:has-text('구매하기')").first.click()
        
        # Handle Confirmation Popup
        confirm_popup = frame.locator("#lotto720_popup_confirm")
        confirm_popup.wait_for(state="visible", timeout=5000)
        
        # Click Final Purchase Button
        confirm_popup.locator("a.btn_blue").click()
        
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
