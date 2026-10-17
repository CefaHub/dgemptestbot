"""Database schema. PostgreSQL recommended for production; SQLite for local tests."""
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index, Text, delete, select, text, or_, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class Player(Base):
    __tablename__ = 'players'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default='Игрок')
    coins: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    peak_income: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    slots: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    free_charges: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    refill_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pity_epic: Mapped[int] = mapped_column(Integer, default=0)
    pity_legendary: Mapped[int] = mapped_column(Integer, default=0)
    pity_mythic: Mapped[int] = mapped_column(Integer, default=0)
    paid_day: Mapped[str] = mapped_column(String(10), default='')
    paid_count: Mapped[int] = mapped_column(Integer, default=0)
    total_rolls: Mapped[int] = mapped_column(Integer, default=0)
    total_collected: Mapped[int] = mapped_column(BigInteger, default=0)
    last_claim: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    income_remainder: Mapped[int] = mapped_column(Integer, default=0)
    pending_income: Mapped[int] = mapped_column(BigInteger, default=0)
    bank_seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_daily: Mapped[str] = mapped_column(String(10), default='')
    quest_day: Mapped[str] = mapped_column(String(10), default='')
    quest_rolls: Mapped[int] = mapped_column(Integer, default=0)
    quest_claims: Mapped[int] = mapped_column(Integer, default=0)
    quest_upgrades: Mapped[int] = mapped_column(Integer, default=0)
    quest_rewards: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class OwnedCard(Base):
    __tablename__ = 'owned_cards'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('players.id'), index=True)
    definition_id: Mapped[str] = mapped_column(String(140), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    awakening: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (Index('idx_owned_active', 'owner_id', 'slot'),)

class Discovery(Base):
    __tablename__ = 'discoveries'
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('players.id'), primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(140), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Trade(Base):
    __tablename__ = 'trades'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('players.id'))
    receiver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('players.id'))
    sender_card_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receiver_card_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sender_coins: Mapped[int] = mapped_column(BigInteger, default=0)
    receiver_coins: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Listing(Base):
    __tablename__ = 'listings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('players.id'))
    buyer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey('owned_cards.id'))
    price: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default='active')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index('idx_listing_status', 'status', 'created_at'),)

class Ledger(Base):
    __tablename__ = 'ledger'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(BigInteger, index=True)
    delta: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(80))
    reference: Mapped[str] = mapped_column(String(128), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ResetMarker(Base):
    """Persists completed resets so a new Docker deployment never wipes players twice."""
    __tablename__ = 'game_reset_markers'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# Increase this ONLY when an explicitly requested new worldwide wipe is needed.
PHOTO_ONLY_RESET_KEY = 'photo_only_world_reset_2026_10_16_v1'


async def reset_all_players_once(engine, key: str = PHOTO_ONLY_RESET_KEY) -> bool:
    """Clear all gameplay in one DB transaction, once per persistent database.

    Handles PostgreSQL and SQLite. Git pull alone cannot reset Bothost state:
    the reset is performed at boot *before* Telegram polling begins.
    Returns True only if this invocation performed the wipe.
    """
    async with engine.begin() as conn:
        if conn.dialect.name == 'postgresql':
            # Serializes concurrent workers trying to apply the same migration.
            await conn.execute(text('SELECT pg_advisory_xact_lock(20261016084)'))
        existing = await conn.scalar(
            select(ResetMarker.key).where(ResetMarker.key == key)
        )
        if existing is not None:
            return False
        # Child records first, so FK enforcement remains valid in both DBs.
        for model in (Listing, Trade, Discovery, OwnedCard, Ledger, Player):
            await conn.execute(delete(model))
        await conn.execute(
            ResetMarker.__table__.insert().values(key=key, applied_at=utcnow())
        )
        return True


CURATION_RESET_KEY = 'retire_unverified_photo_sets_2026_10_17_v1'


async def retire_unverified_cards_once(engine, valid_definitions, key: str = CURATION_RESET_KEY):
    """Retire bad photo sets atomically while retaining players and their coins.

    Clear old collectibles/discovery and related open trades/listings; never
    reset an entire user account. Marker makes process safe on every restart.
    """
    if not valid_definitions:
        raise ValueError('Refusing to retire collectibles without verified replacements')
    valid_ids = set(valid_definitions)
    async with engine.begin() as conn:
        if conn.dialect.name == 'postgresql':
            await conn.execute(text('SELECT pg_advisory_xact_lock(20261017009)'))
        exists = await conn.scalar(select(ResetMarker.key).where(ResetMarker.key == key))
        if exists is not None:
            return False
        invalid_ids = select(OwnedCard.id).where(
            OwnedCard.definition_id.not_in(sorted(valid_ids))
        )
        # Listings FK -> owned_cards, so remove those first.
        await conn.execute(delete(Listing).where(Listing.card_id.in_(invalid_ids)))
        await conn.execute(delete(Trade).where(or_(
            Trade.sender_card_id.in_(invalid_ids),
            Trade.receiver_card_id.in_(invalid_ids),
        )))
        await conn.execute(delete(Discovery).where(
            Discovery.definition_id.not_in(sorted(valid_ids))
        ))
        await conn.execute(delete(OwnedCard).where(
            OwnedCard.definition_id.not_in(sorted(valid_ids))
        ))
        # Recalculate peak studio income excluding all removed studio slots;
        # old retired Mythic cards must not inflate future gacha prices.
        rows = await conn.execute(select(OwnedCard.owner_id, OwnedCard.definition_id,
                                         OwnedCard.level, OwnedCard.awakening)
                                  .where(OwnedCard.slot.is_not(None)))
        incomes = {}
        for uid, cid, level, awakening in rows:
            base = valid_definitions[cid]
            earned = base * (100 + (level - 1) * 6) * (100 + awakening * 20) // 10000
            incomes[uid] = incomes.get(uid, 0) + earned
        await conn.execute(update(Player).values(peak_income=0))
        for uid, amount in incomes.items():
            await conn.execute(update(Player).where(Player.id == uid)
                               .values(peak_income=amount))
        await conn.execute(ResetMarker.__table__.insert().values(key=key, applied_at=utcnow()))
        return True


def engine_and_session(db_url: str):
    extra = {'connect_args': {'timeout': 30}} if db_url.startswith('sqlite') else {}
    engine = create_async_engine(db_url, pool_pre_ping=True, **extra)
    return engine, async_sessionmaker(engine, expire_on_commit=False)

async def init_database(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
