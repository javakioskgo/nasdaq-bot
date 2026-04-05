from telegram_notifier import send_telegram_message, format_message

import json
from datetime import datetime

from config import DRY_RUN
from ibkr_client import IBKRClient


def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


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
    action_summary = "아직 판단 전"

    log("===== 자동매매 실행 시작 =====")

    signal_data = load_signal()
    target_symbol, target_name = extract_target_signal(signal_data)

    log(f"추천 결과: {target_name} ({target_symbol})")

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
            action_summary = "변경 없음 (HOLD)"

        elif current_symbol != "CASH" and target_symbol == "CASH":
            log(f"→ {current_symbol} 전량 매도 필요")
            action_summary = f"{current_symbol} 전량 매도 필요"

            if DRY_RUN:
                log("DRY_RUN 모드: 실제 매도 주문은 실행하지 않음")
            else:
                sell_result = client.sell_all(current_symbol)
                log(f"매도 주문 접수: {sell_result}")

        elif current_symbol == "CASH" and target_symbol != "CASH":
            log(f"→ {target_symbol} 신규 매수 필요")
            action_summary = f"{target_symbol} 신규 매수 필요"

            if DRY_RUN:
                log("DRY_RUN 모드: 실제 매수 주문은 실행하지 않음")
            else:
                buy_result = client.buy_max(target_symbol, available_funds)
                log(f"매수 주문 접수: {buy_result}")

        else:
            log(f"→ {current_symbol} 보유 중, 목표 종목은 {target_symbol}")
            log("→ 기존 종목 매도 후 새 종목 매수 필요")
            action_summary = f"{current_symbol} 매도 후 {target_symbol} 매수 필요"

            if DRY_RUN:
                log("DRY_RUN 모드: 실제 매도/매수 주문은 실행하지 않음")
            else:
                sell_result = client.sell_all(current_symbol)
                log(f"매도 주문 접수: {sell_result}")
                log("현금 반영 확인 후 매수 진행 예정")

    finally:
        client.disconnect()

        log("===== 자동매매 종료 =====")

        message = format_message(
            "자동매매 실행 결과",
            [
                f"추천 종목: {target_name}",
                f"현재 보유: {current_symbol}",
                f"판단 결과: {action_summary}",
                f"DRY_RUN: {DRY_RUN}"
            ]
        )

        send_telegram_message(message)


if __name__ == "__main__":
    main()
