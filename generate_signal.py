import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
import FinanceDataReader as fdr


# =========================
# 공통 전략 파라미터
# =========================
DOWNLOAD_PERIOD = "6mo"
DOWNLOAD_INTERVAL = "1d"
MIN_REQUIRED_BARS = 25
CHART_BARS = 60

EMA_FAST_SPAN = 5
EMA_SLOW_SPAN = 20

EMERGENCY_DROP_PCT = -0.03
SIDEWAYS_SLOPE_PCT_THRESHOLD = 0.0005
SIDEWAYS_DISTANCE_THRESHOLD = 0.02

DOWN_ACCEL_RATIO = 1.5
ABOVE_CONFIRM_BARS = 2
BELOW_CONFIRM_BARS = 2
BELOW_LOOKBACK_BARS = 5
BELOW_REQUIRED_COUNT = 3


# =========================
# 해외 전략
# =========================
OVERSEAS_PRIMARY_SYMBOL = "QQQ"
OVERSEAS_PRIMARY_LEVERAGED_SYMBOL = "TQQQ"

OVERSEAS_ALT_ASSETS = [
    {"base": "SOXX", "leveraged": "SOXL", "priority": 1},
    {"base": "XLE", "leveraged": "ERX", "priority": 2},
    {"base": "GLD", "leveraged": "UGL", "priority": 3},
]


# =========================
# 국내 전략
# 이름은 FinanceDataReader의 ETF/KR 종목명과 일치해야 함
# =========================
DOMESTIC_PRIMARY_NAME = "KODEX 미국나스닥100"

DOMESTIC_ALT_ASSETS = [
    {
        "base_name": "TIGER 미국필라델피아반도체나스닥",
        "leveraged_name": "TIGER 미국필라델피아반도체나스닥",
        "priority": 1,
    },
    {
        "base_name": "KODEX 골드선물(H)",
        "leveraged_name": "KODEX 골드선물(H)",
        "priority": 2,
    },
]


# =========================
# 시간 유틸
# =========================
def get_now_kst() -> datetime:
    return datetime.now(ZoneInfo("Asia/Seoul"))


# =========================
# 국내 ETF 코드 조회 (FDR)
# =========================
_domestic_code_cache: dict[str, str] = {}


def build_domestic_etf_name_map() -> dict[str, str]:
    df = fdr.StockListing("ETF/KR")

    if df.empty:
        raise ValueError("FinanceDataReader에서 ETF/KR 목록을 가져오지 못했습니다.")

    # FDR 환경에 따라 Symbol 또는 Code 컬럼명이 다를 수 있음
    symbol_col = None
    if "Symbol" in df.columns:
        symbol_col = "Symbol"
    elif "Code" in df.columns:
        symbol_col = "Code"

    if "Name" not in df.columns or symbol_col is None:
        raise ValueError(f"ETF/KR 목록 형식이 예상과 다릅니다. columns={list(df.columns)}")

    name_to_code = {}
    for _, row in df.iterrows():
        name = str(row["Name"]).strip()
        code = str(row[symbol_col]).strip().zfill(6)
        if name:
            name_to_code[name] = code

    return name_to_code


def resolve_domestic_etf_code_by_name(etf_name: str) -> str:
    if etf_name in _domestic_code_cache:
        return _domestic_code_cache[etf_name]

    name_map = build_domestic_etf_name_map()

    # 1. 완전 일치
    if etf_name in name_map:
        code = name_map[etf_name]
        _domestic_code_cache[etf_name] = code
        return code

    # 2. 공백 제거 후 완전 일치
    normalized_target = etf_name.replace(" ", "")
    for name, code in name_map.items():
        if name.replace(" ", "") == normalized_target:
            _domestic_code_cache[etf_name] = code
            return code

    # 3. 부분 일치 후보 중 첫 번째 사용
    candidates = [
        (name, code) for name, code in name_map.items()
        if normalized_target in name.replace(" ", "")
    ]
    if len(candidates) == 1:
        matched_name, matched_code = candidates[0]
        print(f"[INFO] 국내 ETF 이름 자동 보정: '{etf_name}' -> '{matched_name}'")
        _domestic_code_cache[etf_name] = matched_code
        return matched_code

    sample = ", ".join([name for name, _ in candidates[:10]])
    raise ValueError(
        f"국내 ETF 이름 '{etf_name}'을 ETF/KR 목록에서 찾지 못했습니다. "
        f"유사 후보: {sample if sample else '없음'}"
    )

# =========================
# 공통 유틸
# =========================
def safe_series_close_from_yf(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].copy()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close = pd.to_numeric(close, errors="coerce").dropna()
    return close


def safe_series_close_from_fdr(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)

    if "Close" not in df.columns:
        raise ValueError(f"국내 ETF 가격 데이터 형식이 예상과 다릅니다. columns={list(df.columns)}")

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    close.index = pd.to_datetime(close.index)
    close = close.sort_index()
    return close


def download_close_series_overseas(symbol: str) -> pd.Series:
    df = yf.download(
        symbol,
        period=DOWNLOAD_PERIOD,
        interval=DOWNLOAD_INTERVAL,
        auto_adjust=True,
        progress=False
    )

    if df.empty or len(df) < MIN_REQUIRED_BARS:
        raise ValueError(f"{symbol} 데이터를 충분히 가져오지 못했습니다.")

    close = safe_series_close_from_yf(df)

    if len(close) < MIN_REQUIRED_BARS:
        raise ValueError(f"{symbol} 유효한 종가 데이터가 충분하지 않습니다.")

    return close


def download_close_series_domestic(symbol_or_name: str) -> pd.Series:
    if symbol_or_name.isdigit() and len(symbol_or_name) == 6:
        code = symbol_or_name
        display_name = symbol_or_name
    else:
        code = resolve_domestic_etf_code_by_name(symbol_or_name)
        display_name = symbol_or_name

    df = fdr.DataReader(code)

    if df.empty:
        raise ValueError(f"{display_name} ({code}) 국내 ETF 데이터를 가져오지 못했습니다.")

    close = safe_series_close_from_fdr(df)

    # 최근 6개월만 사용
    close = close.tail(180)

    if len(close) < MIN_REQUIRED_BARS:
        raise ValueError(f"{display_name} ({code}) 국내 ETF 유효 종가 데이터가 충분하지 않습니다.")

    return close


def download_close_series(symbol: str, market_type: str) -> pd.Series:
    if market_type == "OVERSEAS":
        return download_close_series_overseas(symbol)
    if market_type == "DOMESTIC":
        return download_close_series_domestic(symbol)
    raise ValueError(f"지원하지 않는 market_type: {market_type}")


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


# =========================
# 지표 계산
# =========================
def calculate_asset_metrics(symbol: str, market_type: str, display_name: str | None = None) -> dict:
    close = download_close_series(symbol, market_type)

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
        "display_name": display_name if display_name else symbol,
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
# 자산별 판정
# =========================
def evaluate_asset(
    symbol: str,
    market_type: str,
    leveraged_symbol: str | None = None,
    is_primary: bool = False,
    display_name: str | None = None,
    leveraged_display_name: str | None = None,
) -> dict:
    metrics = calculate_asset_metrics(symbol, market_type, display_name=display_name)
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
    signal_display_name = "CASH"
    signal_strength = 0

    name_for_text = metrics["display_name"]

    if cond_emergency_exit:
        market_state = "EMERGENCY_EXIT"
        reason = f"{name_for_text} 직전 거래일 종가가 전일 대비 3% 이상 하락해 긴급 피신 조건이 발동했습니다."
        final_trigger = f"🚨 긴급 피신: {name_for_text} 직전 거래일 -3% 급락 → 비추천"
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
        signal_display_name = leveraged_display_name if leveraged_display_name else (leveraged_symbol if leveraged_symbol else name_for_text)
        signal_strength = 2

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
        signal_display_name = leveraged_display_name if leveraged_display_name else (leveraged_symbol if leveraged_symbol else name_for_text)
        signal_strength = 1

    else:
        market_state = "UNCLEAR"
        reason = "추세가 명확하지 않아 보유 비추천입니다."
        final_trigger = "⚖️ 방향 불명확 → 비추천"
        decision_path.append("fallback_not_recommended=True")

    latest_indicator_info = metrics["latest_indicator_info"]
    condition_values = metrics["condition_values"]
    score = (
        latest_indicator_info["ema20_slope_raw"] * 1000
        + latest_indicator_info["ema5_slope_raw"] * 500
        - condition_values["price_distance_pct"] * 0.5
    )

    return {
        "symbol": symbol,
        "display_name": metrics["display_name"],
        "leveraged_symbol": leveraged_symbol if leveraged_symbol else symbol,
        "leveraged_display_name": leveraged_display_name if leveraged_display_name else (leveraged_symbol if leveraged_symbol else metrics["display_name"]),
        "is_primary": is_primary,
        "recommendation": recommendation,
        "signal": signal if recommendation else "CASH",
        "signal_display_name": signal_display_name if recommendation else "CASH",
        "signal_strength": signal_strength,
        "signal_strength_label": (
            "STRONG_UPTREND" if signal_strength == 2
            else "EARLY_UPTREND" if signal_strength == 1
            else "NOT_RECOMMENDED"
        ),
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


def select_alternative_asset(alt_assets: list[dict], market_type: str) -> tuple[dict | None, list]:
    alt_results = []

    for asset in alt_assets:
        result = evaluate_asset(
            symbol=asset["base"],
            leveraged_symbol=asset["leveraged"],
            market_type=market_type,
            is_primary=False,
            display_name=asset.get("base_name", asset["base"]),
            leveraged_display_name=asset.get("leveraged_name", asset["leveraged"]),
        )
        result["priority"] = asset["priority"]
        alt_results.append(result)

    recommended = [x for x in alt_results if x["recommendation"]]

    if not recommended:
        return None, alt_results

    recommended.sort(
        key=lambda x: (-x["signal_strength"], -x["score"], x["priority"])
    )
    return recommended[0], alt_results


def run_strategy(
    market_type: str,
    title: str,
    primary_symbol: str,
    primary_display_name: str,
    primary_leveraged_symbol: str,
    primary_leveraged_display_name: str,
    alt_assets: list[dict],
) -> dict:
    primary_result = evaluate_asset(
        symbol=primary_symbol,
        leveraged_symbol=primary_leveraged_symbol,
        market_type=market_type,
        is_primary=True,
        display_name=primary_display_name,
        leveraged_display_name=primary_leveraged_display_name,
    )

    signal_date = primary_result["signal_date"]

    if primary_result["recommendation"]:
        final_signal = primary_result["leveraged_symbol"]
        final_signal_display_name = primary_result["leveraged_display_name"]
        final_market_state = "PRIMARY_SELECTED"
        reason = (
            f"{primary_display_name}가 상승 추세로 판단되어 "
            f"{primary_leveraged_display_name}를 보유합니다."
        )
        final_trigger = f"🥇 {primary_display_name} 우선 조건 충족 → {primary_leveraged_display_name}"

        alt_selected = None
        alt_results = []

        final_source = {
            "type": "PRIMARY",
            "base_symbol": primary_symbol,
            "base_display_name": primary_display_name,
            "leveraged_symbol": primary_leveraged_symbol,
            "leveraged_display_name": primary_leveraged_display_name,
        }

    else:
        alt_selected, alt_results = select_alternative_asset(alt_assets, market_type)

        if alt_selected:
            final_signal = alt_selected["leveraged_symbol"]
            final_signal_display_name = alt_selected["leveraged_display_name"]
            final_market_state = "ALT_SELECTED"
            reason = (
                f"{primary_display_name}가 {primary_result['market_state']} 상태로 판단되어 "
                f"{primary_leveraged_display_name}는 보유하지 않습니다. "
                f"대체자산을 검토한 결과 {alt_selected['display_name']}가 가장 우호적인 추세를 보여 "
                f"{alt_selected['leveraged_display_name']}를 선택했습니다."
            )
            final_trigger = (
                f"🔁 {primary_display_name} 비추천 → 대체자산 {alt_selected['display_name']} 추천 → "
                f"{alt_selected['leveraged_display_name']}"
            )
            final_source = {
                "type": "ALTERNATIVE",
                "base_symbol": alt_selected["symbol"],
                "base_display_name": alt_selected["display_name"],
                "leveraged_symbol": alt_selected["leveraged_symbol"],
                "leveraged_display_name": alt_selected["leveraged_display_name"],
            }
        else:
            final_signal = "CASH"
            final_signal_display_name = "CASH"
            final_market_state = "CASH_SELECTED"
            alt_names = ", ".join([asset.get("base_name", asset["base"]) for asset in alt_assets])
            reason = (
                f"{primary_display_name}가 {primary_result['market_state']} 상태로 판단되어 "
                f"{primary_leveraged_display_name}는 보유하지 않습니다. "
                f"대체자산({alt_names})도 모두 보유 조건을 충족하지 않아 CASH를 유지합니다."
            )
            final_trigger = f"⚖️ {primary_display_name} 비추천 + 대체자산 전부 비추천 → CASH"
            final_source = {
                "type": "CASH",
                "base_symbol": None,
                "base_display_name": None,
                "leveraged_symbol": None,
                "leveraged_display_name": None,
            }

    alt_review_summary = []
    for alt in alt_results:
        alt_review_summary.append({
            "base_symbol": alt["symbol"],
            "base_display_name": alt["display_name"],
            "leveraged_symbol": alt["leveraged_symbol"],
            "leveraged_display_name": alt["leveraged_display_name"],
            "recommendation": "추천" if alt["recommendation"] else "비추천",
            "signal_strength": alt["signal_strength"],
            "signal_strength_label": alt["signal_strength_label"],
            "reason": alt["reason"],
            "final_trigger": alt["final_trigger"],
            "score": alt["score"],
            "display": alt["display"],
            "conditions": alt["conditions"]
        })

    selected_alt_brief_reason = (
        f"{alt_selected['display_name']}가 추천되어 {alt_selected['leveraged_display_name']} 선택"
        if alt_selected else
        "대체자산 모두 비추천"
    )

    return {
        "title": title,
        "signal_date": signal_date,
        "signal": final_signal,
        "signal_display_name": final_signal_display_name,
        "reason": reason,
        "final_trigger": final_trigger,
        "final_market_state": final_market_state,
        "final_source": final_source,
        "primary_review": {
            "symbol": primary_result["symbol"],
            "display_name": primary_result["display_name"],
            "leveraged_symbol": primary_result["leveraged_symbol"],
            "leveraged_display_name": primary_result["leveraged_display_name"],
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
        "alt_review": {
            "selected_alt_brief_reason": selected_alt_brief_reason,
            "selected_asset": {
                "base_symbol": alt_selected["symbol"],
                "base_display_name": alt_selected["display_name"],
                "leveraged_symbol": alt_selected["leveraged_symbol"],
                "leveraged_display_name": alt_selected["leveraged_display_name"],
                "signal_strength": alt_selected["signal_strength"],
                "signal_strength_label": alt_selected["signal_strength_label"],
                "reason": alt_selected["reason"],
                "final_trigger": alt_selected["final_trigger"],
                "score": alt_selected["score"]
            } if alt_selected else None,
            "candidates": alt_review_summary
        },
        "chart_data": {
            "labels": primary_result["chart_data"]["labels"],
            "close_data": primary_result["chart_data"]["close_data"],
            "ema5_data": primary_result["chart_data"]["ema5_data"],
            "ema20_data": primary_result["chart_data"]["ema20_data"]
        }
    }


def main():
    now_kst = get_now_kst()
    today_date = now_kst.strftime("%Y-%m-%d")
    generated_at_kst = now_kst.strftime("%Y-%m-%d %H:%M:%S %Z")

    domestic_alt_assets = [
        {
            "base": asset["base_name"],
            "base_name": asset["base_name"],
            "leveraged": asset["leveraged_name"],
            "leveraged_name": asset["leveraged_name"],
            "priority": asset["priority"],
        }
        for asset in DOMESTIC_ALT_ASSETS
    ]

    overseas_result = run_strategy(
        market_type="OVERSEAS",
        title="해외 ETF 추천 시그널",
        primary_symbol=OVERSEAS_PRIMARY_SYMBOL,
        primary_display_name="QQQ",
        primary_leveraged_symbol=OVERSEAS_PRIMARY_LEVERAGED_SYMBOL,
        primary_leveraged_display_name="TQQQ",
        alt_assets=OVERSEAS_ALT_ASSETS,
    )

    domestic_result = run_strategy(
        market_type="DOMESTIC",
        title="국내 ETF 추천 시그널",
        primary_symbol=DOMESTIC_PRIMARY_NAME,
        primary_display_name=DOMESTIC_PRIMARY_NAME,
        primary_leveraged_symbol=DOMESTIC_PRIMARY_NAME,
        primary_leveraged_display_name=DOMESTIC_PRIMARY_NAME,
        alt_assets=domestic_alt_assets,
    )

    payload = {
        "title": "국내 / 해외 ETF 추천 시그널",
        "today_date": today_date,
        "generated_at_kst": generated_at_kst,
        "page_notice": "국내/해외 모두 직전 거래일 마감 기준",
        "markets": {
            "overseas": overseas_result,
            "domestic": domestic_result
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
        }
    }

    with open("signal.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("signal.json 생성 완료")


if __name__ == "__main__":
    main()
