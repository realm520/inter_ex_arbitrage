import asyncio
import time
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
        
        # Performance tracking
        self._scan_count = 0
        self._opportunity_count = 0
        self._start_time = None

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
        self._start_time = time.time()
        logger.info("=" * 50)
        logger.info("--- PAPER TRADING MODE ---" if self.paper_mode else "--- LIVE TRADING MODE ---")
        if not self.paper_mode:
            logger.warning("Bot will execute live trades on your accounts.")
        
        # Log configuration summary
        logger.info(f"Min profit threshold: {self.arbitrage_scanner.min_profit_threshold}%")
        logger.info(f"Max trade size: ${self.trade_executor.max_trade_size_usd}")
        logger.info(f"Emergency stop loss: ${self.risk_manager.emergency_stop_loss_usd}")
        logger.info(f"Max open trades: {self.risk_manager.max_open_trades}")
        
        # Log monitored trading pairs
        total_pairs = 0
        for exchange_name, symbols in self.data_fetcher.active_symbols.items():
            logger.info(f"{exchange_name}: {len(symbols)} pairs - {', '.join(symbols)}")
            total_pairs += len(symbols)
        
        logger.info(f"Total monitoring: {total_pairs} trading pairs across {len(self.exchange_manager.exchanges)} exchanges")
        logger.info("=" * 50)

        # Register event-driven scan callback
        self.data_fetcher.register_scan_callback(self._on_market_data_change)
        
        self.data_fetcher.start_monitoring()
        
        logger.info("Waiting 10s for initial market data to populate...")
        await asyncio.sleep(10)

        logger.info("Starting event-driven arbitrage monitoring...")
        logger.info("Scanner will now trigger automatically on Level 1 price changes")
        
        # Keep the bot running and handle emergency stops
        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                
                # --- Emergency Stop Check (every 30 seconds) ---
                if self.risk_manager.check_emergency_stop():
                    logger.critical("EMERGENCY STOP CONDITION MET. INITIATING SHUTDOWN.")
                    await self.trade_executor.liquidate_all_positions()
                    await self.shutdown()
                    break # Exit the main loop

                # Log periodic status every few loops
                if loop_count % 10 == 1:  # Every 5 minutes (30s * 10)
                    current_pnl = self.risk_manager.pnl
                    open_orders = self.order_manager.get_open_order_count()
                    uptime = time.time() - self._start_time if self._start_time else 0
                    scan_rate = self._scan_count / (uptime / 60) if uptime > 0 else 0  # scans per minute
                    
                    logger.info(f"[STATUS] Bot running normally - "
                               f"Uptime: {uptime/60:.1f}min, "
                               f"Scans: {self._scan_count} ({scan_rate:.1f}/min), "
                               f"Opportunities: {self._opportunity_count}, "
                               f"PnL: ${current_pnl:.2f}, "
                               f"Open orders: {open_orders}, "
                               f"Paper mode: {self.paper_mode}")

                # Sleep longer since scanning is now event-driven
                await asyncio.sleep(30)  # Check emergency stop every 30 seconds

            except asyncio.CancelledError:
                logger.info("Main loop received cancellation signal.")
                break
            except Exception as e:
                logger.error(f"An error occurred in the main loop: {e}")
                logger.exception(e)
                await asyncio.sleep(10)

        logger.info("Bot run loop finished.")

    async def _on_market_data_change(self):
        """
        Event-driven callback triggered when Level 1 market data changes.
        This replaces the polling-based scan loop.
        """
        try:
            self._scan_count += 1
            logger.trace(f"Market data change detected, triggering scan #{self._scan_count}")
            
            best_opportunity = self.arbitrage_scanner.scan()

            if best_opportunity:
                self._opportunity_count += 1
                logger.success(
                    f"OPPORTUNITY #{self._opportunity_count}: Net Profit {best_opportunity.net_profit_pct:.4f}% | "
                    f"Buy on {best_opportunity.buy_exchange}, Sell on {best_opportunity.sell_exchange}"
                )

                if self.risk_manager.is_trade_safe(best_opportunity):
                    if not self.paper_mode:
                        execution_result = await self.trade_executor.execute_opportunity(best_opportunity)
                        
                        # Update PnL based on actual trade execution results
                        if execution_result and execution_result.get('success'):
                            buy_order = execution_result.get('buy_order')
                            sell_order = execution_result.get('sell_order')
                            if buy_order and sell_order:
                                self.risk_manager.update_pnl_from_orders(buy_order, sell_order)
                    else:
                        logger.info(f"[PAPER MODE] Would execute opportunity: {best_opportunity.symbol}")
                
        except Exception as e:
            logger.error(f"Error in market data change callback: {e}")
            logger.exception(e)

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