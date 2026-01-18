#!/usr/bin/env python3
import json
import time
import re
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from login import login

# .env loading is handled by login module import


def run(playwright: Playwright) -> None:
    """
    연금복권 720+를 구매합니다.
    '모든 조'를 선택하여 임의의 번호로 5매(5,000원)를 구매합니다.
    
    Args:
        playwright: Playwright 객체
    """
    # Create browser, context, and page
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    # Perform login using injected page
    login(page)

    try:
        # Navigate to the Wrapper Page (TotalGame.jsp) which handles session sync correctly
        print("🚀 Navigating to Lotto 720 Wrapper page...")
        page.goto("https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LP72", timeout=30000, wait_until="domcontentloaded")
        
        # Access the game iframe
        # The actual game UI is loaded inside this iframe
        print("Waiting for game iframe to load...")
        # Wait for the iframe element to be visible on the main page
        try:
            page.locator("#ifrm_tab").wait_for(state="visible", timeout=10000)
        except Exception:
            print("⚠️ Iframe #ifrm_tab not visible. Page source might be different.")
        
        frame = page.frame_locator("#ifrm_tab")
        
        # Wait for an element inside the frame explicitly to ensure it's ready
        try:
             # Wait for either the hidden balance input OR the visible balance text
             # This makes it robust if one is missing or slow
             frame.locator("#curdeposit, .lpdeposit").first.wait_for(state="attached", timeout=20000)
        except Exception:
             print("⚠️ Timeout waiting for iframe content. Retrying navigation...")
             page.reload()
             page.locator("#ifrm_tab").wait_for(state="visible", timeout=10000)
             frame.locator("#curdeposit, .lpdeposit").first.wait_for(state="attached", timeout=20000)

        print('✅ Navigated to Lotto 720 Game Frame')
        
        # ----------------------------------------------------
        # Verify Session & Balance (Inside Frame)
        # ----------------------------------------------------
        time.sleep(1)

        # 1. Check Login Session (via hidden input in frame)
        user_id_val = frame.locator("input[name='USER_ID']").get_attribute("value")
        if not user_id_val:
            raise Exception("❌ Session lost: Not logged in on Game Frame (USER_ID empty).")
        
        print(f"🔑 Login ID on Game Page: {user_id_val}")

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
            print(f"⚠️ Could not parse balance value: '{balance_val}', assuming 0.")

        print(f"💰 Current Balance on Game Page: {current_balance:,} KRW")

        if current_balance == 0:
            raise Exception("❌ Deposit is 0 KRW. Cannot proceed with purchase. Please charge your account.")

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
            print(f"❌ Error: Payment mismatch (Expected 5000, Displayed {payment_val})")
            return

        # [구매하기] 클릭
        frame.locator("a:has-text('구매하기')").first.click()
        
        # Handle Confirmation Popup
        confirm_popup = frame.locator("#lotto720_popup_confirm")
        confirm_popup.wait_for(state="visible", timeout=5000)
        
        # Click Final Purchase Button
        confirm_popup.locator("a.btn_blue").click()
        
        time.sleep(2)
        print("✅ Lotto 720: All sets purchased successfully!")
        

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # Cleanup
        context.close()
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)

