#!/usr/bin/env python3
import json
import re
import sys
import time
from os import environ
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright
from login import login

# .env loading is handled by login module import


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
                print(f"ℹ️  Auto mode: {auto_games} game(s) (₩{amount:,})")
                return auto_games, []
            else:
                print(f"❌ Error: Invalid amount '{args[0]}'")
                print(f"Valid amounts: 1000, 2000, 3000, 4000, 5000")
                sys.exit(1)
        except ValueError:
            print(f"❌ Error: Invalid amount format '{args[0]}'")
            sys.exit(1)
    
    # Case 2: Six arguments (manual number selection)
    elif len(args) == 6:
        try:
            numbers = [int(arg) for arg in args]
            
            # Validate: all numbers must be 1-45
            if not all(1 <= n <= 45 for n in numbers):
                print(f"❌ Error: All numbers must be between 1 and 45")
                print(f"Provided: {numbers}")
                sys.exit(1)
            
            # Validate: no duplicates
            if len(numbers) != len(set(numbers)):
                print(f"❌ Error: Numbers must not contain duplicates")
                print(f"Provided: {numbers}")
                sys.exit(1)
            
            # Sort numbers for display
            sorted_numbers = sorted(numbers)
            print(f"ℹ️  Manual mode: {sorted_numbers}")
            return 0, [numbers]
            
        except ValueError:
            print(f"❌ Error: All arguments must be numbers")
            print(f"Provided: {args}")
            sys.exit(1)
    
    else:
        print(f"❌ Error: Invalid number of arguments")
        print(f"\nUsage:")
        print(f"  Auto games:   ./lotto645.py [AMOUNT]")
        print(f"                where AMOUNT is 1000, 2000, 3000, 4000, or 5000")
        print(f"  Manual game:  ./lotto645.py [N1] [N2] [N3] [N4] [N5] [N6]")
        print(f"                where each N is a number from 1 to 45 (no duplicates)")
        print(f"\nExamples:")
        print(f"  ./lotto645.py 3000          # Buy 3 auto games")
        print(f"  ./lotto645.py 1 2 3 4 5 6   # Buy 1 manual game with numbers 1,2,3,4,5,6")
        sys.exit(1)


def run(playwright: Playwright, auto_games: int, manual_numbers: list) -> None:
    """
    로또 6/45를 자동 및 수동으로 구매합니다.
    
    Args:
        playwright: Playwright 객체
        auto_games: 자동 구매 게임 수
        manual_numbers: 수동 구매 번호 리스트 (예: [[1,2,3,4,5,6], ...])
    """
    # Create browser, context, and page
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    # Perform login
    try:
        login(page)

        # Navigate to game page
        page.goto(url="https://ol.dhlottery.co.kr/olotto/game/game645.do", timeout=30000, wait_until="domcontentloaded")
        print('✅ Navigated to Lotto 6/45 page')

        # Wait for page to be fully loaded
        page.wait_for_load_state("networkidle")
        
        # Remove all intercepting pause layer popups using JavaScript
        # These elements block clicks even when they're not supposed to be visible
        page.evaluate("""
            () => {
                // Hide all known pause layer elements
                const selectors = [
                    '#pause_layer_pop_02',
                    '#ele_pause_layer_pop02',
                    '.pause_layer_pop',
                    '.pause_bg'
                ];
                
                selectors.forEach(selector => {
                    const elements = document.querySelectorAll(selector);
                    elements.forEach(el => {
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                        el.style.pointerEvents = 'none';
                    });
                });
            }
        """)
        
        # Dismiss popup if present - use force to bypass any remaining intercepting elements
        try:
            popup_alert = page.locator("#popupLayerAlert")
            if popup_alert.is_visible(timeout=2000):
                # Click the confirmation button with force
                popup_alert.get_by_role("button", name="확인").click(force=True, timeout=5000)
                print('✅ Dismissed popup alert')
        except Exception as e:
            # If popup handling fails, log but continue
            print(f'⚠️  Popup handling: {str(e)}')

        # Manual numbers
        if manual_numbers and len(manual_numbers) > 0:
            for game in manual_numbers:
                for number in game:
                    page.click(f'label[for="check645num{number}"]', force=True)
                page.click("#btnSelectNum")
                print(f'✅ Manual game added: {game}')

        # Automatic games
        if auto_games > 0:
            page.click("#num2") 
            page.select_option("#amoundApply", str(auto_games))
            page.click("#btnSelectNum")
            print(f'✅ Automatic game(s) added: {auto_games}')

        # Check if any games were added
        total_games = len(manual_numbers) + auto_games
        if total_games == 0:
            print('⚠️  No games to purchase!')
            return

        # Verify payment amount
        time.sleep(1)
        payment_amount_el = page.locator("#payAmt")
        payment_text = payment_amount_el.inner_text().strip()
        payment_amount = int(re.sub(r'[^0-9]', '', payment_text))
        expected_amount = total_games * 1000
        
        if payment_amount != expected_amount:
            print(f'❌ Error: Payment mismatch (Expected {expected_amount}, Displayed {payment_amount})')
            return
        
        # Purchase
        page.click("#btnBuy")
        
        # Confirm purchase popup
        page.click("#popupLayerConfirm input[value='확인']")
        
        # Check for purchase limit alert or recommendation popup AFTER confirmation
        # Wait enough time for popup to appear (network lag handling)
        time.sleep(3)
        
        # 1. Check for specific limit exceeded recommendation popup
        limit_popup = page.locator("#recommend720Plus")
        if limit_popup.is_visible():
            print("❌ Error: Weekly purchase limit exceeded (detected limit popup).")
            # Try to find error message inside
            content = limit_popup.locator(".cont1").inner_text()
            print(f"   Message: {content.strip()}")
            return

        print(f'✅ Lotto 6/45: All {total_games} games purchased successfully!')

    finally:
        # Cleanup
        context.close()
        browser.close()


if __name__ == "__main__":
    # Parse command-line arguments or use .env configuration
    auto_games, manual_numbers = parse_arguments()
    
    with sync_playwright() as playwright:
        run(playwright, auto_games, manual_numbers)
