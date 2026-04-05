import json
import os
from datetime import datetime


STATE_FILE = "last_execution.json"


def load_last_execution():
    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_last_execution(data):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_str():
    return datetime.now().strftime("%Y-%m-%d")


def is_already_executed_today():
    data = load_last_execution()
    if not data:
        return False

    return data.get("execution_date") == get_today_str()


def mark_execution(status, target_symbol, current_symbol, action_summary):
    payload = {
        "execution_date": get_today_str(),
        "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "target_symbol": target_symbol,
        "current_symbol": current_symbol,
        "action_summary": action_summary,
    }
    save_last_execution(payload)
