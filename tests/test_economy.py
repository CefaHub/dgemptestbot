from datetime import datetime, timedelta
from dolce_empire.economy import (paid_price, upgrade_price, slot_upgrade_price,
                                  rarity_roll, refill_charges, projected_unclaimed)
from dolce_empire.catalog import all_cards, album_sets, search_cards

def test_price_growth():
    assert paid_price(0,1)==2000
    assert paid_price(1000,1)==8000
    assert paid_price(100000,1)==800000
    assert paid_price(100000,2)==920000
    assert paid_price(100000,3)==1040000
    assert paid_price(100000,1,True)==3200000
    assert paid_price(100000,3)>paid_price(100000,1)

def test_pity_and_refill():
    assert rarity_roll(lambda n:0,pity_epic=9)=='epic'
    assert rarity_roll(lambda n:0,pity_legendary=39)=='legendary'
    assert rarity_roll(lambda n:0,pity_mythic=149)=='mythic'
    now=datetime(2026,10,16,12)
    assert refill_charges(0,now+timedelta(hours=1),now)==(0,now+timedelta(hours=1))
    assert refill_charges(0,now-timedelta(hours=4),now)==(3,None)

def test_catalog_transliterations_and_sets():
    assert len(all_cards()) == 9
    assert any(x['idol']=='Yunah' for x in search_cards('юна'))
    assert any(x['idol']=='Karina' for x in search_cards('карина'))
    assert len(album_sets()) == 2


def test_verified_photo_sets_and_active_rarities():
    from pathlib import Path
    from dolce_empire.set_validation import validate_photo_sets
    cards = all_cards()
    assert validate_photo_sets(cards) == 9
    rarities = {card['rarity'] for card in cards}
    assert rarities == {'epic'}
    from collections import Counter
    groups = Counter((c['group'],c['era'],c['rarity']) for c in cards)
    assert groups == {('ILLIT','SPOTLIGHT','epic'):5,('aespa','SPOTLIGHT','epic'):4}
    for premium in (False,True):
        for value in range(0,200,7):
            assert rarity_roll(lambda n, value=value:value % n,
                               premium=premium,available_rarities=rarities) == 'epic'
    assert all(Path(c['image_path']).is_file() for c in cards)



def test_income_cap():
    start=datetime(2026,10,16,0)
    pending,_,seconds=projected_unclaimed(100,0,0,0,start,start+timedelta(days=1))
    assert pending==1200
    assert seconds==12*3600
    assert upgrade_price(100,1)<upgrade_price(100,3)
    assert slot_upgrade_price(3)==7500


def test_catalog_independent_of_data_volume(monkeypatch, tmp_path):
    # Bothost can mount a blank volume at /app/data; catalogue must still load.
    from dolce_empire import catalog as module
    module.all_cards.cache_clear()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    assert len(module.all_cards()) == 9
    module.all_cards.cache_clear()
