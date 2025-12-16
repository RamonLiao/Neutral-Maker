import asyncio
import sys
import os

from app.avellaneda_bot import main as bot_main
from app.bot import logger

if __name__ == "__main__":
    logger.info("Starting via Root main.py...")
    try:
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"FATAL: {e}")
