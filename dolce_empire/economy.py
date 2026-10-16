"""Deterministic economic formulas, separated from database and Telegram."""
from datetime import datetime, timedelta
from .catalog import RARITIES, WEIGHTS_NORMAL, WEIGHTS_PREMIUM

HOUR = 3600
MAX_OFFLINE_SECONDS = 12 * HOUR
FREE_INTERVAL = timedelta(hours=1)
DAILY_MULTIPLIER_PERCENT = 15
MARKET_FEE_PERCENT = 5
MAX_COIN_BALANCE = 10**15


def paid_price(peak_hourly_income: int, paid_roll_number: int = 1, premium: bool = False) -> int:
    """The nth *paid* roll today. Free rolls never increase the price."""
    if peak_hourly_income < 0 or paid_roll_number < 1:
        raise ValueError('Invalid price arguments')
    base = max(2000, 8 * peak_hourly_income)
    amount = base * (100 + DAILY_MULTIPLIER_PERCENT * (paid_roll_number - 1)) // 100
    return amount * (4 if premium else 1)


def upgrade_price(base_income: int, level: int) -> int:
    if not 1 <= level < 50:
        raise ValueError('Max card level is 50')
    return base_income * (15 + 3 * level * level)


def slot_upgrade_price(current_slots: int) -> int:
    if not 3 <= current_slots < 8:
        raise ValueError('Maximum studio capacity reached')
    return 7500 * 3 ** (current_slots - 3)


def card_income(base_income: int, level: int, awakening: int) -> int:
    if not (1 <= level <= 50 and 0 <= awakening <= 5):
        raise ValueError('Out of bounds card attributes')
    return base_income * (100 + (level - 1) * 6) * (100 + awakening * 20) // 10000


def rarity_roll(randbelow, premium=False, pity_epic=0, pity_legendary=0, pity_mythic=0):
    weights = WEIGHTS_PREMIUM if premium else WEIGHTS_NORMAL
    number = randbelow(sum(weights.values()))
    position = 0
    rolled = RARITIES[-1]
    for rarity in RARITIES:
        position += weights[rarity]
        if number < position:
            rolled = rarity
            break
    # Guarantee applies after 9 / 39 / 149 prior failures.
    if pity_mythic >= 149 and RARITIES.index(rolled) < RARITIES.index('mythic'):
        return 'mythic'
    if pity_legendary >= 39 and RARITIES.index(rolled) < RARITIES.index('legendary'):
        return 'legendary'
    if pity_epic >= 9 and RARITIES.index(rolled) < RARITIES.index('epic'):
        return 'epic'
    return rolled


def refill_charges(charges, refill_at, now):
    if charges >= 3:
        return 3, None
    if refill_at is None:
        return charges, now + FREE_INTERVAL
    if now < refill_at:
        return charges, refill_at
    intervals = int((now - refill_at).total_seconds() // HOUR) + 1
    charges = min(3, charges + intervals)
    return charges, None if charges >= 3 else refill_at + intervals * FREE_INTERVAL


def projected_unclaimed(hourly_income: int, pending: int, remainder: int,
                        bank_seconds: int, last_claim: datetime, now: datetime):
    elapsed = max(0, int((now - last_claim).total_seconds()))
    accrue = min(elapsed, max(0, MAX_OFFLINE_SECONDS - bank_seconds))
    minted, new_remainder = divmod(hourly_income * accrue + remainder, HOUR)
    return pending + minted, new_remainder, accrue
