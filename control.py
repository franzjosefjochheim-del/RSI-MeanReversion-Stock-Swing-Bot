import json, os, threading
LOCK = threading.Lock()
FLAG = "bot_state.json"

def _read():
    if not os.path.exists(FLAG):
        return {"paused": False}
    try:
        with open(FLAG, "r") as f:
            return json.load(f)
    except Exception:
        return {"paused": False}

def is_paused() -> bool:
    with LOCK:
        return bool(_read().get("paused", False))

def set_paused(value: bool):
    with LOCK:
        with open(FLAG, "w") as f:
            json.dump({"paused": bool(value)}, f)
