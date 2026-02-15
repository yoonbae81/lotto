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
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT

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
    
    Args:
        playwright: Playwright 객체
        auto_games: 자동 구매 게임 수
        manual_numbers: 수동 구매 번호 리스트
        sr: ScriptReporter 객체
    
    Returns:
        dict: 처리 결과 세부 정보 (processed_count 등)
    """
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
    
    # 0. Setup alert handler to automatically accept any alerts (like session timeout alerts)
    page.on("dialog", lambda dialog: dialog.accept())

    # Perform login only if needed
    from login import is_logged_in
    try:
        if not is_logged_in(page):
            sr.stage("LOGIN")
            login(page)
        else:
            print("Already logged in. Skipping login stage.")

        # Navigate to the Mobile Game Page directly
        sr.stage("NAVIGATE")
        # Note: The previous URL (ol.dhlottery.co.kr) is deprecated. 
        # TODO: Update with the correct mobile-optimized URL for 6/45
        print("Lotto 6/45 mobile URL needs to be updated. Skipping for now.")
        return {"processed_count": 0, "status": "skipped"}
        
        # Following code is kept for structure but currently unreachable
        game_url = "https://m.dhlottery.co.kr/" # Placeholder
        page.goto(game_url, timeout=GLOBAL_TIMEOUT, wait_until="commit")
        
        # Check if we were redirected to login page (session lost)
        if "/login" in page.url or "method=login" in page.url:
            print("Redirection detected. Attempting to log in again...")
            sr.stage("RELOGIN")
            login(page)
            page.goto(game_url, timeout=GLOBAL_TIMEOUT, wait_until="commit")
            print(f"Current URL: {page.url}")

        # Wait for the game interface to load
        print("Waiting for game interface to load...")
        page.wait_for_selector("#checkAutoSelect, #btnSelectNum", state="visible", timeout=GLOBAL_TIMEOUT)

        # 1. Automatic games
        sr.stage("SELECT_NUMBERS")
        if auto_games > 0:
            print(f"Adding automatic game(s): {auto_games}")
            # Check '자동선택'
            page.locator('label[for="checkAutoSelect"]').click()
            # Select amount
            page.locator("#amoundApply").select_option(str(auto_games))
            # Click '확인'
            page.locator("#btnSelectNum").click()

        # 2. Manual numbers
        if manual_numbers and len(manual_numbers) > 0:
            for game in manual_numbers:
                print(f"Adding manual game: {game}")
                # Ensure '수동선택' is active if needed (usually default or after auto)
                # On mobile, clicking a number might just work
                for number in game:
                    page.locator(f'label[for="check645num{number}"]').click()
                page.locator("#btnSelectNum").click()

        # 3. Check if any games were added
        total_games = len(manual_numbers) + auto_games
        if total_games == 0:
            print('No games to purchase!')
            return {"processed_count": 0}

        # 4. Purchase
        sr.stage("PURCHASE")
        print("Clicking 'Purchase' (구매하기)...")
        page.locator("#btnBuy").click()
        
        # 5. Confirm purchase popup
        print("Confirming final purchase...")
        # Mobile uses #popupLayerConfirm or standard alert
        confirm_btn = page.locator("#popupLayerConfirm").get_by_role("button", name="확인")
        if confirm_btn.is_visible(timeout=2000):
            confirm_btn.click()
        else:
            # Fallback to general alert handling (automated by page.on("dialog"))
            pass

        time.sleep(2)
        print(f'Lotto 6/45: All {total_games} games purchased successfully!')
        return {"processed_count": total_games}


    finally:
        # Cleanup
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
