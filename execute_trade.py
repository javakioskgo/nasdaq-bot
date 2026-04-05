from telegram_notifier import send_telegram_message, format_message

import json
from datetime import datetime

from config import DRY_RUN
from ibkr_client import IBKRClient
from state_manager import is_already_executed_today, mark_execution

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def notify_step(title, lines):
    message = format_message(title, lines)
    send_telegram_message(message)


def notify_error(error_text, target_name="UNKNOWN", current_symbol="UNKNOWN"):
    message = format_message(
        "자동매매 오류",
        [
            f"추천 종목: {target_name}",
            f"현재 보유: {current_symbol}",
            f"오류 내용: {error_text}",
            f"DRY_RUN: {DRY_RUN}"
        ]
    )
    send_telegram_message(message)


def load_signal():
    with open("signal.json", "r", encoding="utf-8") as f:
        return json.load(f)


def extract_target_signal(signal_data):
    overseas = signal_data["markets"]["overseas"]
    return overseas["signal"], overseas["signal_display_name"]


def get_current_position_symbol(positions):
    if not positions:
        return "CASH"

    first_position = positions[0]
    return first_position.get("symbol", "CASH")


def main():
    target_symbol = "UNKNOWN"
    target_name = "UNKNOWN"
    current_symbol = "UNKNOWN"
    action_summary = "초기 상태"

    log("===== 자동매매 실행 시작 =====")

    signal_data = load_signal()
    target_symbol, target_name = extract_target_signal(signal_data)

    log(f"추천 결과: {target_name} ({target_symbol})")

    notify_step(
        "자동매매 실행 시작",
        [
            f"추천 종목: {target_name}",
            f"DRY_RUN: {DRY_RUN}"
        ]
    )

    client = IBKRClient()

    try:
        client.connect()

        positions = client.get_positions()
        current_symbol = get_current_position_symbol(positions)
        available_funds = client.get_available_funds()

        log(f"현재 보유: {current_symbol}")
        log(f"매수 가능 금액: ${available_funds}")

        if current_symbol == target_symbol:
            log("→ 현재 보유 종목과 추천 종목이 같음")
            log("→ 변경 없음 (HOLD)")
            action_summary = "HOLD"

        elif current_symbol != "CASH" and target_symbol == "CASH":
            log(f"→ {current_symbol} 전량 매도 필요")
            action_summary = f"{current_symbol} → CASH"

            if DRY_RUN:
                log("DRY_RUN: 매도 생략")
            else:
                sell_result = client.sell_all(current_symbol)
                log(f"매도 주문 접수: {sell_result}")

                fill_result = client.wait_until_filled(sell_result["order_id"])

                if not fill_result["filled"]:
                    log("❌ 매도 체결 실패 → 중단")
                    action_summary = "매도 실패"
                    notify_error("매도 체결 실패", target_name, current_symbol)
                    return

                log("✅ 매도 체결 완료")

                notify_step(
                    "매도 체결 완료",
                    [
                        f"매도 종목: {current_symbol}",
                        f"주문번호: {sell_result['order_id']}",
                        f"체결수량: {fill_result['filled_qty']}",
                        f"평균체결가: {fill_result['avg_price']}",
                        f"DRY_RUN: {DRY_RUN}"
                    ]
                )

        elif current_symbol == "CASH" and target_symbol != "CASH":
            log(f"→ {target_symbol} 신규 매수 필요")
            action_summary = f"CASH → {target_symbol}"

            if DRY_RUN:
                log("DRY_RUN: 매수 생략")
            else:
                buy_result = client.buy_max(target_symbol, available_funds)
                log(f"매수 주문 접수: {buy_result}")

                fill_result = client.wait_until_filled(buy_result["order_id"])

                if not fill_result["filled"]:
                    log("❌ 매수 체결 실패")
                    action_summary = "매수 실패"
                    notify_error("매수 체결 실패", target_name, current_symbol)
                    return

                log("✅ 매수 체결 완료")

                notify_step(
                    "매수 체결 완료",
                    [
                        f"매수 종목: {target_symbol}",
                        f"주문번호: {buy_result['order_id']}",
                        f"체결수량: {fill_result['filled_qty']}",
                        f"평균체결가: {fill_result['avg_price']}",
                        f"DRY_RUN: {DRY_RUN}"
                    ]
                )

        else:
            log(f"→ {current_symbol} → {target_symbol} 교체 필요")
            action_summary = f"{current_symbol} → {target_symbol}"

            if DRY_RUN:
                log("DRY_RUN: 매도/매수 생략")

            else:
                sell_result = client.sell_all(current_symbol)
                log(f"매도 주문 접수: {sell_result}")

                fill_result = client.wait_until_filled(sell_result["order_id"])

                if not fill_result["filled"]:
                    log("❌ 매도 체결 실패 → 중단")
                    action_summary = "매도 실패"
                    notify_error("매도 체결 실패", target_name, current_symbol)
                    return

                log("✅ 매도 체결 완료")

                notify_step(
                    "매도 체결 완료",
                    [
                        f"매도 종목: {current_symbol}",
                        f"주문번호: {sell_result['order_id']}",
                        f"체결수량: {fill_result['filled_qty']}",
                        f"평균체결가: {fill_result['avg_price']}",
                        "상태: 현금 반영 확인 중",
                        f"DRY_RUN: {DRY_RUN}"
                    ]
                )

                cash_result = client.wait_until_cash_ready()

                if not cash_result["cash_ready"]:
                    log("❌ 현금 반영 실패 → 중단")
                    action_summary = "현금 반영 실패"
                    notify_error("현금 반영 실패", target_name, current_symbol)
                    return

                new_funds = cash_result["available_funds"]
                log(f"현금 확인 완료: ${new_funds}")

                buy_result = client.buy_max(target_symbol, new_funds)
                log(f"매수 주문 접수: {buy_result}")

                fill_result = client.wait_until_filled(buy_result["order_id"])

                if not fill_result["filled"]:
                    log("❌ 매수 체결 실패")
                    action_summary = "매수 실패"
                    notify_error("매수 체결 실패", target_name, current_symbol)
                    return

                log("✅ 매수 체결 완료")

                notify_step(
                    "매수 체결 완료",
                    [
                        f"매수 종목: {target_symbol}",
                        f"주문번호: {buy_result['order_id']}",
                        f"체결수량: {fill_result['filled_qty']}",
                        f"평균체결가: {fill_result['avg_price']}",
                        f"사용 가능 금액: {new_funds}",
                        f"DRY_RUN: {DRY_RUN}"
                    ]
                )

    except Exception as e:
        log(f"❌ 에러 발생: {e}")
        action_summary = f"ERROR: {str(e)}"
        notify_error(str(e), target_name, current_symbol)

    finally:
        client.disconnect()

        log("===== 자동매매 종료 =====")

        message = format_message(
            "자동매매 실행 결과",
            [
                f"추천 종목: {target_name}",
                f"현재 보유: {current_symbol}",
                f"실행 결과: {action_summary}",
                f"DRY_RUN: {DRY_RUN}"
            ]
        )

        send_telegram_message(message)


if __name__ == "__main__":
    main()
