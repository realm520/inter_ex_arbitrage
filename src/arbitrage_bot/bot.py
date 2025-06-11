import asyncio
from loguru import logger
from typing import Optional

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
        self.config = config
        self.error_handler = ErrorHandler()

        self.exchange_manager = ExchangeManager(self.config, self.error_handler)

        self.order_manager = OrderManager(self.exchange_manager)
        self.risk_manager = RiskManager(self.order_manager)
        self.data_fetcher = DataFetcher(self.exchange_manager, self.error_handler)
        self.arbitrage_scanner = ArbitrageScanner(self.data_fetcher)
        self.trade_executor = TradeExecutor(self.exchange_manager, self.order_manager, paper_mode=paper_mode)
        
        self.running = False
        self._shutting_down = False
        self._main_task: Optional[asyncio.Task] = None

    async def run(self):
        """
        Starts the main bot loop.

        This method initializes connections, starts data monitoring, and continuously
        scans for arbitrage opportunities.
        """
        self.running = True
        
        logger.info("="*50)
        if not self.paper_mode:
            logger.warning("!!! REAL TRADING IS ENABLED !!!")
            logger.warning("Bot will execute live trades on your accounts.")
            logger.warning("Please wait 5 seconds to review your configuration or press Ctrl+C to cancel.")
            await asyncio.sleep(5)
        else:
            logger.info("--- PAPER TRADING MODE ---")
            logger.info("Bot will scan for opportunities but will NOT execute trades.")
        logger.info("="*50)

        logger.info("Initializing modules...")
        await self.exchange_manager.initialize_exchanges()
        
        if len(self.exchange_manager.exchanges) < 2:
            logger.error("Arbitrage requires at least two connected exchanges. Exiting.")
            await self.shutdown()
            return
            
        self.data_fetcher.start_monitoring()
        logger.info("Waiting for initial market data...")
        await asyncio.sleep(10) # Give more time for all websockets to connect
        logger.info("Starting arbitrage scanner...")

        while self.running:
            try:
                opportunities = self.arbitrage_scanner.scan()
                
                if opportunities:
                    best_opportunity = opportunities[0]
                    
                    logger.success(f"OPPORTUNITY: Net Profit {best_opportunity.net_profit_pct:.4f}% | Buy on {best_opportunity.buy_exchange}, Sell on {best_opportunity.sell_exchange}")

                    if self.risk_manager.is_trade_safe(best_opportunity) and not self.paper_mode:
                        await self.trade_executor.execute_opportunity(best_opportunity)
                        await asyncio.sleep(10) # Cooldown after a trade attempt
                
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Main loop received cancellation signal.")
                self.running = False
            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}", exc_info=True)
                await asyncio.sleep(10) # Wait longer after an error

        logger.info("Bot run loop finished.")

    async def shutdown(self):
        """
        Gracefully shuts down the bot and all its components.
        """
        if self._shutting_down:
            logger.debug("Shutdown already in progress.")
            return
            
        self._shutting_down = True
        self.running = False # Stop the main loop
        
        logger.info("Cleaning up and shutting down...")
        logger.debug("Calling data_fetcher.stop_monitoring()...")
        await self.data_fetcher.stop_monitoring()
        logger.debug("Finished data_fetcher.stop_monitoring().")
        
        logger.debug("Calling exchange_manager.close_all()...")
        await self.exchange_manager.close_all()
        logger.debug("Finished exchange_manager.close_all().")
        
        logger.info("Shutdown complete.") 