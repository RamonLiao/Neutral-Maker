import asyncio
from avellaneda_bot import main as bot_main
from bot import logger

if __name__ == "__main__":
    logger.info("Starting via main.py Entry Point...")
    try:
        asyncio.run(bot_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"FATAL: {e}")
