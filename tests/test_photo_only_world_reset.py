"""A one-time worldwide wipe must clear every player record atomically.

Running it again must preserve any new progress made after the reset.
"""
import pytest
from sqlalchemy import func, select
from dolce_empire.db import (
    Player, OwnedCard, Discovery, Trade, Listing, Ledger, ResetMarker,
    engine_and_session, init_database, reset_all_players_once, PHOTO_ONLY_RESET_KEY,
)
from dolce_empire.catalog import all_cards


@pytest.mark.asyncio
async def test_reset_removes_all_old_progress_only_once(tmp_path):
    engine, sf = engine_and_session(
        'sqlite+aiosqlite:///' + str(tmp_path / 'existing_empire.db')
    )
    await init_database(engine)
    old_card = all_cards()[0]['id']
    async with sf() as session, session.begin():
        session.add_all([
            Player(id=1001, display_name='Old', coins=100000, peak_income=8000),
            Player(id=1002, display_name='Other', coins=1000),
        ])
        await session.flush()
        old_owned = OwnedCard(owner_id=1001, definition_id=old_card, slot=1)
        session.add(old_owned)
        session.add(Discovery(user_id=1001, definition_id=old_card))
        session.add(Trade(sender_id=1001, receiver_id=1002, sender_coins=10,
                          receiver_coins=10, status='pending'))
        session.add(Ledger(player_id=1001, delta=100000, reason='old'))
        await session.flush()
        session.add(Listing(seller_id=1001, card_id=old_owned.id,
                            price=12345, status='active'))
    assert await reset_all_players_once(engine) is True
    async with sf() as session:
        for model in (Listing, Trade, Discovery, OwnedCard, Ledger, Player):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        assert await session.get(ResetMarker, PHOTO_ONLY_RESET_KEY) is not None

    # A new user after the wipe must survive subsequent container restarts.
    async with sf() as session, session.begin():
        session.add(Player(id=3003, display_name='After reset', coins=567))
    assert await reset_all_players_once(engine) is False
    async with sf() as session:
        player = await session.get(Player, 3003)
        assert player and player.coins == 567
    await engine.dispose()

    # Reconnect the same persistent file, emulating a Docker restart.
    engine2, sf2 = engine_and_session(
        'sqlite+aiosqlite:///' + str(tmp_path / 'existing_empire.db')
    )
    await init_database(engine2)
    assert await reset_all_players_once(engine2) is False
    async with sf2() as session:
        assert (await session.get(Player, 3003)).coins == 567
    await engine2.dispose()
