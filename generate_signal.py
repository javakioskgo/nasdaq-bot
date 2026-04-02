import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


# =========================
# 전략 파라미터
# =========================
SYMBOL = "QQQ"
DOWNLOAD_PERIOD = "6mo"
DOWNLOAD_INTERVAL = "1d"
MIN_REQUIRED_BARS = 25
CHART_BARS = 60

EMA_FAST_SPAN = 5
EMA_SLOW_SPAN = 20

EMERGENCY_DROP_PCT = -0.03          # 하루 -3% 이상 하락 시 긴급 피신
SIDEWAYS_SLOPE_PCT_THRESHOLD = 0.0005   # EMA20 하루 변화율이 0.05% 미만이면 약한 추세로 판단
SIDEWAYS_DISTANCE_THRESHOLD = 0.02      # 현재 종가가 EMA20과 2% 이내면 횡보 후보

DOWN_ACCEL_RATIO = 1.5              # EMA5 하락 속도가 EMA20보다 1.5배 이상 빠를 때
ABOVE_CONFIRM_BARS = 2              # 20EMA 위 연속 확인 봉 수
BELOW_CONFIRM_BARS = 2              # 20EMA 아래 연속 확인 봉 수
BELOW_LOOKBACK_BARS = 5             # 최근 5봉 확인
BELOW_REQUIRED_COUNT = 3            # 최근 5봉 중 3봉 이상 20EMA 아래


def main():
    df = yf.download(
        SYMBOL,
        period=DOWNLOAD_PERIOD,
        interval=DOWNLOAD_INTERVAL,
        auto_adjust=True,
        progress=False
    )

    if df.empty or len(df) < MIN_REQUIRED_BARS:
        raise ValueError(f"{SYMBOL} 데이터를 충분히 가져오지 못했습니다.")

    close = df["Close"].copy()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()

    if len(close) < MIN_REQUIRED_BARS:
        raise ValueError("유효한 종가 데이터가 충분하지 않습니다.")

    # =========================
    # 지표 계산
    # =========================
    ema5 = close.ewm(span=EMA_FAST_SPAN, adjust=False).mean()
    ema20 = close.ewm(span=EMA_SLOW_SPAN, adjust=False).mean()
    ema5_slope = ema5.diff()
    ema20_slope = ema20.diff()
    daily_return = close.pct_change()

    last_idx = close.index[-1]
    signal_date = pd.to_datetime(last_idx).strftime("%Y-%m-%d")
    today_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    generated_at_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S %Z")

    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    last_daily_return = float(daily_return.iloc[-1])

    last_ema5 = float(ema5.iloc[-1])
    prev_ema5 = float(ema5.iloc[-2])
    last_ema20 = float(ema20.iloc[-1])
    prev_ema20 = float(ema20.iloc[-2])

    last_ema5_slope = float(ema5_slope.iloc[-1])
    last_ema20_slope = float(ema20_slope.iloc[-1])

    # slope를 비율 기준으로도 계산
    ema5_slope_pct = last_ema5_slope / prev_ema5 if prev_ema5 != 0 else 0.0
    ema20_slope_pct = last_ema20_slope / prev_ema20 if prev_ema20 != 0 else 0.0

    # =========================
    # 조건 계산
    # =========================
    recent_above_close = close.iloc[-ABOVE_CONFIRM_BARS:]
    recent_above_ema20 = ema20.iloc[-ABOVE_CONFIRM_BARS:]
    cond_above_n = bool((recent_above_close > recent_above_ema20).all())

    recent_below_close = close.iloc[-BELOW_CONFIRM_BARS:]
    recent_below_ema20 = ema20.iloc[-BELOW_CONFIRM_BARS:]
    cond_below_n = bool((recent_below_close < recent_below_ema20).all())

    recent_lookback_close = close.iloc[-BELOW_LOOKBACK_BARS:]
    recent_lookback_ema20 = ema20.iloc[-BELOW_LOOKBACK_BARS:]
    below_lookback_count = int((recent_lookback_close <= recent_lookback_ema20).sum())

    cond_ema_cross = last_ema5 > last_ema20
    cond_ema20_up = last_ema20_slope > 0
    cond_ema5_up = last_ema5_slope > 0
    cond_ema20_down = last_ema20_slope < 0
    cond_ema5_down = last_ema5_slope < 0
    cond_emergency_exit = last_daily_return <= EMERGENCY_DROP_PCT
    cond_below_lookback_required = below_lookback_count >= BELOW_REQUIRED_COUNT

    # 횡보장 필터
    ema20_strength_abs = abs(last_ema20_slope)
    ema20_strength_pct = abs(ema20_slope_pct)
    price_distance = abs(last_close - last_ema20) / last_ema20 if last_ema20 != 0 else 0.0

    is_sideways = (
        ema20_strength_pct < SIDEWAYS_SLOPE_PCT_THRESHOLD and
        price_distance < SIDEWAYS_DISTANCE_THRESHOLD
    )

    # 하락 가속 조건
    down_acceleration_ratio = (
        abs(last_ema5_slope) / abs(last_ema20_slope)
        if abs(last_ema20_slope) > 0 else None
    )
    cond_down_acceleration = (
        down_acceleration_ratio is not None and
        down_acceleration_ratio >= DOWN_ACCEL_RATIO
    )

    # =========================
    # 최종 판단
    # =========================
    market_state = ""
    decision_path = []

    if cond_emergency_exit:
        signal = "CASH"
        market_state = "EMERGENCY_EXIT"
        reason = f"{SYMBOL} 전일 종가가 전일 대비 3% 이상 하락해 긴급 피신 조건이 발동했습니다."
        final_trigger = f"🚨 긴급 피신: {SYMBOL} 전일 -3% 급락 → CASH"
        decision_path.append("cond_emergency_exit=True")

    elif (
        cond_ema20_down and
        cond_ema5_down and
        cond_down_acceleration and
        cond_below_n and
        cond_below_lookback_required
    ):
        signal = "CASH"
        market_state = "DOWNTREND_CONFIRMED"
        reason = (
            "하락 전환 조건 충족: EMA5/EMA20 기울기 음수, 하락 가속, "
            f"20EMA 아래 {BELOW_CONFIRM_BARS}봉 + 최근 {BELOW_LOOKBACK_BARS}봉 중 "
            f"{BELOW_REQUIRED_COUNT}봉 이상 아래."
        )
        final_trigger = "📉 하락 전환 확정: EMA 하락 + 20EMA 아래 지속 → CASH"
        decision_path.extend([
            "cond_ema20_down=True",
            "cond_ema5_down=True",
            "cond_down_acceleration=True",
            "cond_below_n=True",
            "cond_below_lookback_required=True"
        ])

    elif is_sideways and last_ema20_slope < 0:
        signal = "CASH"
        market_state = "SIDEWAYS"
        reason = "하락 추세에서 횡보 구간으로 판단되어 관망합니다."
        final_trigger = "🟡 하락 횡보 → CASH"
        decision_path.append("is_sideways=True")

    elif cond_ema20_up and cond_ema5_up and cond_above_n:
        signal = "TQQQ"
        market_state = "UPTREND_RECOVERY"
        reason = (
            "상승 복귀 조건 충족: EMA5/EMA20 기울기 양수, "
            f"종가가 20EMA 위 {ABOVE_CONFIRM_BARS}봉 연속입니다."
        )
        final_trigger = "📈 상승 복귀 확인: EMA 기울기 양수 + 20EMA 위 연속 확인 → TQQQ"
        decision_path.extend([
            "cond_ema20_up=True",
            "cond_ema5_up=True",
            "cond_above_n=True"
        ])

    elif cond_ema_cross and cond_ema20_up:
        signal = "TQQQ"
        market_state = "EARLY_UPTREND"
        reason = "상승 초기 조건 충족: 5EMA > 20EMA, 20EMA 상승 시작."
        final_trigger = "📈 초기 상승 진입 → TQQQ"
        decision_path.extend([
            "cond_ema_cross=True",
            "cond_ema20_up=True"
        ])

    else:
        signal = "CASH"
        market_state = "UNCLEAR"
        reason = "추세가 명확하지 않아 관망합니다."
        final_trigger = "⚖️ 방향 불명확 → CASH"
        decision_path.append("fallback_to_cash=True")

    # =========================
    # 차트용 데이터
    # =========================
    recent_close = close.tail(CHART_BARS)
    ema5_recent = recent_close.ewm(span=EMA_FAST_SPAN, adjust=False).mean()
    ema20_recent = recent_close.ewm(span=EMA_SLOW_SPAN, adjust=False).mean()

    labels = [pd.to_datetime(idx).strftime("%m-%d") for idx in recent_close.index]
    close_data = [round(float(v), 2) for v in recent_close]
    ema5_data = [round(float(v), 2) for v in ema5_recent]
    ema20_data = [round(float(v), 2) for v in ema20_recent]

    # =========================
    # 디버깅 / 로그용 payload
    # =========================
    payload = {
    # 기존 HTML 호환용 키
    "today_date": today_date,
    "signal_date": signal_date,
    "signal": signal,
    "reason": reason,
    "final_trigger": final_trigger,
    "last_close": f"{last_close:,.2f}",
    "daily_return": f"{last_daily_return * 100:+.2f}%",
    "ema5": f"{last_ema5:,.2f}",
    "ema20": f"{last_ema20:,.2f}",
    "ema5_slope": f"{last_ema5_slope:+.4f}",
    "ema20_slope": f"{last_ema20_slope:+.4f}",
    "cond_ema_cross": cond_ema_cross,
    "cond_ema20_up": cond_ema20_up,
    "cond_ema5_up": cond_ema5_up,
    "cond_emergency_exit": cond_emergency_exit,
    "is_sideways": is_sideways,
    "labels": labels,
    "close_data": close_data,
    "ema5_data": ema5_data,
    "ema20_data": ema20_data,

    # 새 디버깅용 구조
    "meta": {
        "generated_at_kst": generated_at_kst,
        "today_date": today_date,
        "signal_date": signal_date,
        "symbol": SYMBOL,
        "download_period": DOWNLOAD_PERIOD,
        "download_interval": DOWNLOAD_INTERVAL,
        "data_points": int(len(close))
    },
    "strategy_params": {
        "EMA_FAST_SPAN": EMA_FAST_SPAN,
        "EMA_SLOW_SPAN": EMA_SLOW_SPAN,
        "EMERGENCY_DROP_PCT": EMERGENCY_DROP_PCT,
        "SIDEWAYS_SLOPE_PCT_THRESHOLD": SIDEWAYS_SLOPE_PCT_THRESHOLD,
        "SIDEWAYS_DISTANCE_THRESHOLD": SIDEWAYS_DISTANCE_THRESHOLD,
        "DOWN_ACCEL_RATIO": DOWN_ACCEL_RATIO,
        "ABOVE_CONFIRM_BARS": ABOVE_CONFIRM_BARS,
        "BELOW_CONFIRM_BARS": BELOW_CONFIRM_BARS,
        "BELOW_LOOKBACK_BARS": BELOW_LOOKBACK_BARS,
        "BELOW_REQUIRED_COUNT": BELOW_REQUIRED_COUNT
    },
    "signal_summary": {
        "signal": signal,
        "market_state": market_state,
        "reason": reason,
        "final_trigger": final_trigger,
        "decision_path": decision_path
    },
    "latest_price_info": {
        "last_close_raw": round(last_close, 2),
        "prev_close_raw": round(prev_close, 2),
        "daily_return_pct_raw": round(last_daily_return * 100, 2)
    },
    "latest_indicator_info": {
        "ema5_raw": round(last_ema5, 4),
        "ema20_raw": round(last_ema20, 4),
        "ema5_slope_raw": round(last_ema5_slope, 6),
        "ema20_slope_raw": round(last_ema20_slope, 6),
        "ema5_slope_pct": round(ema5_slope_pct * 100, 4),
        "ema20_slope_pct": round(ema20_slope_pct * 100, 4)
    },
    "condition_values": {
        "ema20_strength_abs": round(ema20_strength_abs, 6),
        "ema20_strength_pct": round(ema20_strength_pct * 100, 4),
        "price_distance_pct": round(price_distance * 100, 4),
        "below_lookback_count": below_lookback_count,
        "down_acceleration_ratio": round(down_acceleration_ratio, 4) if down_acceleration_ratio is not None else None
    },
    "conditions": {
        "cond_ema_cross": cond_ema_cross,
        "cond_ema20_up": cond_ema20_up,
        "cond_ema5_up": cond_ema5_up,
        "cond_ema20_down": cond_ema20_down,
        "cond_ema5_down": cond_ema5_down,
        "cond_emergency_exit": cond_emergency_exit,
        "cond_above_n": cond_above_n,
        "cond_below_n": cond_below_n,
        "cond_below_lookback_required": cond_below_lookback_required,
        "cond_down_acceleration": cond_down_acceleration,
        "is_sideways": is_sideways
    },
    "display": {
        "last_close": f"{last_close:,.2f}",
        "daily_return": f"{last_daily_return * 100:+.2f}%",
        "ema5": f"{last_ema5:,.2f}",
        "ema20": f"{last_ema20:,.2f}",
        "ema5_slope": f"{last_ema5_slope:+.4f}",
        "ema20_slope": f"{last_ema20_slope:+.4f}",
        "ema5_slope_pct": f"{ema5_slope_pct * 100:+.4f}%",
        "ema20_slope_pct": f"{ema20_slope_pct * 100:+.4f}%",
        "price_distance_pct": f"{price_distance * 100:.2f}%"
    },
    "chart_data": {
        "labels": labels,
        "close_data": close_data,
        "ema5_data": ema5_data,
        "ema20_data": ema20_data
    }
}

    with open("signal.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
