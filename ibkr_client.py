import time


class IBKRClient:
    def __init__(self):
        self.connected = False

    def connect(self):
        print("IBKR 연결 시도")
        self.connected = True
        return True

    def disconnect(self):
        if self.connected:
            print("IBKR 연결 종료")
        self.connected = False

    def get_available_funds(self):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")

        print("매수 가능 금액 조회")
        # 현재는 테스트용 가짜 값
        return 10000.0

    def get_positions(self):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")

        print("현재 보유 종목 조회")

        # 현재는 테스트용 가짜 데이터
        # 예:
        # return [{"symbol": "SOXL", "qty": 100}]
        return []

    def sell_all(self, symbol):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")

        if not symbol or symbol == "CASH":
            raise ValueError("매도할 실제 종목이 없습니다.")

        print(f"{symbol} 전량 매도 주문")

        # 현재는 테스트용 가짜 응답
        return {
            "success": True,
            "order_id": f"SELL-{symbol}-001",
            "symbol": symbol,
            "side": "SELL"
        }

    def buy_max(self, symbol, available_funds):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")

        if not symbol or symbol == "CASH":
            raise ValueError("매수할 실제 종목이 없습니다.")

        if available_funds <= 0:
            raise ValueError("매수 가능 금액이 없습니다.")

        print(f"{symbol} 최대 금액 매수 주문: ${available_funds}")

        # 현재는 테스트용 가짜 응답
        return {
            "success": True,
            "order_id": f"BUY-{symbol}-001",
            "symbol": symbol,
            "side": "BUY",
            "available_funds_used": available_funds
        }

    def wait_until_filled(self, order_id, timeout=60, check_interval=2):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")

        print(f"체결 대기 시작: {order_id}")

        elapsed = 0

        while elapsed < timeout:
            time.sleep(check_interval)
            elapsed += check_interval

            print(f"체결 확인 중... ({elapsed}s)")

            # 현재는 테스트용으로 체결 완료 처리
            filled = True

            if filled:
                print("체결 완료")
                return {
                    "success": True,
                    "order_id": order_id,
                    "filled": True,
                    "filled_qty": 100,
                    "avg_price": 50.0,
                    "filled_at_sec": elapsed
                }

        print("체결 대기 타임아웃")
        return {
            "success": False,
            "order_id": order_id,
            "filled": False,
            "filled_qty": 0,
            "avg_price": 0.0,
            "filled_at_sec": timeout
        }

    def wait_until_cash_ready(self, timeout=30, check_interval=2):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")

        print("현금 반영 대기 시작")

        elapsed = 0

        while elapsed < timeout:
            time.sleep(check_interval)
            elapsed += check_interval

            print(f"현금 반영 확인 중... ({elapsed}s)")

            # 현재는 테스트용으로 바로 반영 완료 처리
            cash_ready = True

            if cash_ready:
                funds = self.get_available_funds()
                print("현금 반영 확인 완료")
                return {
                    "success": True,
                    "cash_ready": True,
                    "available_funds": funds,
                    "checked_at_sec": elapsed
                }

        print("현금 반영 대기 타임아웃")
        return {
            "success": False,
            "cash_ready": False,
            "available_funds": 0.0,
            "checked_at_sec": timeout
        }
