"""Run database integration tests even offline (using SQLAlchemy's sync SQLite driver).
Production code still uses AsyncSession and actual asyncpg/aiosqlite drivers.
"""
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dolce_empire.db import Base
from dolce_empire.service import Game

class AsyncSessionShim:
    def __init__(self,factory):
        self._session=factory()
    async def __aenter__(self):return self
    async def __aexit__(self,*exc):self._session.close()
    def begin(self):return SyncTxShim(self._session.begin())
    async def get(self,*a,**kw):return self._session.get(*a,**kw)
    async def scalar(self,*a,**kw):return self._session.scalar(*a,**kw)
    async def scalars(self,*a,**kw):return self._session.scalars(*a,**kw)
    async def flush(self):return self._session.flush()
    async def delete(self,x):return self._session.delete(x)
    def add(self,x):return self._session.add(x)

class SyncTxShim:
    def __init__(self,tx):self.tx=tx
    async def __aenter__(self):self.tx.__enter__();return self
    async def __aexit__(self,*exc):self.tx.__exit__(*exc)

@pytest.fixture
def env(tmp_path):
    from datetime import datetime
    engine=create_engine('sqlite:///'+str(tmp_path/'test.db'))
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    class Clock:
        now=datetime(2026,10,16,12,0)
        def __call__(self):return self.now
    clock=Clock()
    game=Game(lambda:AsyncSessionShim(factory),randbelow=lambda n:0,clock=clock)
    yield game,clock,factory
    engine.dispose()
