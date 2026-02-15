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
        print(f"Navigating to Lotto 6/45 mobile game: {GAME_URL}")
        try:
            # Use 'domcontentloaded' for faster loading
            page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
            
            # Final check if redirected
            if "/login" in page.url or "method=login" in page.url:
                print("Session lost during navigation. Re-logging in...")
                login(page)
                page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            page.screenshot(path=f"lotto645_nav_failed_{int(time.time())}.png")
            raise e

        # Give a moment for components to initialize
        time.sleep(1)
        
        # 3. Selection Flow
        sr.stage("SELECT_NUMBERS")
        
        # Automatic games
        if auto_games > 0:
            print(f"Adding automatic game(s): {auto_games}")
            # On mobile, clicking '자동 1매 추가' adds one game to the list
            auto_btn = page.locator("button:has-text('자동 1매 추가')")
            for i in range(auto_games):
                try:
                    # Ensure button is visible/ready
                    if auto_btn.is_visible(timeout=3000):
                        auto_btn.click()
                        time.sleep(0.5)
                    else:
                        print(f"Auto button not visible for game {i+1}")
                        break
                except Exception as e:
                    print(f"Failed to click auto button: {e}")
                    break

        # Manual numbers
        if manual_numbers and len(manual_numbers) > 0:
            for numbers in manual_numbers:
                print(f"Adding manual game: {numbers}")
                # Select each number
                for number in numbers:
                    num_el = page.locator(f".lt-num:has-text('{number}')").first
                    if num_el.is_visible(timeout=2000):
                        num_el.click()
                    else:
                        print(f"Number {number} not found on board")
                
                # Click '선택완료' to add to list
                select_done = page.locator("#btnSelectNum, button:has-text('선택완료')").first
                if select_done.is_visible(timeout=2000):
                    select_done.click()
                time.sleep(0.5)

        # Check total games added
        # (This is a simplified check, ideally we'd look at the UI list)
        total_games = auto_games + len(manual_numbers)
        if total_games == 0:
            print('No games selected to purchase!')
            return {"processed_count": 0}

        # 4. Final Purchase
        sr.stage("PURCHASE")
        print(f"Clicking 'Purchase' (구매하기) for {total_games} games...")
        buy_btn = page.locator("#btnBuy, button:has-text('구매하기')").first
        if buy_btn.is_visible(timeout=5000):
            buy_btn.click()
        else:
            print("Purchase button not visible. Check if games were added successfully.")
            page.screenshot(path=f"lotto645_no_buy_btn_{int(time.time())}.png")
            return {"processed_count": 0, "status": "failed"}
        
        # 5. Confirm purchase popup
        print("Confirming final purchase...")
        try:
            # Mobile uses a custom popup layer with '확인' button
            confirm_btn = page.locator("#popupLayerConfirm button:has-text('확인'), button:has-text('확인'), a:has-text('확인')").first
            if confirm_btn.is_visible(timeout=3000):
                confirm_btn.click()
                print("Final confirmation clicked.")
        except Exception:
            # Fallback for standard alert (though dialog handler should catch it)
            print("No confirmation popup found, assuming initial dialog handler handled it.")

        time.sleep(2)
        print(f'Lotto 6/45: Purchase process completed.')
        return {"processed_count": total_games}

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
            sr.success(process_result)
            
    except Exception as e:
        sr.fail(traceback.format_exc())
        sys.exit(1)
