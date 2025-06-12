import asyncio
from loguru import logger
from typing import Optional, Self

from arbitrage_bot.config.settings import config
from arbitrage_bot.exchange.manager import ExchangeManager
from arbitrage_bot.data.fetcher import DataFetcher
from arbitrage_bot.arbitrage.scanner import ArbitrageScanner
from arbitrage_bot.execution.executor import TradeExecutor
from arbitrage_bot.execution.order_manager import OrderManager
from arbitrage_bot.risk_management.manager import RiskManager
from arbitrage_bot.utils.error_handler import ErrorHandler

class ArbitrageBot:
    """
    The main class for the arbitrage bot.

    This class initializes all necessary components, including the exchange
    manager, data fetcher, arbitrage scanner, and trade executor. It contains
    the main application logic to run the bot and orchestrates the graceful
    shutdown of all components.
    """
    def __init__(self, paper_mode: bool = False):
        """
        Initializes the ArbitrageBot.

        Args:
            paper_mode (bool): If True, the bot will run in paper trading mode,
                               and no real orders will be executed.
        """
        self.paper_mode = paper_mode
        self.running = False
        self._main_task: Optional[asyncio.Task] = None

    @classmethod
    async def create(cls, paper_mode: bool = False) -> Self:
        """
        Asynchronously creates and initializes the ArbitrageBot.
        This is the correct way to instantiate the bot.
        """
        bot = cls(paper_mode)
        
        bot.config = config
        bot.error_handler = ErrorHandler()
        
        # Initialize and connect exchanges BEFORE creating dependent components
        bot.exchange_manager = ExchangeManager(bot.config, bot.error_handler)
        await bot.exchange_manager.initialize_exchanges()

        # Now, create components with a fully initialized exchange_manager
        bot.order_manager = OrderManager(bot.exchange_manager)
        bot.risk_manager = RiskManager(bot.order_manager)
        bot.data_fetcher = DataFetcher(bot.exchange_manager, bot.error_handler)
        bot.arbitrage_scanner = ArbitrageScanner(bot.data_fetcher, bot.exchange_manager)
        bot.trade_executor = TradeExecutor(bot.exchange_manager, bot.order_manager, paper_mode=paper_mode)
        
        return bot

    async def run(self):
        """
        Starts the main bot loop. Assumes all components are initialized.
        """
        if len(self.exchange_manager.exchanges) < 2:
            logger.error("Arbitrage requires at least two connected exchanges. Exiting.")
            return

        self.running = True
        logger.info("=" * 50)
        logger.info("--- PAPER TRADING MODE ---" if self.paper_mode else "--- LIVE TRADING MODE ---")
        if not self.paper_mode:
            logger.warning("Bot will execute live trades on your accounts.")
        logger.info("=" * 50)

        self.data_fetcher.start_monitoring()
        
        logger.info("Waiting 10s for initial market data to populate...")
        await asyncio.sleep(10)

        logger.info("Starting arbitrage scanner...")
        while self.running:
            try:
                # --- New Emergency Stop Check ---
                if self.risk_manager.check_emergency_stop():
                    logger.critical("EMERGENCY STOP CONDITION MET. INITIATING SHUTDOWN.")
                    await self.trade_executor.liquidate_all_positions()
                    await self.shutdown()
                    break # Exit the main loop

                best_opportunity = self.arbitrage_scanner.scan()

                if best_opportunity:
                    logger.success(
                        f"OPPORTUNITY: Net Profit {best_opportunity.net_profit_pct:.4f}% | "
                        f"Buy on {best_opportunity.buy_exchange}, Sell on {best_opportunity.sell_exchange}"
                    )

                    if self.risk_manager.is_trade_safe(best_opportunity) and not self.paper_mode:
                        await self.trade_executor.execute_opportunity(best_opportunity)
                        
                        # In a real scenario, PnL would be calculated based on trade execution results.
                        # Here, we simulate a loss to test the emergency stop functionality.
                        logger.warning("SIMULATION: Applying a -$120 PnL change to test emergency stop.")
                        self.risk_manager.update_pnl(-120.0)

                        await asyncio.sleep(10)  # Cooldown after a trade attempt
                
                await asyncio.sleep(self.config.arbitrage.get('scan_interval_s', 5))

            except asyncio.CancelledError:
                logger.info("Main loop received cancellation signal.")
                break
            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}")
                logger.exception(e)
                await asyncio.sleep(10)

        logger.info("Bot run loop finished.")

    async def shutdown(self):
        """
        Gracefully shuts down the bot and all its components.
        """
        if not self.running:
            return

        self.running = False
        logger.info("Cleaning up and shutting down...")

        if self._main_task:
            self._main_task.cancel()

        logger.debug("Calling data_fetcher.stop_monitoring()...")
        await self.data_fetcher.stop_monitoring()
        logger.debug("Finished data_fetcher.stop_monitoring().")
        
        logger.debug("Calling exchange_manager.close_all()...")
        await self.exchange_manager.close_all()
        logger.debug("Finished exchange_manager.close_all().")

        logger.info("Shutdown complete.") 