import json
from datetime import datetime

from config import DRY_RUN


def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def load_signal():
    with open("signal.json", "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    log("===== 자동매매 실행 시작 =====")

    signal_data = load_signal()

    # 네 구조에 맞게 수정 가능
    overseas = signal_data["markets"]["overseas"]

    target = overseas["signal"]
    target_name = overseas["signal_display_name"]

    log(f"추천 결과: {target_name} ({target})")

    # 현재는 테스트 모드
    if DRY_RUN:
        log("DRY_RUN 모드: 실제 주문은 실행하지 않음")

        # 가짜 현재 상태
        current_position = "CASH"

        log(f"현재 보유: {current_position}")

        if current_position == target:
            log("→ 변경 없음 (HOLD)")

        elif current_position != "CASH" and target == "CASH":
            log("→ 전량 매도 예정")

        elif current_position == "CASH" and target != "CASH":
            log(f"→ {target} 매수 예정 (최대 금액)")

        else:
            log(f"→ {current_position} 매도 후 {target} 매수 예정")

    log("===== 자동매매 종료 =====")


if __name__ == "__main__":
    main()
