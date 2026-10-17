from datetime import timedelta
import pytest
from sqlalchemy import select
from dolce_empire.service import GameError
from dolce_empire.db import OwnedCard, Listing, Trade

@pytest.mark.asyncio
async def test_start_roll_claim_upgrades(env):
    game,clock,factory=env
    assert await game.start(101,'<Admin>') is True
    assert await game.start(101,'<Admin>') is False
    p=await game.profile(101)
    assert p['income']==660 and p['slots']==3 and p['free']==3
    assert p['price']==5280
    rolled=await game.roll(101,'free')
    assert rolled['price']==0 and rolled['card']['rarity'] in {'rare', 'epic', 'legendary', 'mythic'}
    assert (await game.profile(101))['free']==2
    clock.now+=timedelta(hours=2)
    p=await game.profile(101)
    assert p['pending']==1320 and p['free']==3
    amount,balance=await game.claim(101)
    assert amount==1320 and balance==1320
    with pytest.raises(GameError):await game.roll(101,'paid')
    assert (await game.profile(101))['coins']==1320
    await game.daily(101)
    clock.now+=timedelta(hours=3)
    await game.claim(101)
    cards=await game.cards(101)
    target=cards[0]
    upgraded,cost=await game.upgrade(101,target['id'])
    assert upgraded['level']==2 and cost==3960
    assert (await game.profile(101))['income']>660
    with pytest.raises(GameError):await game.upgrade(101,999999)

@pytest.mark.asyncio
async def test_tycoon_no_history_minting(env):
    game,clock,factory=env
    await game.start(11,'A')
    deck=await game.cards(11)
    clock.now+=timedelta(hours=5)
    card=await game.roll(11,'free')
    await game.equip(11,card['card']['id'],1)
    pending=(await game.profile(11))['pending']
    assert pending==3300 # previous 5 hours ×660, not new equipped rate
    clock.now+=timedelta(hours=24)
    p=await game.profile(11)
    assert p['pending'] == 3300 + p['income']*7  # 12h total cap, 5 already banked
    got,_=await game.claim(11)
    assert got==p['pending']
    assert (await game.profile(11))['pending']==0

@pytest.mark.asyncio
async def test_trade_happy_path_and_double_spend(env):
    game,clock,factory=env
    await game.start(1,'A')
    await game.start(2,'B')
    a=(await game.roll(1,'free'))['card']['id']
    b=(await game.roll(2,'free'))['card']['id']
    await game.daily(1);await game.daily(2)
    tid=await game.offer_trade(1,2,a,b,100,40)
    assert await game.trade_action(2,tid,'accept')=='accepted'
    assert await game.trade_action(1,tid,'confirm')=='completed'
    with pytest.raises(GameError):await game.trade_action(1,tid,'confirm')
    assert any(c['id']==a for c in await game.cards(2))
    assert any(c['id']==b for c in await game.cards(1))
    p1=await game.profile(1);p2=await game.profile(2)
    assert p1['coins']==1260 and p2['coins']==1380

@pytest.mark.asyncio
async def test_trade_validations(env):
    game,clock,_=env
    await game.start(1,'A');await game.start(2,'B')
    a=(await game.cards(1))[0]['id'] # active
    with pytest.raises(GameError):await game.offer_trade(1,2,a,0)
    with pytest.raises(GameError):await game.offer_trade(1,1,0,0,1)
    with pytest.raises(GameError):await game.offer_trade(1,2,0,0)
    with pytest.raises(GameError):await game.offer_trade(1,3,0,0,5)

@pytest.mark.asyncio
async def test_market_tax_and_no_double_purchase(env):
    game,clock,_=env
    await game.start(1,'A');await game.start(2,'B');await game.start(3,'C')
    cid=(await game.roll(1,'free'))['card']['id']
    await game.daily(2)
    lot=await game.list_card(1,cid,500)
    card,tax=await game.buy(2,lot)
    assert card['id']==cid and tax==25
    assert (await game.profile(1))['coins']==475
    assert (await game.profile(2))['coins']==820
    with pytest.raises(GameError):await game.buy(3,lot)
    with pytest.raises(GameError):await game.cancel_listing(1,lot)

@pytest.mark.asyncio
async def test_awakening_consumes_one_copy(env):
    game,clock,_=env
    await game.start(1,'A')
    a=(await game.roll(1,'free'))['card']
    b=(await game.roll(1,'free'))['card']
    assert a['definition_id']==b['definition_id'] # RNG fixed at first available Epic
    c,used=await game.awaken(1,a['id'])
    assert c['awakening']==1 and used==b['id']
    assert not any(x['id']==b['id'] for x in await game.cards(1))

@pytest.mark.asyncio
async def test_quest_rewards_are_idempotent(env):
    game,clock,_=env
    await game.start(1,'A')
    await game.roll(1,'free')
    reward=await game.quest_reward(1,'roll')
    assert reward>=250
    with pytest.raises(GameError):await game.quest_reward(1,'roll')
    with pytest.raises(GameError):await game.quest_reward(1,'upgrade')
    clock.now+=timedelta(days=1)
    assert (await game.quests(1))['roll']==0

@pytest.mark.asyncio
async def test_no_market_or_trade_active_cards(env):
    game,clock,_=env
    await game.start(1,'A')
    await game.start(2,'B')
    active=(await game.cards(1))[0]
    with pytest.raises(GameError):await game.list_card(1,active['id'],100)
    await game.unequip(1,active['id'])
    listing=await game.list_card(1,active['id'],100)
    with pytest.raises(GameError):await game.equip(1,active['id'],1)
    with pytest.raises(GameError):await game.upgrade(1,active['id'])
    with pytest.raises(GameError):await game.offer_trade(1,2,active['id'],0)
    await game.cancel_listing(1,listing)
    await game.equip(1,active['id'],1)

@pytest.mark.asyncio
async def test_trade_fails_if_card_sold_before_final_acceptance(env):
    game,clock,_=env
    await game.start(1,'A');await game.start(2,'B');await game.start(3,'C')
    card=(await game.roll(1,'free'))['card']
    tid=await game.offer_trade(1,2,card['id'],0)
    await game.trade_action(2,tid,'accept')
    lot=await game.list_card(1,card['id'],100)
    await game.daily(3)
    await game.buy(3,lot)
    with pytest.raises(GameError):await game.trade_action(1,tid,'confirm')
    assert (await game.trade_details(1,tid))['status']=='accepted'
    assert any(c['id']==card['id'] for c in await game.cards(3))


@pytest.mark.asyncio
async def test_premium_mode_disabled_until_another_verified_rarity_exists(env):
    game, clock, _ = env
    await game.start(909, 'Collector')
    from dolce_empire.catalog import all_cards
    if len({c['rarity'] for c in all_cards()}) >= 2:
        pytest.skip('Premium enabled with multiple verified rarities')
    before = (await game.profile(909))['coins']
    with pytest.raises(GameError, match='Премиум'):
        await game.roll(909, 'premium')
    assert (await game.profile(909))['coins'] == before
