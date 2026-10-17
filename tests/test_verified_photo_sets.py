"""Do not let mixed photo sets or retired trading objects enter the live game."""
import copy
import json

import pytest
from sqlalchemy import func, select

from dolce_empire.catalog import all_cards
from dolce_empire.set_validation import validate_photo_sets, SOURCES_FILE
from dolce_empire.db import (
    Player, OwnedCard, Discovery, Listing, Trade, Ledger, ResetMarker,
    engine_and_session, init_database, retire_unverified_cards_once,
    CURATION_RESET_KEY,
)


def test_photo_series_fail_closed(monkeypatch, tmp_path):
    verified = all_cards()
    assert validate_photo_sets(verified) == 9
    bad = copy.deepcopy(verified)
    bad[0]['rarity'] = 'mythic'
    with pytest.raises(ValueError, match='Mixed rarity'):
        validate_photo_sets(bad)
    bad = copy.deepcopy(verified)
    bad[0]['idol'] = 'Winter'
    with pytest.raises(ValueError, match='member'):
        validate_photo_sets(bad)
    bad = copy.deepcopy(verified)
    bad.append(copy.deepcopy(bad[0]))
    with pytest.raises(ValueError):
        validate_photo_sets(bad)
    sources = json.loads(SOURCES_FILE.read_text(encoding='utf-8'))
    sources['cards'][1]['page'] = sources['cards'][0]['page']
    tmp = tmp_path / 'sources.json'
    tmp.write_text(json.dumps(sources), encoding='utf-8')
    from dolce_empire import set_validation
    monkeypatch.setattr(set_validation, 'SOURCES_FILE', tmp)
    with pytest.raises(ValueError, match='(reused|Mixed)'):
        validate_photo_sets(verified)


@pytest.mark.asyncio
async def test_retired_card_migration_preserves_money_and_runs_once(tmp_path):
    db_url = 'sqlite+aiosqlite:///' + str(tmp_path / 'active_players.db')
    engine, sf = engine_and_session(db_url)
    await init_database(engine)
    valid = all_cards()[0]
    async with sf() as session, session.begin():
        session.add_all([
            Player(id=1, display_name='Player One', coins=7777, peak_income=99999),
            Player(id=2, display_name='Player Two', coins=500),
        ])
        await session.flush()
        valid_card = OwnedCard(owner_id=1, definition_id=valid['id'], slot=1)
        retired_card = OwnedCard(owner_id=1, definition_id='card_ive_velvet_light_legendary_yujin_01', slot=2)
        session.add_all([valid_card, retired_card])
        session.add(Discovery(user_id=1, definition_id=valid['id']))
        session.add(Discovery(user_id=1, definition_id=retired_card.definition_id))
        await session.flush()
        session.add(Listing(seller_id=1, card_id=retired_card.id, price=1000))
        session.add(Trade(sender_id=1, receiver_id=2, sender_card_id=retired_card.id,
                          receiver_card_id=None, status='pending'))
        session.add(Ledger(player_id=1,delta=7777,reason='old_reward'))
    valid_definitions = {c['id']: c['base_income'] for c in all_cards()}
    assert await retire_unverified_cards_once(engine, valid_definitions) is True
    async with sf() as session:
        assert (await session.get(Player, 1)).coins == 7777
        assert (await session.get(Player, 2)).coins == 500
        assert (await session.get(Player, 1)).peak_income == 220
        owned = (await session.scalars(select(OwnedCard))).all()
        assert len(owned) == 1 and owned[0].definition_id == valid['id']
        assert await session.scalar(select(func.count()).select_from(Listing)) == 0
        assert await session.scalar(select(func.count()).select_from(Trade)) == 0
        assert await session.scalar(select(func.count()).select_from(Discovery)) == 1
        assert await session.scalar(select(func.count()).select_from(Ledger)) == 1
        assert await session.get(ResetMarker, CURATION_RESET_KEY)
    assert await retire_unverified_cards_once(engine, valid_definitions) is False
    await engine.dispose()
    engine2,sf2 = engine_and_session(db_url)
    await init_database(engine2)
    assert await retire_unverified_cards_once(engine2, valid_definitions) is False
    async with sf2() as session:
        assert (await session.get(Player, 1)).coins == 7777
    await engine2.dispose()
