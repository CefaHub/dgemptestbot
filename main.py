"""Hosting-compatible launch wrapper; no secrets in source."""
import asyncio
from dolce_empire.bot import main

if __name__ == '__main__':
    asyncio.run(main())
