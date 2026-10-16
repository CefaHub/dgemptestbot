"""Database schema. PostgreSQL recommended for production; SQLite for local tests."""
from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, Index, Text
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


def engine_and_session(db_url: str):
    extra = {'connect_args': {'timeout': 30}} if db_url.startswith('sqlite') else {}
    engine = create_async_engine(db_url, pool_pre_ping=True, **extra)
    return engine, async_sessionmaker(engine, expire_on_commit=False)

async def init_database(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
