"""Read-only catalogue of K-pop cards. No third-party photos are bundled."""
import json
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).resolve().parent.parent

RARITIES = ["common", "rare", "epic", "legendary", "mythic", "secret"]
RARITY_TITLES = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая", "legendary": "Легендарная", "mythic": "Мифическая", "secret": "Секретная"}
RARITY_EMOJIS = {"common": "⚪", "rare": "🔵", "epic": "🟣", "legendary": "🟡", "mythic": "💎", "secret": "❤️‍🔥"}
RARITY_INCOME = {"common": 50, "rare": 100, "epic": 220, "legendary": 500, "mythic": 1200, "secret": 3000}
WEIGHTS_NORMAL = {"common": 5400, "rare": 2700, "epic": 1300, "legendary": 500, "mythic": 90, "secret": 10}
WEIGHTS_PREMIUM = {"common": 0, "rare": 5100, "epic": 3000, "legendary": 1500, "mythic": 380, "secret": 20}

# Bundled read-only metadata must NOT be stored inside /app/data:
# some hosting providers mount a writable volume over that directory.
# This path remains available even when the /app/data directory is replaced.
CATALOG_PATH = Path(__file__).resolve().with_name('_catalog.json')

@lru_cache(maxsize=1)
def all_cards():
    with CATALOG_PATH.open('r', encoding='utf-8') as file:
        cards = json.load(file)
    if not isinstance(cards, list) or len(cards) < 80:
        raise ValueError(f'Card catalog is incomplete: {CATALOG_PATH}')
    return cards

@lru_cache(maxsize=1)
def card_by_id():
    return {x['id']: x for x in all_cards()}

def get_card(card_id):
    return card_by_id().get(card_id)

def normalize(value):
    import re
    import unicodedata
    value = unicodedata.normalize('NFKC', str(value)).casefold().replace('ё','е')
    return re.sub(r'[^a-zа-я0-9]+', '', value)

def search_cards(query):
    needle = normalize(query)
    if not needle:
        return []
    return [c for c in all_cards() if any(needle in normalize(a) for a in [c['idol'], c['group'], c['era'], *c.get('aliases', [])])]

def album_groups():
    groups = {}
    for card in all_cards():
        groups.setdefault(card['group'], {}).setdefault(card['era'], []).append(card)
    return groups

def album_sets():
    """All (group, era) sets with >=3 cards."""
    return { (group, era): {c['id'] for c in cards}
        for group, eras in album_groups().items() for era, cards in eras.items() if len(cards) >= 3 }
