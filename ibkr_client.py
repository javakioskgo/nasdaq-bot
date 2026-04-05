class IBKRClient:
    def __init__(self):
        self.connected = False

    def connect(self):
        print("IBKR 연결 시도")
        self.connected = True
        return True

    def disconnect(self):
        print("IBKR 연결 종료")
        self.connected = False

    def get_available_funds(self):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")
        print("매수 가능 금액 조회")
        return 10000.0

    def get_positions(self):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")
        print("현재 보유 종목 조회")
        return []

    def sell_all(self, symbol):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")
        print(f"{symbol} 전량 매도 주문")
        return {"success": True, "order_id": "SELL-001"}

    def buy_max(self, symbol, available_funds):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")
        print(f"{symbol} 최대 금액 매수 주문: ${available_funds}")
        return {"success": True, "order_id": "BUY-001"}

    def wait_until_filled(self, order_id):
        if not self.connected:
            raise RuntimeError("IBKR 연결 안됨")
        print(f"주문 체결 대기: {order_id}")
        return {
            "success": True,
            "order_id": order_id,
            "filled": True,
            "filled_qty": 100,
            "avg_price": 50.0
        }
