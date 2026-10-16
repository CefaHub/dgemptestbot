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


def rarity_roll(randbelow, premium=False, pity_epic=0, pity_legendary=0,
                pity_mythic=0, available_rarities=None):
    """Roll only rarities that actually have cards; renormalize remaining weights.

    Existing rates and pity remain unchanged whenever the full catalog is
    available. After a photo-only wipe, Common/Secret have zero cards and must
    never produce a missing-card error or consume a paid roll.
    """
    weights = WEIGHTS_PREMIUM if premium else WEIGHTS_NORMAL
    enabled = set(available_rarities) if available_rarities is not None else set(RARITIES)
    choices = [(tier, weights[tier]) for tier in RARITIES if tier in enabled and weights[tier] > 0]
    total = sum(weight for _, weight in choices)
    if not choices or total <= 0:
        raise ValueError('There are no available cards for this gacha.')
    number = randbelow(total)
    position = 0
    rolled = choices[-1][0]
    for rarity, weight in choices:
        position += weight
        if number < position:
            rolled = rarity
            break
    if ('mythic' in enabled and pity_mythic >= 149
            and RARITIES.index(rolled) < RARITIES.index('mythic')):
        return 'mythic'
    if ('legendary' in enabled and pity_legendary >= 39
            and RARITIES.index(rolled) < RARITIES.index('legendary')):
        return 'legendary'
    if ('epic' in enabled and pity_epic >= 9
            and RARITIES.index(rolled) < RARITIES.index('epic')):
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
