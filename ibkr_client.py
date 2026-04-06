import math
import time
from typing import List, Dict, Optional

from ib_insync import IB, Stock, MarketOrder


class IBKRClient:
    def __init__(self, host="127.0.0.1", port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self.connected = False

    def connect(self):
        if self.connected and self.ib.isConnected():
            print("이미 IBKR 연결됨")
            return True

        print(f"IBKR 연결 시도: {self.host}:{self.port}, client_id={self.client_id}")
        self.ib.connect(self.host, self.port, clientId=self.client_id)

        self.connected = self.ib.isConnected()
        print(f"IBKR 연결 성공: {self.connected}")
        return self.connected

    def disconnect(self):
        if self.ib.isConnected():
            print("IBKR 연결 종료")
            self.ib.disconnect()
        self.connected = False

    def _ensure_connected(self):
        if not self.connected or not self.ib.isConnected():
            raise RuntimeError("IBKR 연결 안됨")

    def _qualify_stock(self, symbol: str, exchange="SMART", currency="USD"):
        self._ensure_connected()

        contract = Stock(symbol, exchange, currency)
        qualified = self.ib.qualifyContracts(contract)

        if not qualified:
            raise RuntimeError(f"종목 계약 조회 실패: {symbol}")

        return contract

    def _get_account_summary_value(self, tag: str) -> Optional[str]:
        self._ensure_connected()

        summary = self.ib.accountSummary()
        for item in summary:
            if item.tag == tag:
                return item.value
        return None

    def get_available_funds(self):
        self._ensure_connected()

        print("매수 가능 금액 조회")
        value = self._get_account_summary_value("AvailableFunds")

        if value is None:
            raise RuntimeError("AvailableFunds 조회 실패")

        return float(value)

    def get_net_liquidation(self):
        self._ensure_connected()

        print("순자산 조회")
        value = self._get_account_summary_value("NetLiquidation")

        if value is None:
            raise RuntimeError("NetLiquidation 조회 실패")

        return float(value)

    def get_positions(self) -> List[Dict]:
        self._ensure_connected()

        print("현재 보유 종목 조회")
        positions = self.ib.positions()

        result = []
        for p in positions:
            result.append({
                "symbol": p.contract.symbol,
                "qty": p.position,
                "avg_cost": p.avgCost,
                "secType": p.contract.secType,
                "currency": p.contract.currency
            })

        return result

    def get_position_qty(self, symbol: str) -> int:
        self._ensure_connected()

        for p in self.ib.positions():
            if p.contract.symbol == symbol:
                return int(p.position)
        return 0

    def get_last_price(self, symbol: str) -> float:
        self._ensure_connected()

        contract = self._qualify_stock(symbol)
        ticker = self.ib.reqMktData(contract, "", False, False)

        for _ in range(10):
            self.ib.sleep(1)
            price = ticker.marketPrice()
            if price is not None and not math.isnan(price) and price > 0:
                print(f"{symbol} 현재가 조회 성공: {price}")
                return float(price)

        raise RuntimeError(f"{symbol} 현재가 조회 실패")

    def sell_all(self, symbol):
        self._ensure_connected()

        if not symbol or symbol == "CASH":
            raise ValueError("매도할 실제 종목이 없습니다.")

        qty = self.get_position_qty(symbol)
        if qty <= 0:
            raise ValueError(f"{symbol} 보유 수량이 없습니다.")

        contract = self._qualify_stock(symbol)
        order = MarketOrder("SELL", qty)

        print(f"{symbol} 전량 매도 주문: {qty}주")
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(1)

        order_id = trade.order.orderId if trade.order else None

        return {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": "SELL",
            "qty": qty,
            "trade": trade
        }

    def buy_max(self, symbol, available_funds, buy_buffer=0.995):
        self._ensure_connected()

        if not symbol or symbol == "CASH":
            raise ValueError("매수할 실제 종목이 없습니다.")

        if available_funds <= 0:
            raise ValueError("매수 가능 금액이 없습니다.")

        last_price = self.get_last_price(symbol)
        usable_funds = available_funds * buy_buffer
        qty = int(usable_funds // last_price)

        if qty <= 0:
            raise ValueError(
                f"매수 수량이 0주입니다. available_funds={available_funds}, "
                f"usable_funds={usable_funds}, last_price={last_price}"
            )

        contract = self._qualify_stock(symbol)
        order = MarketOrder("BUY", qty)

        print(
            f"{symbol} 최대 금액 매수 주문: usable_funds=${usable_funds:.2f}, "
            f"last_price=${last_price:.2f}, qty={qty}"
        )

        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(1)

        order_id = trade.order.orderId if trade.order else None

        return {
            "success": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": "BUY",
            "qty": qty,
            "last_price": last_price,
            "usable_funds": usable_funds,
            "trade": trade
        }

    def wait_until_filled(self, order_id, timeout=60, check_interval=2):
        self._ensure_connected()

        print(f"체결 대기 시작: {order_id}")
        elapsed = 0

        while elapsed < timeout:
            self.ib.sleep(check_interval)
            elapsed += check_interval

            open_trades = self.ib.openTrades()
            target_trade = None

            for t in open_trades:
                if t.order and t.order.orderId == order_id:
                    target_trade = t
                    break

            if target_trade is None:
                fills = self.ib.fills()
                matched_fill = None

                for f in fills:
                    if f.execution.orderId == order_id:
                        matched_fill = f

                if matched_fill:
                    print("체결 완료")
                    return {
                        "success": True,
                        "order_id": order_id,
                        "filled": True,
                        "filled_qty": matched_fill.execution.shares,
                        "avg_price": matched_fill.execution.price,
                        "filled_at_sec": elapsed
                    }

                print(f"체결 확인 중... ({elapsed}s) - openTrades 없음, fills 재확인 중")
            else:
                status = target_trade.orderStatus.status
                filled_qty = target_trade.orderStatus.filled
                avg_fill_price = target_trade.orderStatus.avgFillPrice

                print(
                    f"체결 확인 중... ({elapsed}s) "
                    f"status={status}, filled={filled_qty}, avg={avg_fill_price}"
                )

                if status in ("Filled",):
                    print("체결 완료")
                    return {
                        "success": True,
                        "order_id": order_id,
                        "filled": True,
                        "filled_qty": filled_qty,
                        "avg_price": avg_fill_price,
                        "filled_at_sec": elapsed
                    }

                if status in ("Cancelled", "Inactive", "ApiCancelled"):
                    return {
                        "success": False,
                        "order_id": order_id,
                        "filled": False,
                        "filled_qty": filled_qty,
                        "avg_price": avg_fill_price,
                        "filled_at_sec": elapsed,
                        "status": status
                    }

        print("체결 대기 타임아웃")
        return {
            "success": False,
            "order_id": order_id,
            "filled": False,
            "filled_qty": 0,
            "avg_price": 0.0,
            "filled_at_sec": timeout,
            "status": "TIMEOUT"
        }

    def wait_until_cash_ready(self, timeout=30, check_interval=2):
        self._ensure_connected()

        print("현금 반영 대기 시작")
        elapsed = 0

        while elapsed < timeout:
            self.ib.sleep(check_interval)
            elapsed += check_interval

            try:
                funds = self.get_available_funds()
                print(f"현금 반영 확인 중... ({elapsed}s) available_funds={funds}")

                if funds > 0:
                    print("현금 반영 확인 완료")
                    return {
                        "success": True,
                        "cash_ready": True,
                        "available_funds": funds,
                        "checked_at_sec": elapsed
                    }

            except Exception as e:
                print(f"현금 반영 확인 중 오류: {e}")

        print("현금 반영 대기 타임아웃")
        return {
            "success": False,
            "cash_ready": False,
            "available_funds": 0.0,
            "checked_at_sec": timeout
        }
