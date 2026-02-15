#!/usr/bin/env python3
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import Playwright, sync_playwright, Page
from login import login, SESSION_PATH, DEFAULT_USER_AGENT, DEFAULT_VIEWPORT, DEFAULT_HEADERS, GLOBAL_TIMEOUT

import traceback
from script_reporter import ScriptReporter

# .env loading is handled by login module import

CHARGE_PIN = os.environ.get('CHARGE_PIN')

def parse_keypad(page: Page) -> dict:
    """
    랜덤 키패드 이미지를 OCR로 분석하여 각 숫자의 위치를 파악합니다.
    
    키패드 구조:
    - 숫자 0-9: 10개
    - 전체삭제: 1개
    - 백스페이스: 1개
    - 총 12개 버튼
    
    Args:
        page: Playwright Page 객체
        
    Returns:
        dict: {숫자(str): element} 형태의 버튼 매핑 (0-9만 포함)
    """
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    import io

    # Tesseract 경로 설정
    tesseract_cmd = os.environ.get('TESSERACT_PATH')
    if not tesseract_cmd:
        common_paths = ["/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract", "/usr/bin/tesseract"]
        for path in common_paths:
            if os.path.exists(path):
                tesseract_cmd = path
                break
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    keypad_selector = ".nppfs-keypad"
    try:
        page.wait_for_selector(keypad_selector, state="visible", timeout=GLOBAL_TIMEOUT)
    except Exception:
        raise Exception("Keypad not visible")
    
    # 버튼 위치 정보 수집
    buttons = page.locator("img.kpd-data")
    count = buttons.count()
    if count == 0:
        raise Exception("No keypad buttons found")

    button_positions = []
    for i in range(count):
        btn = buttons.nth(i)
        box = btn.bounding_box()
        if box and box['width'] > 0:
            button_positions.append({'element': btn, 'x': box['x'], 'y': box['y'], 'w': box['width'], 'h': box['height']})

    # 전체 키패드 영역 스크린샷
    time.sleep(0.3) # 애니메이션 대기 시간 단축
    keypad_layer = page.locator(keypad_selector)
    keypad_box = keypad_layer.bounding_box()
    screenshot_bytes = page.screenshot(clip=keypad_box)
    keypad_img = Image.open(io.BytesIO(screenshot_bytes))

    number_map = {}
    button_positions.sort(key=lambda b: (b['y'], b['x']))

    for idx, btn_info in enumerate(button_positions):
        lx = btn_info['x'] - keypad_box['x']
        ly = btn_info['y'] - keypad_box['y']
        button_img = keypad_img.crop((lx, ly, lx + btn_info['w'], ly + btn_info['h']))
        
        # 전처리: 흑백 변환 및 대비 향상
        gray = button_img.convert('L')
        enhanced = ImageEnhance.Contrast(gray).enhance(2.0)
        binary = enhanced.point(lambda p: p > 128 and 255)
        
        # OCR (가장 효율적인 설정부터 시도)
        configs = [r'--oem 3 --psm 10 -c tessedit_char_whitelist=0123456789', r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789']
        
        found_text = None
        for config in configs:
            result = pytesseract.image_to_string(binary, config=config).strip()
            if result.isdigit() and len(result) == 1:
                found_text = result
                break
        
        if found_text and found_text not in number_map:
            number_map[found_text] = btn_info['element']

    print(f"Keypad mapping: {sorted(number_map.keys())}")
    return number_map

def charge_deposit(page: Page, amount: int) -> bool:
    """
    [간편충전] 기능을 사용하여 예치금을 충전합니다.
    """
    if not CHARGE_PIN:
        print("Error: CHARGE_PIN not found")
        return False

    print(f"Navigating to charge page for {amount:,} won...")
    page.goto("https://m.dhlottery.co.kr/mypage/mndpChrg", timeout=GLOBAL_TIMEOUT, wait_until="networkidle")
    
    if "/login" in page.url:
        login(page)
        page.goto("https://m.dhlottery.co.kr/mypage/mndpChrg", timeout=GLOBAL_TIMEOUT, wait_until="networkidle")

    # 충전 금액 선택
    amount_map = {5000: "5,000", 10000: "10,000", 20000: "20,000", 30000: "30,000", 50000: "50,000"}
    if amount not in amount_map:
        print(f"Error: Invalid amount {amount}")
        return False
        
    page.select_option("select#EcAmt", label=f"{amount_map[amount]}원")
    
    # 충전하기 버튼 클릭
    print("Clicking charge button...")
    page.click("button.btn-rec01:visible", timeout=GLOBAL_TIMEOUT)
    
    # PIN 키패드 대기
    try:
        page.wait_for_selector(".nppfs-keypad", state="visible", timeout=GLOBAL_TIMEOUT)
    except:
        print("Keypad did not appear.")
        return False

    number_map = parse_keypad(page)
    if len(number_map) < 10:
        print(f"Keypad recognition incomplete ({len(number_map)}/10). Retrying crop logic...")
        # (Optinal: 추가 로직 넣을 수 있음)
        
    print(f"Entering PIN...")
    for digit in CHARGE_PIN:
        if digit in number_map:
            number_map[digit].click()
            time.sleep(0.1) # 속도 향상
        else:
            print(f"Digit {digit} not found")
            return False
            
    print("PIN entered. Waiting for confirmation...")
    
    # 결과 확인 로직 강화
    try:
        # 1. URL 변화 확인 (result=OK)
        # 2. 완료 팝업 확인 (#btnAlertPop)
        success_selector = "button#btnAlertPop, .btn_confirm, text='완료되었습니다', text='OK'"
        page.wait_for_selector(success_selector, state="visible", timeout=20000)
        
        msg = page.locator("body").inner_text()
        if "완료" in msg or "result=OK" in page.url:
            print("Charge success confirmed by UI!")
            # 팝업 닫기 시도
            if page.locator("button#btnAlertPop").is_visible():
                page.click("button#btnAlertPop")
            return True
        else:
            print(f"Unexpected message or state: {page.url}")
            return False
    except Exception as e:
        print(f"Verification timed out or failed: {e}")
        # URL이라도 확인
        if "result=OK" in page.url:
            print("Charge likely successful (URL result=OK)")
            return True
        return False

def run(playwright: Playwright, amount: int, sr: ScriptReporter):
    HEADLESS = os.environ.get('HEADLESS', 'false').lower() == 'true'
    
    browser = playwright.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 200)
    storage_state = SESSION_PATH if Path(SESSION_PATH).exists() else None
    context = browser.new_context(
        storage_state=storage_state,
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT,
        extra_http_headers=DEFAULT_HEADERS
    )
    page = context.new_page()
    
    try:
        from login import is_logged_in, setup_dialog_handler
        setup_dialog_handler(page) # 알럿 자동 처리
        
        if not is_logged_in(page):
            sr.stage("LOGIN")
            login(page)
            
        sr.stage("CHARGE")
        success = charge_deposit(page, amount)
        
        if success:
            return True
        else:
            return False
    except Exception:
        raise
    finally:
        time.sleep(2) # 결과 확인용 대기
        context.close()
        browser.close()


if __name__ == "__main__":
    amount = 10000
    if len(sys.argv) > 1:
        try:
            amount = int(sys.argv[1].replace(',', ''))
        except ValueError:
            pass
            
    sr = ScriptReporter("Balance Charge")
    with sync_playwright() as playwright:
        try:
            success = run(playwright, amount, sr)
            if success:
                sr.success({"amount": amount})
                print("Final result: True")
                sys.exit(0)
            else:
                sr.fail("Charge failed verification")
                sys.exit(1)
        except Exception:
            sr.fail(traceback.format_exc())
            sys.exit(1)
