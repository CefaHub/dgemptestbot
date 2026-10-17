"""Server-authoritative transactions. All prices and ownership checked on server.

Production: PostgreSQL uses row-level locks. SQLite is for local development and
single-process demos; SQLite does not honor SELECT FOR UPDATE.
"""
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from .db import Player, OwnedCard, Discovery, Trade, Listing, Ledger
from .catalog import all_cards, get_card, RARITIES, RARITY_EMOJIS, album_sets
from .economy import (paid_price, upgrade_price, slot_upgrade_price, card_income,
    rarity_roll, refill_charges, projected_unclaimed, MAX_OFFLINE_SECONDS, MAX_COIN_BALANCE)


class GameError(Exception):
    """Safe message to show to an end user."""


def day_key(now):
    return now.strftime('%Y-%m-%d')


class Game:
    def __init__(self, session_factory, randbelow=None, clock=None):
        self.sf = session_factory
        self.randbelow = randbelow or secrets.randbelow
        self.clock = clock or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    async def _players_locked(self, session, *user_ids):
        ids = sorted(set(user_ids))
        rows = (await session.scalars(select(Player).where(Player.id.in_(ids))
                                      .order_by(Player.id).with_for_update())).all()
        result = {p.id: p for p in rows}
        if len(result) != len(ids):
            raise GameError('Второй игрок ещё не зарегистрирован: ему нужно нажать /start.')
        return result

    async def _player_locked(self, session, uid):
        p = await session.scalar(select(Player).where(Player.id == uid).with_for_update())
        if p is None:
            raise GameError('Сначала открой игру командой /start.')
        return p

    async def _cards(self, session, uid):
        return (await session.scalars(select(OwnedCard).where(OwnedCard.owner_id == uid)
                                            .order_by(OwnedCard.id))).all()

    async def _discovered(self, session, uid):
        return set((await session.scalars(select(Discovery.definition_id)
                          .where(Discovery.user_id == uid))).all())

    async def _album_bonus(self, session, uid):
        found = await self._discovered(session, uid)
        sets = album_sets()
        complete = sum(1 for ids in sets.values() if ids.issubset(found))
        return min(20, 5 * complete), complete

    async def _income(self, session, uid):
        cards = (await session.scalars(select(OwnedCard)
                    .where(OwnedCard.owner_id == uid, OwnedCard.slot.is_not(None)))).all()
        raw = sum(card_income(get_card(c.definition_id)['base_income'], c.level, c.awakening)
                  for c in cards if get_card(c.definition_id))
        bonus, complete = await self._album_bonus(session, uid)
        return raw * (100 + bonus) // 100, bonus, complete

    async def _settle(self, session, player, now):
        income, _, _ = await self._income(session, player.id)
        pending, remainder, elapsed = projected_unclaimed(income, player.pending_income,
                   player.income_remainder, player.bank_seconds, player.last_claim, now)
        player.pending_income = pending
        player.income_remainder = remainder
        player.bank_seconds = min(MAX_OFFLINE_SECONDS, player.bank_seconds + elapsed)
        player.last_claim = now
        player.peak_income = max(player.peak_income, income)
        return income

    async def _credit(self, session, p, amount, reason, ref=''):
        if amount < 0 or p.coins + amount > MAX_COIN_BALANCE:
            raise GameError('Превышен предел игрового баланса.')
        p.coins += amount
        session.add(Ledger(player_id=p.id, delta=amount, reason=reason, reference=str(ref)))

    async def _debit(self, session, p, amount, reason, ref=''):
        if amount < 0 or p.coins < amount:
            raise GameError(f'Недостаточно монет! Нужно {amount:,} 🪙.'.replace(',', ' '))
        p.coins -= amount
        session.add(Ledger(player_id=p.id, delta=-amount, reason=reason, reference=str(ref)))

    def _quest_today(self, p, now):
        d = day_key(now)
        if p.quest_day != d:
            p.quest_day = d
            p.quest_rolls = p.quest_claims = p.quest_upgrades = p.quest_rewards = 0
        if p.paid_day != d:
            p.paid_day, p.paid_count = d, 0

    async def start(self, uid, display_name):
        async with self.sf() as session, session.begin():
            p = await session.get(Player, uid, with_for_update=True)
            if p:
                p.display_name = (display_name or 'Игрок')[:128]
                return False
            p = Player(id=uid, display_name=(display_name or 'Игрок')[:128], coins=0,
                       last_claim=self.clock())
            session.add(p)
            await session.flush()
            # Offer three DIFFERENT real photographs from the verified sets.
            # Prefer different groups before filling the remaining slot.
            options = all_cards()
            starts, selected_groups = [], set()
            for card in options:
                if len(starts) >= 3:
                    break
                if card['group'] not in selected_groups:
                    starts.append(card)
                    selected_groups.add(card['group'])
            for card in options:
                if len(starts) >= 3:
                    break
                if card['id'] not in {c['id'] for c in starts}:
                    starts.append(card)
            if len(starts) != 3:
                raise RuntimeError('At least three different verified card photos required.')
            for index, c in enumerate(starts, 1):
                session.add(OwnedCard(owner_id=uid, definition_id=c['id'], slot=index))
                session.add(Discovery(user_id=uid, definition_id=c['id']))
            await session.flush()
            p.peak_income = sum(c['base_income'] for c in starts)
            return True

    async def profile(self, uid):
        async with self.sf() as session:
            p = await session.get(Player, uid)
            if not p:
                raise GameError('Сначала /start.')
            now = self.clock()
            charges, refill_at = refill_charges(p.free_charges, p.refill_at, now)
            income, bonus, complete = await self._income(session, uid)
            pending, _, _ = projected_unclaimed(income, p.pending_income, p.income_remainder,
                                                p.bank_seconds, p.last_claim, now)
            self_roll_count = p.paid_count if p.paid_day == day_key(now) else 0
            return {'id':p.id,'name':p.display_name,'coins':p.coins,'income':income,
                    'peak_income':p.peak_income, 'slots':p.slots,'album_bonus':bonus,
                    'complete_sets':complete,'pending':pending,'free':charges,'refill_at':refill_at,
                    'paid_count':self_roll_count,'price': paid_price(max(p.peak_income,income),self_roll_count+1),
                    'premium_price':paid_price(max(p.peak_income,income),self_roll_count+1, True),
                    'total_rolls':p.total_rolls}

    async def cards(self, uid):
        async with self.sf() as session:
            await self._player_locked(session, uid)
            return [self.card_dict(c) for c in await self._cards(session, uid)]

    @staticmethod
    def card_dict(c):
        data = get_card(c.definition_id)
        return {'id':c.id,'definition_id':c.definition_id, 'name':data['idol'] if data else 'Unknown',
                'group':data['group'] if data else '', 'era':data['era'] if data else '',
                'rarity':data['rarity'] if data else 'common', 'level':c.level,
                'awakening':c.awakening, 'slot':c.slot,
                'hourly':card_income(data['base_income'], c.level,c.awakening) if data else 0}

    async def card_details(self, uid, card_id):
        async with self.sf() as session:
            c = await session.get(OwnedCard,card_id)
            if not c or c.owner_id!=uid:
                raise GameError('Карточка не найдена в твоём инвентаре.')
            result=self.card_dict(c)
            result['upgrade_price']=upgrade_price(get_card(c.definition_id)['base_income'],c.level) if c.level<50 else None
            duplicates=(await session.scalars(select(OwnedCard).where(OwnedCard.owner_id==uid,
                   OwnedCard.definition_id==c.definition_id,OwnedCard.id !=c.id,
                   OwnedCard.slot.is_(None)))).all()
            available=[]
            for d in duplicates:
                if not await self._is_listed(session,d.id): available.append(d.id)
            result['dupes']=available
            return result

    async def roll(self, uid, mode):
        if mode not in ('free','paid','premium'):
            raise GameError('Неизвестный баннер.')
        if mode == 'premium' and len({c['rarity'] for c in all_cards()}) < 2:
            raise GameError('Премиум-баннер временно закрыт: пока доступна только одна подтверждённая редкость. Не трать монеты зря.')
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            now=self.clock()
            await self._settle(session,p,now)
            self._quest_today(p,now)
            p.free_charges,p.refill_at=refill_charges(p.free_charges,p.refill_at,now)
            price=0
            if mode=='free':
                if p.free_charges==0:
                    raise GameError('Бесплатных круток пока нет. Приходи через час!')
                p.free_charges-=1
                if p.refill_at is None: p.refill_at=now+timedelta(hours=1)
            else:
                price=paid_price(p.peak_income,p.paid_count+1,mode=='premium')
                await self._debit(session,p,price,'paid_roll',mode)
                p.paid_count+=1
            tier=rarity_roll(self.randbelow,mode=='premium',p.pity_epic,
                             p.pity_legendary,p.pity_mythic,
                             available_rarities={c['rarity'] for c in all_cards()})
            tier_index=RARITIES.index(tier)
            p.pity_epic=0 if tier_index>=2 else p.pity_epic+1
            p.pity_legendary=0 if tier_index>=3 else p.pity_legendary+1
            p.pity_mythic=0 if tier_index>=4 else p.pity_mythic+1
            pool=[c for c in all_cards() if c['rarity']==tier]
            if not pool: raise RuntimeError(f'No cards in rarity {tier}')
            # Premium focus banner: 70% group focus, without changing declared rarity odds.
            from .catalog import album_groups
            groups=list(album_groups())
            focus=groups[now.isocalendar().week % len(groups)]
            focus_pool=[c for c in pool if c['group']==focus]
            if mode=='premium' and focus_pool and self.randbelow(100)<70:
                pool=focus_pool
            selected=pool[self.randbelow(len(pool))]
            c=OwnedCard(owner_id=uid,definition_id=selected['id'])
            session.add(c)
            await session.flush()
            already=await session.get(Discovery,(uid,selected['id']))
            if not already:
                session.add(Discovery(user_id=uid,definition_id=selected['id']))
            p.total_rolls+=1
            p.quest_rolls+=1
            return {'card':self.card_dict(c),'price':price,'focus':focus,'pity':(p.pity_epic,p.pity_legendary,p.pity_mythic)}

    async def claim(self,uid):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            now=self.clock()
            await self._settle(session,p,now)
            amount=p.pending_income
            if amount <= 0: raise GameError('Монеты ещё не накопились.')
            await self._credit(session,p,amount,'tycoon_claim')
            p.pending_income=0
            p.bank_seconds=0
            p.total_collected+=amount
            self._quest_today(p,now)
            p.quest_claims+=1
            return amount,p.coins

    async def equip(self,uid,card_id,slot):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            if not 1<=slot<=p.slots: raise GameError('Этот слот пока закрыт.')
            c=await session.get(OwnedCard,card_id,with_for_update=True)
            if not c or c.owner_id!=uid: raise GameError('Карточка не найдена.')
            if await self._is_listed(session,c.id): raise GameError('Эта карточка выставлена на рынок.')
            await self._settle(session,p,self.clock())
            occupied=await session.scalar(select(OwnedCard).where(OwnedCard.owner_id==uid,OwnedCard.slot==slot).with_for_update())
            if occupied: occupied.slot=None
            c.slot=slot
            await session.flush()
            current,_,_=await self._income(session,uid)
            p.peak_income=max(p.peak_income,current)
            return self.card_dict(c)

    async def unequip(self,uid,card_id):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            c=await session.get(OwnedCard,card_id,with_for_update=True)
            if not c or c.owner_id!=uid: raise GameError('Карточка не найдена.')
            await self._settle(session,p,self.clock())
            c.slot=None

    async def upgrade(self,uid,card_id):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            c=await session.get(OwnedCard,card_id,with_for_update=True)
            if not c or c.owner_id!=uid: raise GameError('Карточка не найдена.')
            if c.level>=50: raise GameError('Карточка уже максимального уровня.')
            if await self._is_listed(session,c.id): raise GameError('Карточка выставлена на рынок.')
            await self._settle(session,p,self.clock())
            cost=upgrade_price(get_card(c.definition_id)['base_income'],c.level)
            await self._debit(session,p,cost,'card_upgrade',c.id)
            c.level+=1
            self._quest_today(p,self.clock())
            p.quest_upgrades+=1
            await session.flush()
            current,_,_=await self._income(session,uid)
            p.peak_income=max(p.peak_income,current)
            return self.card_dict(c),cost

    async def awaken(self,uid,card_id):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            c=await session.get(OwnedCard,card_id,with_for_update=True)
            if not c or c.owner_id!=uid: raise GameError('Карточка не найдена.')
            if c.awakening>=5: raise GameError('Максимум 5 пробуждений.')
            if await self._is_listed(session,c.id): raise GameError('Карточка выставлена на рынок.')
            dupes=(await session.scalars(select(OwnedCard).where(OwnedCard.owner_id==uid,
                   OwnedCard.definition_id==c.definition_id,OwnedCard.id!=c.id,
                   OwnedCard.slot.is_(None)).order_by(OwnedCard.id).with_for_update())).all()
            spare=None
            for d in dupes:
                if not await self._is_listed(session,d.id): spare=d; break
            if spare is None: raise GameError('Для пробуждения нужен дубликат той же карточки (не в слоте и не на рынке).')
            await self._settle(session,p,self.clock())
            await session.delete(spare)
            c.awakening+=1
            await session.flush()
            current,_,_=await self._income(session,uid)
            p.peak_income=max(p.peak_income,current)
            return self.card_dict(c),spare.id

    async def upgrade_studio(self,uid):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            if p.slots>=8: raise GameError('Все 8 слотов открыты!')
            await self._settle(session,p,self.clock())
            cost=slot_upgrade_price(p.slots)
            await self._debit(session,p,cost,'studio_slot',p.slots+1)
            p.slots+=1
            return p.slots,cost

    async def daily(self,uid):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            now=self.clock(); self._quest_today(p,now)
            if p.last_daily==day_key(now): raise GameError('Ежедневный подарок уже получен. Возвращайся завтра по UTC!')
            await self._settle(session,p,now)
            income,_,_=await self._income(session,uid)
            reward=min(1000000,max(500,income*2))
            await self._credit(session,p,reward,'daily_reward')
            p.last_daily=day_key(now)
            return reward

    async def quests(self,uid):
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            self._quest_today(p,self.clock())
            return {'roll':p.quest_rolls,'claim':p.quest_claims,'upgrade':p.quest_upgrades,
                    'claimed_mask':p.quest_rewards,'can_daily':p.last_daily!=day_key(self.clock())}

    async def quest_reward(self,uid,kind):
        specs={'roll':(1,1),'claim':(2,1),'upgrade':(4,1)}
        if kind not in specs: raise GameError('Неизвестное задание.')
        bit,needed=specs[kind]
        async with self.sf() as session,session.begin():
            p=await self._player_locked(session,uid)
            self._quest_today(p,self.clock())
            if p.quest_rewards & bit: raise GameError('Награда уже получена.')
            if getattr(p,{'roll':'quest_rolls','claim':'quest_claims','upgrade':'quest_upgrades'}[kind])<needed:
                raise GameError('Задание ещё не выполнено.')
            income,_,_=await self._income(session,uid)
            reward=max(250,min(500000,income))
            await self._credit(session,p,reward,'quest',kind)
            p.quest_rewards|=bit
            return reward

    async def album(self,uid):
        async with self.sf() as session:
            p=await self._player_locked(session,uid)
            found=await self._discovered(session,uid)
            sets=album_sets()
            return [{'group':group,'era':era,'total':len(ids),'found':len(ids.intersection(found)),
                     'completed':ids.issubset(found)} for (group,era),ids in sets.items()]

    async def _is_listed(self,session,card_id):
        return await session.scalar(select(Listing.id).where(Listing.card_id==card_id,Listing.status=='active')) is not None

    async def offer_trade(self,sender,receiver,sender_card_id,receiver_card_id,sender_coins=0,receiver_coins=0):
        if sender==receiver or sender_coins<0 or receiver_coins<0 or sender_coins>10**12 or receiver_coins>10**12:
            raise GameError('Неверные условия обмена.')
        if not(sender_card_id or receiver_card_id or sender_coins or receiver_coins):
            raise GameError('В обмене должно быть хотя бы что-то.')
        if sender_card_id and sender_card_id==receiver_card_id: raise GameError('Карточки должны быть разными.')
        async with self.sf() as session,session.begin():
            people=await self._players_locked(session,sender,receiver)
            now=self.clock()
            for p in people.values(): await self._settle(session,p,now)
            active=await session.scalar(select(func.count()).select_from(Trade)
                            .where(Trade.sender_id==sender,Trade.status.in_(['pending','accepted'])))
            if active>=5: raise GameError('У тебя уже 5 активных предложений.')
            for cid,owner in [(sender_card_id,sender),(receiver_card_id,receiver)]:
                if cid:
                    c=await session.get(OwnedCard,cid,with_for_update=True)
                    if not c or c.owner_id!=owner or c.slot is not None or await self._is_listed(session,cid):
                        raise GameError(f'Карточка #{cid} не может участвовать в обмене.')
            if people[sender].coins<sender_coins or people[receiver].coins<receiver_coins:
                raise GameError('Недостаточно монет для указанных условий.')
            trade=Trade(sender_id=sender,receiver_id=receiver,
                        sender_card_id=sender_card_id or None,receiver_card_id=receiver_card_id or None,
                        sender_coins=sender_coins,receiver_coins=receiver_coins,
                        status='pending',created_at=now)
            session.add(trade)
            await session.flush()
            return trade.id

    async def trade_details(self,user_id,trade_id):
        async with self.sf() as session:
            t=await session.get(Trade,trade_id)
            if not t or user_id not in (t.sender_id,t.receiver_id): raise GameError('Сделка не найдена.')
            return self._trade_dict(t)

    @staticmethod
    def _trade_dict(t):
        return {'id':t.id,'sender':t.sender_id,'receiver':t.receiver_id,
                'sender_card':t.sender_card_id,'receiver_card':t.receiver_card_id,
                'sender_coins':t.sender_coins,'receiver_coins':t.receiver_coins,'status':t.status}

    async def trade_action(self,user_id,trade_id,action):
        async with self.sf() as session,session.begin():
            t=await session.get(Trade,trade_id,with_for_update=True)
            if not t or user_id not in (t.sender_id,t.receiver_id): raise GameError('Сделка не найдена.')
            if t.status not in ('pending','accepted'): raise GameError('Сделка уже закрыта.')
            if self.clock()-t.created_at>timedelta(hours=48):
                t.status='expired'
                return 'expired'
            if action=='cancel':
                t.status='cancelled'
                return 'cancelled'
            if action=='accept':
                if user_id!=t.receiver_id or t.status!='pending': raise GameError('Подтвердить должен получатель.')
                t.status='accepted';t.accepted_at=self.clock();return 'accepted'
            if action!='confirm' or user_id!=t.sender_id or t.status!='accepted':
                raise GameError('Сначала обмен должен принять второй игрок.')
            ppl=await self._players_locked(session,t.sender_id,t.receiver_id)
            now=self.clock()
            for p in ppl.values(): await self._settle(session,p,now)
            owned=[]
            for cid,owner in [(t.sender_card_id,t.sender_id),(t.receiver_card_id,t.receiver_id)]:
                if cid:
                    c=await session.get(OwnedCard,cid,with_for_update=True)
                    if not c or c.owner_id!=owner or c.slot is not None or await self._is_listed(session,cid):
                        raise GameError('Одна из карточек больше недоступна. Отмените обмен.')
                    owned.append((c,owner))
            if ppl[t.sender_id].coins<t.sender_coins or ppl[t.receiver_id].coins<t.receiver_coins:
                raise GameError('Баланс одного из участников изменился. Отмените обмен.')
            if t.sender_coins:
                await self._debit(session,ppl[t.sender_id],t.sender_coins,'trade_send',t.id)
                await self._credit(session,ppl[t.receiver_id],t.sender_coins,'trade_receive',t.id)
            if t.receiver_coins:
                await self._debit(session,ppl[t.receiver_id],t.receiver_coins,'trade_send',t.id)
                await self._credit(session,ppl[t.sender_id],t.receiver_coins,'trade_receive',t.id)
            for c,owner in owned:
                dest=t.receiver_id if owner==t.sender_id else t.sender_id
                c.owner_id=dest
                c.slot=None
                if not await session.get(Discovery,(dest,c.definition_id)):
                    session.add(Discovery(user_id=dest,definition_id=c.definition_id))
            t.status='completed'
            return 'completed'

    async def list_card(self,uid,card_id,price):
        if price < 100 or price>10**12: raise GameError('Цена на рынке должна быть от 100 до 1 000 000 000 000.')
        async with self.sf() as session,session.begin():
            await self._player_locked(session,uid)
            c=await session.get(OwnedCard,card_id,with_for_update=True)
            if not c or c.owner_id!=uid or c.slot is not None or await self._is_listed(session,card_id):
                raise GameError('Карточка должна быть твоей, свободной и не на рынке.')
            count=await session.scalar(select(func.count()).select_from(Listing)
                     .where(Listing.seller_id==uid,Listing.status=='active'))
            if count>=10: raise GameError('У тебя уже 10 объявлений.')
            listing=Listing(seller_id=uid,card_id=card_id,price=price)
            session.add(listing);await session.flush()
            return listing.id

    async def market(self):
        async with self.sf() as session:
            entries=(await session.scalars(select(Listing).where(Listing.status=='active')
                       .order_by(Listing.created_at.desc(),Listing.id.desc()).limit(12))).all()
            output=[]
            for item in entries:
                c=await session.get(OwnedCard,item.card_id)
                if c:
                    output.append({'id':item.id,'price':item.price,'seller':item.seller_id,
                                   'card':self.card_dict(c)})
            return output

    async def cancel_listing(self,uid,listing_id):
        async with self.sf() as session,session.begin():
            l=await session.get(Listing,listing_id,with_for_update=True)
            if not l or l.seller_id!=uid or l.status!='active': raise GameError('Объявление не найдено.')
            l.status='cancelled'

    async def buy(self,uid,listing_id):
        async with self.sf() as session,session.begin():
            listing=await session.get(Listing,listing_id,with_for_update=True)
            if not listing or listing.status!='active': raise GameError('Объявление больше не активно.')
            if listing.seller_id==uid: raise GameError('Нельзя покупать у себя.')
            ppl=await self._players_locked(session,uid,listing.seller_id)
            now=self.clock()
            for p in ppl.values():await self._settle(session,p,now)
            c=await session.get(OwnedCard,listing.card_id,with_for_update=True)
            if not c or c.owner_id!=listing.seller_id or c.slot is not None:
                raise GameError('Карточка более недоступна.')
            await self._debit(session,ppl[uid],listing.price,'market_purchase',listing.id)
            tax=listing.price*5//100
            await self._credit(session,ppl[listing.seller_id],listing.price-tax,'market_sale',listing.id)
            c.owner_id=uid
            listing.buyer_id=uid
            listing.status='sold'
            listing.completed_at=now
            if not await session.get(Discovery,(uid,c.definition_id)):
                session.add(Discovery(user_id=uid,definition_id=c.definition_id))
            return self.card_dict(c),tax

    async def leaders(self,kind):
        key={'rich':'coins','income':'peak_income','rolls':'total_rolls','collector':'total_collected'}.get(kind)
        if not key: raise GameError('Неизвестный рейтинг.')
        async with self.sf() as session:
            vals=(await session.scalars(select(Player).order_by(getattr(Player,key).desc()).limit(10))).all()
            return [{'name':p.display_name,'id':p.id,'value':getattr(p,key)} for p in vals]

    async def recent_trades(self,uid):
        async with self.sf() as session:
            trs=(await session.scalars(select(Trade).where((Trade.sender_id==uid)|(Trade.receiver_id==uid))
                       .order_by(Trade.id.desc()).limit(10))).all()
            return [self._trade_dict(t) for t in trs]
