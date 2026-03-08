#!/usr/bin/env python3
import json
import re
import sys
import time
import socket
import traceback
import datetime
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT, setup_dialog_handler

# .env loading is handled by login module import


from script_reporter import ScriptReporter


def parse_arguments():
    """
    커맨드라인 인자를 파싱하여 게임 설정 반환
    
    사용법:
    - Auto: ./lotto645.py 1000  (1게임)
    - Auto: ./lotto645.py 3000  (3게임)
    - Manual: ./lotto645.py 1 2 3 4 5 6  (수동 번호)
    
    Returns:
        tuple: (auto_games, manual_numbers)
    """
    if len(sys.argv) == 1:
        # No arguments - use .env configuration
        auto_games = int(environ.get('AUTO_GAMES', '0'))
        manual_numbers = json.loads(environ.get('MANUAL_NUMBERS', '[]'))
        return auto_games, manual_numbers
    
    # Parse command-line arguments
    args = sys.argv[1:]
    
    # Case 1: Single argument (auto games by amount)
    if len(args) == 1:
        amount_str = args[0].replace(',', '')  # Remove commas
        try:
            amount = int(amount_str)
            
            # Check if it's a valid auto game amount (1000-5000 in 1000 increments)
            if amount in [1000, 2000, 3000, 4000, 5000]:
                auto_games = amount // 1000
                print(f"Auto mode: {auto_games} game(s) ({amount:,} KRW)")
                return auto_games, []
            else:
                print(f"Error: Invalid amount '{args[0]}'")
                print(f"Valid amounts: 1000, 2000, 3000, 4000, 5000")
                sys.exit(1)
        except ValueError:
            print(f"Error: Invalid amount format '{args[0]}'")
            sys.exit(1)
    
    # Case 2: Six arguments (manual number selection)
    elif len(args) == 6:
        try:
            numbers = [int(arg) for arg in args]
            
            # Validate: all numbers must be 1-45
            if not all(1 <= n <= 45 for n in numbers):
                print(f"Error: All numbers must be between 1 and 45")
                print(f"Provided: {numbers}")
                sys.exit(1)
            
            # Validate: no duplicates
            if len(numbers) != len(set(numbers)):
                print(f"Error: Numbers must not contain duplicates")
                print(f"Provided: {numbers}")
                sys.exit(1)
            
            # Sort numbers for display
            sorted_numbers = sorted(numbers)
            print(f"Manual mode: {sorted_numbers}")
            return 0, [numbers]
            
        except ValueError:
            print(f"Error: All arguments must be numbers")
            print(f"Provided: {args}")
            sys.exit(1)
    
    else:
        print(f"Error: Invalid number of arguments")
        print(f"\nUsage:")
        print(f"  Auto games:   ./lotto645.py [AMOUNT]")
        print(f"                where AMOUNT is 1000, 2000, 3000, 4000, or 5000")
        print(f"  Manual game:  ./lotto645.py [N1] [N2] [N3] [N4] [N5] [N6]")
        print(f"                where each N is a number from 1 to 45 (no duplicates)")
        print(f"\nExamples:")
        print(f"  ./lotto645.py 3000          # Buy 3 auto games")
        print(f"  ./lotto645.py 1 2 3 4 5 6   # Buy 1 manual game with numbers 1,2,3,4,5,6")
        sys.exit(1)


def run(playwright: Playwright, auto_games: int, manual_numbers: list, sr: ScriptReporter) -> dict:
    """
    로또 6/45를 자동 및 수동으로 구매합니다.
    """
    GAME_URL = "https://ol.dhlottery.co.kr/olotto/game_mobile/game645.do"
    
    # Create browser, context, and page
    HEADLESS = environ.get('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 500)

    # Load session if exists
    storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None
    context = browser.new_context(
        storage_state=storage_state, 
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT,
        is_mobile=True,
        has_touch=True,
        extra_http_headers=DEFAULT_HEADERS
    )

    def check_mobile_purchase_restriction(page) -> tuple[bool, str]:
        """
        모바일 로또645 구매 가능 여부를 조회합니다.

        Returns:
            tuple[bool, str]: (구매제한 여부, 요일/메시지)
        """
        try:
            resp = page.request.get("https://m.dhlottery.co.kr/selectMobPrchsCheck.do", timeout=GLOBAL_TIMEOUT)
            if not resp.ok:
                return False, ""

            payload = resp.json()
            result = payload.get("data", {}).get("result", {})
            # Site JS logic:
            # mobPrchs == "1"  => 모바일 구매 제한
            # mobPrchs != "1"  => 구매 가능
            if str(result.get("mobPrchs", "")) == "1":
                return True, str(result.get("nowDay", "")).strip()
            return False, ""
        except Exception:
            # If this check fails, continue normal flow and rely on page validation.
            return False, ""
    
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

        # 1.5 Mobile purchase day restriction check (Sat/Sun)
        restricted, now_day = check_mobile_purchase_restriction(page)
        if restricted:
            day_msg = now_day if now_day else "토/일요일"
            msg = f"{day_msg}에는 로또6/45 모바일 구매가 제한됩니다."
            print(msg)
            return {"processed_count": 0, "status": "failed", "reason": "mobile_restricted", "message": msg}
        
        # 2. Navigate to Game Page
        sr.stage("NAVIGATE")
        print(f"Navigating to Lotto 6/45 mobile game: {GAME_URL}")
        try:
            # Use 'domcontentloaded' for faster loading
            page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
            
            # Final check if redirected
            if "/login" in page.url or "method=login" in page.url:
                print("Session lost during navigation. Re-logging in...")
                login(page)
                page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")

            # If still not on game page, fail early with an explicit reason.
            if "ol.dhlottery.co.kr/olotto/game_mobile/game645.do" not in page.url:
                print(f"Unexpected redirect while opening Lotto 6/45: {page.url}")
                page.screenshot(path=f"lotto645_unexpected_redirect_{int(time.time())}.png")
                return {"processed_count": 0, "status": "failed", "reason": "unexpected_redirect", "url": page.url}
        except Exception as e:
            print(f"Navigation failed: {e}")
            page.screenshot(path=f"lotto645_nav_failed_{int(time.time())}.png")
            raise e

        # Give a moment for components to initialize
        time.sleep(1)
        
        # 3. Selection Flow
        sr.stage("SELECT_NUMBERS")
        
        def get_actual_cart_count():
            # Any visible .myNum-box represents an added game (Auto or Manual)
            return page.locator(".myNum-box:visible").count()

        # Automatic games
        if auto_games > 0:
            print(f"Adding automatic game(s): {auto_games}")
            auto_btn = page.locator("button:has-text('자동 1매 추가')")
            for i in range(auto_games):
                current_count = get_actual_cart_count()
                if current_count >= 5:
                    print("Cart is full (5 games max)")
                    break
                
                try:
                    if auto_btn.is_visible(timeout=3000):
                        auto_btn.click()
                        # Wait for count to increase
                        success = False
                        for _ in range(10):
                            time.sleep(0.3)
                            if get_actual_cart_count() > current_count:
                                success = True
                                break
                        if not success:
                            print(f"Failed to add auto game {i+1} (count didn't increase)")
                    else:
                        print(f"Auto button not visible for game {i+1}")
                        break
                except Exception as e:
                    print(f"Error adding auto game: {e}")
                    break

        # Manual numbers
        if manual_numbers and len(manual_numbers) > 0:
            for numbers in manual_numbers:
                if get_actual_cart_count() >= 5:
                    print("Cart is full (5 games max)")
                    break
                    
                print(f"Adding manual game: {numbers}")
                # Click '번호 선택하기' to open the popup board
                open_btn = page.locator("button:has-text('번호 선택하기')").first
                if open_btn.is_visible(timeout=3000):
                    open_btn.click()
                    time.sleep(0.8)

                # Reset previous selection to ensure clean state (especially for identical games)
                reset_btn = page.locator("#btnInit, button:has-text('초기화')").first
                if reset_btn.is_visible(timeout=2000):
                    reset_btn.click()
                    time.sleep(0.5)

                # Select each number
                for number in numbers:
                    num_el = page.locator(f"xpath=//div[contains(@class, 'lt-num') and text()='{number}']").first
                    if num_el.is_visible(timeout=2000):
                        num_el.click()
                        time.sleep(0.05)
                    else:
                        print(f"Number {number} not found on board")
                
                # Click '선택완료' to add to list
                select_done = page.locator("#btnSelectNum, button:has-text('선택완료')").first
                if select_done.is_visible(timeout=2000):
                    current_count = get_actual_cart_count()
                    select_done.click()
                    
                    # Handle "Already selected" or other alerts inside selection popup
                    alert = page.locator("#popupLayerAlert:visible")
                    if alert.is_visible(timeout=2000):
                        msg = alert.inner_text()
                        print(f"Alert during manual addition: {msg}")
                        alert.locator("button:has-text('확인')").click()
                        time.sleep(0.5)

                    # Wait for cart count to increase
                    success = False
                    for _ in range(15):
                        time.sleep(0.3)
                        if get_actual_cart_count() > current_count:
                            success = True
                            break
                    if not success:
                        print(f"Failed to add manual game (count didn't increase). Cart count: {get_actual_cart_count()}")
                    else:
                        print(f"Manual game added successfully. Cart count: {get_actual_cart_count()}")
                
                # Confirm popup closed or handle "Already selected" alert
                # The manual selection popup has an ID #popupSelectNum
                confirm_btn = page.locator("#popupSelectNum button:has-text('확인'), #popupLayerAlert button:has-text('확인')").first
                if confirm_btn.is_visible(timeout=2000):
                    confirm_btn.click()
                    print("Clicked confirmation in popup.")
                    time.sleep(0.8)
                
                # Wait for popup to be hidden to ensure we are back on the main page
                try:
                    page.wait_for_selector("#popupSelectNum", state="hidden", timeout=3000)
                except:
                    # If it's still visible, try to click the close (X) button as fallback
                    close_btn = page.locator("#popupSelectNum .btn-pop-close").first
                    if close_btn.is_visible(timeout=1000):
                        close_btn.click()
                        time.sleep(0.5)
                
                time.sleep(0.5)

        # Check total games added
        total_games = get_actual_cart_count()
        if total_games == 0:
            print('No games in cart to purchase!')
            return {"processed_count": 0}

        # 4. Final Purchase
        sr.stage("PURCHASE")
        # Double check cart before purchase
        final_count = get_actual_cart_count()
        if final_count != total_games:
            print(f"Warning: Expected {total_games} games, but found {final_count} in cart.")
            total_games = final_count
            
        print(f"Clicking 'Purchase' (구매하기) for {total_games} games...")
        buy_btn = page.locator("#btnBuy, button:has-text('구매하기')").first
        if buy_btn.is_visible(timeout=5000):
            buy_btn.click()
        else:
            print("Purchase button not visible. Check if games were added successfully.")
            page.screenshot(path=f"lotto645_no_buy_btn_{int(time.time())}.png")
            return {"processed_count": 0, "status": "failed"}
        
        # 5. Confirm purchase popup
        sr.stage("CONFIRM_PURCHASE")
        print("Confirming final purchase...")
        
        # Select specifically the confirmation OK button (class buttonOk)
        confirm_btn = page.locator("#popupLayerConfirm .buttonOk, #popupLayerConfirm button:has-text('확인')").first
        
        try:
            # Explicitly wait for the confirm button to be visible and enabled
            confirm_btn.wait_for(state="visible", timeout=5000)
            confirm_btn.click()
            print("Final confirmation clicked.")
        except Exception as e:
            print(f"Confirmation button click failed or not found: {e}")
            page.screenshot(path=f"lotto645_confirm_failed_{int(time.time())}.png")
            # If we reached here after clicking Buy, maybe it worked anyway, but we should be careful.
            # Don't return success yet.

        # 6. Verify success (wait for the result/receipt popup)
        sr.stage("VERIFY_RESULT")
        try:
            # The receipt popup is #report. Wait for it or an alert/confirm to become visible.
            # Weekly limit popup often uses #popupLayerConfirm or #popupLayerAlert
            page.wait_for_selector("#report:visible, #popupLayerAlert:visible, #popupLayerConfirm:visible", timeout=15000)
            
            # Final result screenshot
            page.screenshot(path=f"lotto645_result_{int(time.time())}.png")
            
            if page.locator("#report").is_visible():
                print("Purchase success confirmed! (Receipt visible)")
                return {"processed_count": total_games, "status": "success"}
            
            # Check both #popupLayerAlert and #popupLayerConfirm for messages
            alert_text = ""
            if page.locator("#popupLayerAlert").is_visible():
                alert_text = page.locator("#popupLayerAlert").inner_text()
            elif page.locator("#popupLayerConfirm").is_visible():
                alert_text = page.locator("#popupLayerConfirm").inner_text()

            if "구매가 완료되었습니다" in alert_text or "구매를 완료하였습니다" in alert_text:
                print("Purchase success confirmed by alert UI!")
                return {"processed_count": total_games, "status": "success"}
            elif "예치금이 부족합니다" in alert_text:
                print("Purchase failed: Insufficient balance.")
                return {"processed_count": 0, "status": "failed", "reason": "low_balance"}
            elif "구매한도" in alert_text:
                print(f"Purchase failed or partially succeeded: Weekly limit reached. Msg: {alert_text}")
                return {"processed_count": 0, "status": "failed", "reason": "limit_reached"}
            else:
                print(f"Purchase result ambiguous. Alert text: {alert_text}")
                return {"processed_count": total_games, "status": "ambiguous"}
                
        except Exception as e:
            print(f"Result verification timed out: {e}")
            page.screenshot(path=f"lotto645_verify_failed_{int(time.time())}.png")
            return {"processed_count": total_games, "status": "unknown"}

    except Exception as e:
        print(f"Flow interrupted: {e}")
        try:
            page.screenshot(path=f"lotto645_error_{int(time.time())}.png")
        except:
            pass
        raise
    finally:
        context.close()
        browser.close()


if __name__ == "__main__":
    sr = ScriptReporter("Lotto 6/45")
    
    try:
        # Parse command-line arguments or use .env configuration
        auto_games, manual_numbers = parse_arguments()
        
        with sync_playwright() as playwright:
            process_result = run(playwright, auto_games, manual_numbers, sr)
            if process_result.get("status") == "success":
                sr.success(process_result)
            else:
                sr.fail(f"Purchase failed or status unknown: {process_result}")
                sys.exit(1)
            
    except Exception as e:
        sr.fail(traceback.format_exc())
        sys.exit(1)
