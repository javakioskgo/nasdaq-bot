import json
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf

def main():
    df = yf.download("QQQ", period="6mo", interval="1d", auto_adjust=True, progress=False)
    if df.empty or len(df) < 25:
        raise ValueError("QQQ 데이터를 충분히 가져오지 못했습니다.")

    close = df["Close"].copy()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()

    ema5 = close.ewm(span=5, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema5_slope = ema5.diff()
    ema20_slope = ema20.diff()
    daily_return = close.pct_change()

    last_idx = close.index[-1]
    signal_date = pd.to_datetime(last_idx).strftime("%Y-%m-%d")
    today_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    last_close = float(close.iloc[-1])
    last_daily_return = float(daily_return.iloc[-1])
    last_ema5 = float(ema5.iloc[-1])
    last_ema20 = float(ema20.iloc[-1])
    last_ema5_slope = float(ema5_slope.iloc[-1])
    last_ema20_slope = float(ema20_slope.iloc[-1])

    recent2_close = close.iloc[-2:]
    recent2_ema20 = ema20.iloc[-2:]
    cond_below_2 = bool((recent2_close < recent2_ema20).all())
    cond_above_2 = bool((recent2_close > recent2_ema20).all())

    recent5_close = close.iloc[-5:]
    recent5_ema20 = ema20.iloc[-5:]
    below_5_count = int((recent5_close <= recent5_ema20).sum())

    cond_ema_cross = last_ema5 > last_ema20
    cond_ema20_up = last_ema20_slope > 0
    cond_ema5_up = last_ema5_slope > 0
    cond_emergency_exit = last_daily_return <= -0.03
    cond_below_5_3 = below_5_count >= 3

    if cond_emergency_exit:
        signal = "CASH"
        reason = "QQQ 전일 종가가 전일 대비 3% 이상 하락해 긴급 피신 조건이 발동했습니다."
        final_trigger = "🚨 긴급 피신: QQQ 전일 -3% 급락 → CASH"
    elif (
        last_ema20_slope < 0 and
        last_ema5_slope < 0 and
        abs(last_ema5_slope) >= 1.5 * abs(last_ema20_slope) and
        cond_below_2 and
        cond_below_5_3
    ):
        signal = "CASH"
        reason = "하락 전환 조건 충족: EMA5/EMA20 기울기 음수, 하락 가속, 20EMA 아래 2봉 + 최근 5봉 중 3봉 이상 아래."
        final_trigger = "📉 하락 전환 확정: EMA 하락 + 20EMA 아래 지속 → CASH"
    elif last_ema20_slope > 0 and last_ema5_slope > 0 and cond_above_2:
        signal = "TQQQ"
        reason = "상승 복귀 조건 충족: EMA5/EMA20 기울기 양수, 종가가 20EMA 위 2봉 연속입니다."
        final_trigger = "📈 상승 복귀 확인: EMA 기울기 양수 + 20EMA 위 2봉 → TQQQ"
    elif cond_ema_cross and cond_ema20_up:
        signal = "TQQQ"
        reason = "상승 기본조건 충족: 5EMA > 20EMA, 20EMA 기울기 > 0 입니다."
        final_trigger = "📈 상승 추세 확인: 5EMA > 20EMA, 20EMA 상승 → TQQQ"
    else:
        signal = "CASH"
        reason = "추세가 명확하지 않아 관망합니다."
        final_trigger = "⚖️ 방향 불명확 → CASH"

    recent_close = close.tail(60)
    ema5_recent = recent_close.ewm(span=5, adjust=False).mean()
    ema20_recent = recent_close.ewm(span=20, adjust=False).mean()

    labels = [pd.to_datetime(idx).strftime("%m-%d") for idx in recent_close.index]
    close_data = [round(float(v), 2) for v in recent_close]
    ema5_data = [round(float(v), 2) for v in ema5_recent]
    ema20_data = [round(float(v), 2) for v in ema20_recent]

    payload = {
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
        "cond_below_2": cond_below_2,
        "cond_below_5_3": cond_below_5_3,
        "labels": labels,
        "close_data": close_data,
        "ema5_data": ema5_data,
        "ema20_data": ema20_data
    }

    with open("signal.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
