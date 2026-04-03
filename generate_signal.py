import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


# =========================
# 전략 파라미터
# =========================
PRIMARY_SYMBOL = "QQQ"
PRIMARY_LEVERAGED_SYMBOL = "TQQQ"

ALT_ASSETS = [
    {"base": "TLT", "leveraged": "TMF", "priority": 1},
    {"base": "XLE", "leveraged": "ERX", "priority": 2},
    {"base": "GLD", "leveraged": "UGL", "priority": 3},
]

DOWNLOAD_PERIOD = "6mo"
DOWNLOAD_INTERVAL = "1d"
MIN_REQUIRED_BARS = 25
CHART_BARS = 60

EMA_FAST_SPAN = 5
EMA_SLOW_SPAN = 20

EMERGENCY_DROP_PCT = -0.03              # 하루 -3% 이상 하락 시 긴급 피신
SIDEWAYS_SLOPE_PCT_THRESHOLD = 0.0005   # EMA20 하루 변화율이 0.05% 미만이면 약한 추세
SIDEWAYS_DISTANCE_THRESHOLD = 0.02      # 종가가 EMA20과 2% 이내면 횡보 후보

DOWN_ACCEL_RATIO = 1.5                  # EMA5 하락 속도가 EMA20보다 1.5배 이상 빠를 때
ABOVE_CONFIRM_BARS = 2                  # EMA20 위 연속 확인 봉 수
BELOW_CONFIRM_BARS = 2                  # EMA20 아래 연속 확인 봉 수
BELOW_LOOKBACK_BARS = 5                 # 최근 확인 봉 수
BELOW_REQUIRED_COUNT = 3                # 최근 N봉 중 M봉 이상 EMA20 아래


# =========================
# 공통 유틸
# =========================
def safe_series_close(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].copy()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    return close


def download_close_series(symbol: str) -> pd.Series:
    df = yf.download(
        symbol,
        period=DOWNLOAD_PERIOD,
        interval=DOWNLOAD_INTERVAL,
        auto_adjust=True,
        progress=False
    )

    if df.empty or len(df) < MIN_REQUIRED_BARS:
        raise ValueError(f"{symbol} 데이터를 충분히 가져오지 못했습니다.")

    close = safe_series_close(df)

    if len(close) < MIN_REQUIRED_BARS:
        raise ValueError(f"{symbol} 유효한 종가 데이터가 충분하지 않습니다.")

    return close


def build_chart_data(close: pd.Series) -> dict:
    recent_close = close.tail(CHART_BARS)
    ema5_recent = recent_close.ewm(span=EMA_FAST_SPAN, adjust=False).mean()
    ema20_recent = recent_close.ewm(span=EMA_SLOW_SPAN, adjust=False).mean()

    labels = [pd.to_datetime(idx).strftime("%m-%d") for idx in recent_close.index]
    close_data = [round(float(v), 2) for v in recent_close]
    ema5_data = [round(float(v), 2) for v in ema5_recent]
    ema20_data = [round(float(v), 2) for v in ema20_recent]

    return {
        "labels": labels,
        "close_data": close_data,
        "ema5_data": ema5_data,
        "ema20_data": ema20_data
    }


def calculate_asset_metrics(symbol: str) -> dict:
    close = download_close_series(symbol)

    ema5 = close.ewm(span=EMA_FAST_SPAN, adjust=False).mean()
    ema20 = close.ewm(span=EMA_SLOW_SPAN, adjust=False).mean()
    ema5_slope = ema5.diff()
    ema20_slope = ema20.diff()
    daily_return = close.pct_change()

    last_idx = close.index[-1]
    signal_date = pd.to_datetime(last_idx).strftime("%Y-%m-%d")

    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    last_daily_return = float(daily_return.iloc[-1])

    last_ema5 = float(ema5.iloc[-1])
    prev_ema5 = float(ema5.iloc[-2])
    last_ema20 = float(ema20.iloc[-1])
    prev_ema20 = float(ema20.iloc[-2])

    last_ema5_slope = float(ema5_slope.iloc[-1])
    last_ema20_slope = float(ema20_slope.iloc[-1])

    ema5_slope_pct = last_ema5_slope / prev_ema5 if prev_ema5 != 0 else 0.0
    ema20_slope_pct = last_ema20_slope / prev_ema20 if prev_ema20 != 0 else 0.0

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

    ema20_strength_abs = abs(last_ema20_slope)
    ema20_strength_pct = abs(ema20_slope_pct)
    price_distance = abs(last_close - last_ema20) / last_ema20 if last_ema20 != 0 else 0.0

    is_sideways = (
        ema20_strength_pct < SIDEWAYS_SLOPE_PCT_THRESHOLD and
        price_distance < SIDEWAYS_DISTANCE_THRESHOLD
    )

    down_acceleration_ratio = (
        abs(last_ema5_slope) / abs(last_ema20_slope)
        if abs(last_ema20_slope) > 0 else None
    )
    cond_down_acceleration = (
        down_acceleration_ratio is not None and
        down_acceleration_ratio >= DOWN_ACCEL_RATIO
    )

    return {
        "symbol": symbol,
        "signal_date": signal_date,
        "close": close,
        "chart_data": build_chart_data(close),
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
        }
    }


# =========================
# 자산별 판정 로직
# =========================
def evaluate_asset(symbol: str, leveraged_symbol: str | None = None, is_primary: bool = False) -> dict:
    metrics = calculate_asset_metrics(symbol)
    conditions = metrics["conditions"]

    cond_ema_cross = conditions["cond_ema_cross"]
    cond_ema20_up = conditions["cond_ema20_up"]
    cond_ema5_up = conditions["cond_ema5_up"]
    cond_ema20_down = conditions["cond_ema20_down"]
    cond_ema5_down = conditions["cond_ema5_down"]
    cond_emergency_exit = conditions["cond_emergency_exit"]
    cond_above_n = conditions["cond_above_n"]
    cond_below_n = conditions["cond_below_n"]
    cond_below_lookback_required = conditions["cond_below_lookback_required"]
    cond_down_acceleration = conditions["cond_down_acceleration"]
    is_sideways = conditions["is_sideways"]

    market_state = ""
    decision_path = []
    recommendation = False
    signal = "CASH"

    if cond_emergency_exit:
        market_state = "EMERGENCY_EXIT"
        reason = f"{symbol} 전일 종가가 전일 대비 3% 이상 하락해 긴급 피신 조건이 발동했습니다."
        final_trigger = f"🚨 긴급 피신: {symbol} 전일 -3% 급락 → 비추천"
        decision_path.append("cond_emergency_exit=True")

    elif (
        cond_ema20_down and
        cond_ema5_down and
        cond_down_acceleration and
        cond_below_n and
        cond_below_lookback_required
    ):
        market_state = "DOWNTREND_CONFIRMED"
        reason = (
            "하락 전환 조건 충족: EMA5/EMA20 기울기 음수, 하락 가속, "
            f"20EMA 아래 {BELOW_CONFIRM_BARS}봉 + 최근 {BELOW_LOOKBACK_BARS}봉 중 "
            f"{BELOW_REQUIRED_COUNT}봉 이상 아래."
        )
        final_trigger = "📉 하락 전환 확정 → 비추천"
        decision_path.extend([
            "cond_ema20_down=True",
            "cond_ema5_down=True",
            "cond_down_acceleration=True",
            "cond_below_n=True",
            "cond_below_lookback_required=True"
        ])

    elif is_sideways and cond_ema20_down:
        market_state = "SIDEWAYS"
        reason = "하락 추세에서 횡보 구간으로 판단되어 보유 비추천입니다."
        final_trigger = "🟡 하락 횡보 → 비추천"
        decision_path.append("is_sideways=True")

    elif cond_ema20_up and cond_ema5_up and cond_above_n:
        market_state = "UPTREND_RECOVERY"
        reason = (
            "상승 복귀 조건 충족: EMA5/EMA20 기울기 양수, "
            f"종가가 20EMA 위 {ABOVE_CONFIRM_BARS}봉 연속입니다."
        )
        final_trigger = "📈 상승 복귀 확인 → 추천"
        decision_path.extend([
            "cond_ema20_up=True",
            "cond_ema5_up=True",
            "cond_above_n=True"
        ])
        recommendation = True
        signal = leveraged_symbol if leveraged_symbol else symbol

    elif cond_ema_cross and cond_ema20_up:
        market_state = "EARLY_UPTREND"
        reason = "상승 초기 조건 충족: 5EMA > 20EMA, 20EMA 상승 시작."
        final_trigger = "📈 초기 상승 진입 → 추천"
        decision_path.extend([
            "cond_ema_cross=True",
            "cond_ema20_up=True"
        ])
        recommendation = True
        signal = leveraged_symbol if leveraged_symbol else symbol

    else:
        market_state = "UNCLEAR"
        reason = "추세가 명확하지 않아 보유 비추천입니다."
        final_trigger = "⚖️ 방향 불명확 → 비추천"
        decision_path.append("fallback_not_recommended=True")

    # 추천 자산 정렬용 점수
    latest_indicator_info = metrics["latest_indicator_info"]
    condition_values = metrics["condition_values"]
    score = (
        latest_indicator_info["ema20_slope_raw"] * 1000
        + latest_indicator_info["ema5_slope_raw"] * 500
        - condition_values["price_distance_pct"] * 0.5
    )

    result = {
        "symbol": symbol,
        "leveraged_symbol": leveraged_symbol if leveraged_symbol else symbol,
        "is_primary": is_primary,
        "recommendation": recommendation,
        "signal": signal if recommendation else "CASH",
        "market_state": market_state,
        "reason": reason,
        "final_trigger": final_trigger,
        "decision_path": decision_path,
        "score": round(score, 4),
        "latest_price_info": metrics["latest_price_info"],
        "latest_indicator_info": metrics["latest_indicator_info"],
        "condition_values": metrics["condition_values"],
        "conditions": metrics["conditions"],
        "display": metrics["display"],
        "chart_data": metrics["chart_data"],
        "signal_date": metrics["signal_date"]
    }

    return result


def select_alternative_asset() -> tuple[dict | None, list]:
    alt_results = []

    for asset in ALT_ASSETS:
        result = evaluate_asset(
            symbol=asset["base"],
            leveraged_symbol=asset["leveraged"],
            is_primary=False
        )
        result["priority"] = asset["priority"]
        alt_results.append(result)

    recommended = [x for x in alt_results if x["recommendation"]]

    if not recommended:
        return None, alt_results

    recommended.sort(key=lambda x: (-x["score"], x["priority"]))
    return recommended[0], alt_results


# =========================
# 메인 실행
# =========================
def main():
    today_date = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    generated_at_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S %Z")

    # 1차: QQQ 우선 판단
    primary_result = evaluate_asset(
        symbol=PRIMARY_SYMBOL,
        leveraged_symbol=PRIMARY_LEVERAGED_SYMBOL,
        is_primary=True
    )

    signal_date = primary_result["signal_date"]

    if primary_result["recommendation"]:
        final_signal = PRIMARY_LEVERAGED_SYMBOL
        final_title = "TQQQ 우선 / 대체자산 추천 시그널"
        final_market_state = "PRIMARY_SELECTED"
        reason = (
            "QQQ가 상승 추세로 판단되어 대체자산 검토 없이 "
            f"{PRIMARY_LEVERAGED_SYMBOL}를 보유합니다."
        )
        final_trigger = f"🥇 QQQ 우선 조건 충족 → {PRIMARY_LEVERAGED_SYMBOL}"

        alt_selected = None
        alt_results = []

        final_source = {
            "type": "PRIMARY",
            "base_symbol": PRIMARY_SYMBOL,
            "leveraged_symbol": PRIMARY_LEVERAGED_SYMBOL
        }

    else:
        # 2차: 대체자산 검토
        alt_selected, alt_results = select_alternative_asset()

        if alt_selected:
            final_signal = alt_selected["leveraged_symbol"]
            final_title = "TQQQ 우선 / 대체자산 추천 시그널"
            final_market_state = "ALT_SELECTED"
            reason = (
                f"QQQ가 {primary_result['market_state']} 상태로 판단되어 "
                f"{PRIMARY_LEVERAGED_SYMBOL}는 보유하지 않습니다. "
                f"대체자산을 검토한 결과 {alt_selected['symbol']}가 가장 우호적인 추세를 보여 "
                f"{alt_selected['leveraged_symbol']}를 선택했습니다."
            )
            final_trigger = (
                f"🔁 QQQ 비추천 → 대체자산 {alt_selected['symbol']} 추천 → "
                f"{alt_selected['leveraged_symbol']}"
            )
            final_source = {
                "type": "ALTERNATIVE",
                "base_symbol": alt_selected["symbol"],
                "leveraged_symbol": alt_selected["leveraged_symbol"]
            }
        else:
            final_signal = "CASH"
            final_title = "TQQQ 우선 / 대체자산 추천 시그널"
            final_market_state = "CASH_SELECTED"
            reason = (
                f"QQQ가 {primary_result['market_state']} 상태로 판단되어 "
                f"{PRIMARY_LEVERAGED_SYMBOL}는 보유하지 않습니다. "
                "대체자산(TLT, XLE, GLD)도 모두 보유 조건을 충족하지 않아 CASH를 유지합니다."
            )
            final_trigger = "⚖️ QQQ 비추천 + 대체자산 전부 비추천 → CASH"
            final_source = {
                "type": "CASH",
                "base_symbol": None,
                "leveraged_symbol": None
            }

    alt_review_summary = []
    for alt in alt_results:
        alt_review_summary.append({
            "base_symbol": alt["symbol"],
            "leveraged_symbol": alt["leveraged_symbol"],
            "recommendation": "추천" if alt["recommendation"] else "비추천",
            "reason": alt["reason"],
            "final_trigger": alt["final_trigger"],
            "score": alt["score"],
            "display": alt["display"],
            "conditions": alt["conditions"]
        })

    selected_alt_brief_reason = (
        f"{alt_selected['symbol']}가 추천되어 {alt_selected['leveraged_symbol']} 선택"
        if alt_selected else
        "대체자산 모두 비추천"
    )

    payload = {
        # =========================
        # 기존 HTML 호환용 키
        # =========================
        "title": final_title,
        "today_date": today_date,
        "signal_date": signal_date,
        "signal": final_signal,
        "reason": reason,
        "final_trigger": final_trigger,

        # 기존 QQQ 카드에 그대로 쓰기 좋은 값
        "last_close": primary_result["display"]["last_close"],
        "daily_return": primary_result["display"]["daily_return"],
        "ema5": primary_result["display"]["ema5"],
        "ema20": primary_result["display"]["ema20"],
        "ema5_slope": primary_result["display"]["ema5_slope"],
        "ema20_slope": primary_result["display"]["ema20_slope"],

        "cond_ema_cross": primary_result["conditions"]["cond_ema_cross"],
        "cond_ema20_up": primary_result["conditions"]["cond_ema20_up"],
        "cond_ema5_up": primary_result["conditions"]["cond_ema5_up"],
        "cond_emergency_exit": primary_result["conditions"]["cond_emergency_exit"],
        "is_sideways": primary_result["conditions"]["is_sideways"],

        "labels": primary_result["chart_data"]["labels"],
        "close_data": primary_result["chart_data"]["close_data"],
        "ema5_data": primary_result["chart_data"]["ema5_data"],
        "ema20_data": primary_result["chart_data"]["ema20_data"],

        # =========================
        # 새 UI용 상단 요약
        # =========================
        "summary": {
            "title": final_title,
            "today_action": final_signal,
            "final_market_state": final_market_state,
            "final_source": final_source,
            "primary_symbol": PRIMARY_SYMBOL,
            "primary_leveraged_symbol": PRIMARY_LEVERAGED_SYMBOL
        },

        # =========================
        # QQQ 판단 카드용
        # =========================
        "primary_review": {
            "symbol": primary_result["symbol"],
            "leveraged_symbol": primary_result["leveraged_symbol"],
            "recommendation": "추천" if primary_result["recommendation"] else "비추천",
            "market_state": primary_result["market_state"],
            "reason": primary_result["reason"],
            "final_trigger": primary_result["final_trigger"],
            "decision_path": primary_result["decision_path"],
            "display": primary_result["display"],
            "conditions": primary_result["conditions"],
            "condition_values": primary_result["condition_values"],
            "latest_price_info": primary_result["latest_price_info"],
            "latest_indicator_info": primary_result["latest_indicator_info"]
        },

        # =========================
        # 대체자산 카드용
        # =========================
        "alt_review": {
            "selected_alt_brief_reason": selected_alt_brief_reason,
            "selected_asset": {
                "base_symbol": alt_selected["symbol"],
                "leveraged_symbol": alt_selected["leveraged_symbol"],
                "reason": alt_selected["reason"],
                "final_trigger": alt_selected["final_trigger"],
                "score": alt_selected["score"]
            } if alt_selected else None,
            "candidates": alt_review_summary
        },

        # =========================
        # 메타 / 디버깅
        # =========================
        "meta": {
            "generated_at_kst": generated_at_kst,
            "today_date": today_date,
            "signal_date": signal_date,
            "primary_symbol": PRIMARY_SYMBOL,
            "download_period": DOWNLOAD_PERIOD,
            "download_interval": DOWNLOAD_INTERVAL,
            "alternative_assets": ALT_ASSETS
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
            "signal": final_signal,
            "market_state": final_market_state,
            "reason": reason,
            "final_trigger": final_trigger,
            "final_source": final_source
        },
        "chart_data": {
            "labels": primary_result["chart_data"]["labels"],
            "close_data": primary_result["chart_data"]["close_data"],
            "ema5_data": primary_result["chart_data"]["ema5_data"],
            "ema20_data": primary_result["chart_data"]["ema20_data"]
        }
    }

    with open("signal.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
