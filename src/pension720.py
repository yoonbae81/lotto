#!/usr/bin/env python3
import time
from os import environ
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page, Playwright, sync_playwright

from login import (
    click_first_available,
    DEFAULT_HEADERS,
    DEFAULT_USER_AGENT,
    DEFAULT_VIEWPORT,
    dismiss_popups,
    GLOBAL_TIMEOUT,
    get_amount_from_text,
    SESSION_PATH,
    login,
    setup_dialog_handler,
    wait_for_text_markers,
)

import sys
import traceback
from script_reporter import ScriptReporter

# .env loading is handled by login module import


def get_visible_result_text(page: Page) -> str:
    """
    구매 결과 팝업/페이지에 노출된 텍스트를 수집합니다.
    """
    selectors = [
        "#popupLayerAlert",
        "#popupLayerConfirm",
        ".popup_layer",
        ".popup_wrap",
        ".layer_popup",
        "#result",
        "#report",
    ]

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=1000):
                return locator.inner_text().strip()
        except Exception:
            continue

    try:
        return page.locator("body").inner_text()
    except Exception:
        return ""


def is_purchase_success(result_text: str) -> bool:
    success_markers = [
        "연금복권720+ 구매완료",
        "구매가 완료되었습니다",
        "구매를 완료하였습니다",
        "구매완료",
        "구매 완료",
    ]
    return any(marker in result_text for marker in success_markers)


def detect_failure_reason(result_text: str) -> Optional[str]:
    failure_markers = {
        "low_balance": ["예치금이 부족", "잔액이 부족"],
        "limit_reached": ["구매한도", "한도 초과"],
        "invalid_selection": ["선택된 번호가 없습니다", "번호를 선택", "선택해 주세요"],
        "sold_out": ["판매가 마감", "구매 가능 시간이 아닙니다", "판매시간이 아닙니다"],
    }

    for reason, markers in failure_markers.items():
        if any(marker in result_text for marker in markers):
            return reason

    if "연금복권720+ 구매하기" in result_text and "구매가 완료되었습니다" not in result_text:
        compact_text = result_text.replace("\n", " ")
        if "보유중인 예치금 0원" in compact_text:
            return "low_balance"
        return "purchase_not_completed"

    return None


def run(playwright: Playwright, sr: ScriptReporter) -> dict:
    """
    연금복권 720+를 구매합니다.
    '모든 조'를 선택하여 임의의 번호로 5매(5,000원)를 구매합니다.
    """
    GAME_URL = "https://el.dhlottery.co.kr/game_mobile/pension720/game.jsp"
    
    # Create browser, context, and page
    HEADLESS = environ.get('HEADLESS', 'true').lower() == 'true'
    browser = playwright.chromium.launch(headless=HEADLESS)

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
        print(f"Navigating to Pension 720 game: {GAME_URL}")
        try:
            # Use domcontentloaded for faster loading
            page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
            
            # Final check if redirected
            if "/login" in page.url or "method=login" in page.url:
                print("Session lost during navigation. Re-logging in...")
                login(page)
                page.goto(GAME_URL, timeout=GLOBAL_TIMEOUT, wait_until="domcontentloaded")
        except Exception as e:
            print(f"Navigation failed: {e}")
            page.screenshot(path=f"pension720_nav_failed_{int(time.time())}.png")
            raise e

        # Give a small moment for components to initialize
        time.sleep(1)
        dismiss_popups(page)
        
        # 3. Purchase Flow
        sr.stage("PURCHASE_PROCESS")
        
        # Step 1: Open Number Selection
        print("Opening selection options...")
        try:
            click_first_available(
                page,
                [
                    "a.btn_gray_st1.large.full:has-text('번호 선택하기')",
                    "a:has-text('+ 번호 선택하기')",
                    "a:has-text('번호 선택하기')",
                ],
                "Pension 720 selection button",
            )
            page.wait_for_selector("#popup4", state="visible", timeout=GLOBAL_TIMEOUT)
        except Exception as e:
            print(f"Selection button not found/clickable: {e}")
            page.screenshot(path=f"pension720_select_btn_failed_{int(time.time())}.png")
            raise e
        
        time.sleep(1) # Wait for animation

        # Step 2: Ensure 'All Jo' is selected & Click Automatic
        print("Ensuring 'All Jo' (모든조) is selected and clicking 'Automatic' (자동번호)...")
        try:
            # Select 'All Jo'
            all_jo = page.locator("#popup4 span.group.all, #popup4 .selGroup, #popup4 .group.all").first
            if all_jo.is_visible(timeout=2000):
                all_jo.click()
                time.sleep(0.3)
            
            # Click 'Automatic'
            click_first_available(
                page,
                [
                    "#popup4 a.btn_wht.xsmall:has-text('자동번호')",
                    "#popup4 a:has-text('자동번호')",
                ],
                "Pension 720 auto number button",
            )

            wait_for_text_markers(page, ["통신중입니다"], timeout=1500)
            page.wait_for_function(
                """
                () => {
                    const popup = document.querySelector('#popup4');
                    return !!popup && /\\d/.test(popup.innerText || '');
                }
                """,
                timeout=5000,
            )
            time.sleep(0.5)
        except Exception as e:
            print(f"Automatic selection failed: {e}")
            page.screenshot(path=f"pension720_auto_failed_{int(time.time())}.png")
            raise e
        
        # Step 3: Confirm Selection
        print("Confirming selection...")
        click_first_available(
            page,
            [
                "#popup4 a.btn_blue.full.large:has-text('선택완료')",
                "#popup4 a:has-text('선택완료')",
            ],
            "Pension 720 selection confirm button",
        )
        time.sleep(0.8)
        page.wait_for_selector("#popup4", state="hidden", timeout=GLOBAL_TIMEOUT)

        body_text = page.locator("body").inner_text()
        scheduled_amount = get_amount_from_text(body_text, "결제 예정 금액")
        selected_count = page.locator("text='삭제'").count()
        if scheduled_amount != 5000 or selected_count < 5:
            page.screenshot(path=f"pension720_selection_invalid_{int(time.time())}.png")
            raise RuntimeError(
                f"Selection did not settle correctly. amount={scheduled_amount}, selected_count={selected_count}"
            )

        # Step 4: Final Purchase
        print("Clicking 'Purchase' (구매하기)...")
        click_first_available(
            page,
            [
                "a.btn_blue.large.full:has-text('구매하기')",
                "a:has-text('구매하기')",
            ],
            "Pension 720 buy button",
        )

        # Step 5: Verify Result
        sr.stage("VERIFY_RESULT")
        print("Verifying success...")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        try:
            page.wait_for_function(
                """
                () => {
                    const text = document.body ? document.body.innerText : "";
                    const selectors = ["#popupLayerAlert", "#popupLayerConfirm", ".popup_layer", ".popup_wrap", ".layer_popup", "#result", "#report"];
                    const markers = [
                        "연금복권720+ 구매완료",
                        "구매가 완료되었습니다",
                        "구매를 완료하였습니다",
                        "예치금이 부족",
                        "잔액이 부족",
                        "구매한도",
                        "선택된 번호가 없습니다",
                        "번호를 선택",
                        "판매시간",
                        "판매가 마감",
                        "주문번호",
                    ];
                    return selectors.some((selector) => {
                        const el = document.querySelector(selector);
                        return el && el.offsetParent !== null;
                    }) || markers.some((marker) => text.includes(marker));
                }
                """,
                timeout=30000,
            )
        except Exception as e:
            print(f"Result UI did not appear in time: {e}")
            page.screenshot(path=f"pension720_verify_failed_{int(time.time())}.png")
            return {"processed_count": 0, "status": "unknown", "reason": "result_timeout"}

        page.screenshot(path=f"pension720_result_{int(time.time())}.png")
        result_text = get_visible_result_text(page)
        print(f"Result text: {result_text}")

        failure_reason = detect_failure_reason(result_text)
        if failure_reason:
            print(f"Pension 720 purchase failed: {failure_reason}")
            return {"processed_count": 0, "status": "failed", "reason": failure_reason, "message": result_text}

        if is_purchase_success(result_text):
            final_confirm = page.locator(
                "#popupLayerAlert button:has-text('확인'), #popupLayerConfirm button:has-text('확인'), a.btn_lgray.medium:has-text('확인'), a.btn_blue:has-text('확인'), a:has-text('확인')"
            ).first
            try:
                if final_confirm.is_visible(timeout=2000):
                    final_confirm.click()
            except Exception as e:
                print(f"Final confirm click skipped: {e}")

            print("Pension 720: Purchase success confirmed by result UI.")
            return {"processed_count": 5, "status": "success", "message": result_text}

        print("Purchase result ambiguous.")
        return {"processed_count": 0, "status": "ambiguous", "message": result_text}

    except Exception as e:
        print(f"Purchase flow interrupted: {e}")
        try:
            page.screenshot(path=f"pension720_error_{int(time.time())}.png")
        except:
             pass
        raise
    finally:
        context.close()
        browser.close()

if __name__ == "__main__":
    sr = ScriptReporter("Pension 720")
    try:
        with sync_playwright() as playwright:
            process_result = run(playwright, sr)
            if process_result.get("status") == "success":
                sr.success(process_result)
            else:
                sr.fail(f"Purchase failed or status unknown: {process_result}")
                sys.exit(1)
    except Exception:
        sr.fail(traceback.format_exc())
        sys.exit(1)
