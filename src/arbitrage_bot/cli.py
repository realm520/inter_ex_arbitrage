import argparse
import asyncio
import signal
from loguru import logger

from arbitrage_bot.bot import ArbitrageBot
from arbitrage_bot.logging.setup import setup_logging


def main():
    """
    The main entry point for the CLI application.

    This function is called by the script defined in pyproject.toml.
    It parses command-line arguments and starts the arbitrage bot.
    """
    parser = argparse.ArgumentParser(description="Inter-Exchange Arbitrage Bot")
    parser.add_argument(
        "--paper",
        action="store_true",
        help="Run in paper trading mode (no real orders will be executed).",
    )
    args = parser.parse_args()

    # Setup logging first
    setup_logging()
    
    logger.info("Initializing arbitrage bot...")
    if args.paper:
        logger.info("Running in paper trading mode.")
    
    # Get the asyncio event loop
    loop = asyncio.get_event_loop()

    # The main async function that creates and runs the bot
    async def async_main():
        bot = await ArbitrageBot.create(paper_mode=args.paper)

        # --- Graceful Shutdown Logic ---
        shutdown_signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)

        async def shutdown(sig: signal.Signals):
            logger.warning(f"Received exit signal {sig.name}...")
            await bot.shutdown()
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("All tasks cancelled, stopping event loop.")
            loop.stop()

        for s in shutdown_signals:
            loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s)))
        # ---------------------------------

        await bot.run()

    # Run the main async function until it's stopped
    try:
        loop.create_task(async_main())
        loop.run_forever()
    finally:
        logger.info("Event loop stopped. Closing.")
        loop.close()


if __name__ == "__main__":
    main() 