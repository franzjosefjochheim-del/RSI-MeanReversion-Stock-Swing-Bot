import pandas as pd
import config

def should_enter(position_exists: bool, open_positions_count: int) -> bool:
    return (not position_exists) and (open_positions_count < config.MAX_OPEN_POSITIONS)

def should_exit(position_exists: bool) -> bool:
    return position_exists

def hit_stop_or_takeprofit(entry_price: float, last_price: float) -> bool:
    if entry_price <= 0:
        return False
    if last_price <= entry_price * (1 - config.STOP_LOSS_PCT):
        return True
    if last_price >= entry_price * (1 + config.TAKE_PROFIT_PCT):
        return True
    return False
