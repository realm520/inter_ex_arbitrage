import asyncio
import ccxt.pro
from loguru import logger
from typing import Dict, List, Any
from collections import defaultdict

from arbitrage_bot.exchange.manager import ExchangeManager
from arbitrage_bot.utils.error_handler import ErrorHandler

class DataFetcher:
    """
    Fetches and manages real-time market data (order books) from multiple exchanges
    using WebSocket streams provided by ccxt.pro.
    """

    def __init__(self, exchange_manager: ExchangeManager, error_handler: ErrorHandler):
        self.exchange_manager = exchange_manager
        self.error_handler = error_handler
        # A nested defaultdict to store order books: {exchange_name: {symbol: order_book}}
        # This prevents KeyErrors when accessing nested dictionaries for the first time.
        self._order_books: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.active_symbols = self._get_active_symbols()
        self._monitoring_task = None
        self._is_monitoring = False

    def _get_active_symbols(self) -> dict:
        """
        Gets a list of common symbols that are active on all enabled exchanges.
        """
        active_symbols = {}
        # The structure is now self.exchange_manager.config which holds the exchanges dict
        for exchange_name, settings in self.exchange_manager.config.items():
            if settings.get("enabled"):
                symbols = settings.get("symbols", [])
                active_symbols[exchange_name] = symbols
        return active_symbols

    async def _watch_order_book(self, exchange_name: str, symbol: str):
        exchange = self.exchange_manager.exchanges[exchange_name]
        logger.info(f"Subscribing to order book for {symbol} on {exchange_name}")
        
        component_id = f"{exchange_name}_{symbol}_orderbook"

        while self._is_monitoring:
            if self.error_handler.is_circuit_open(component_id):
                await asyncio.sleep(10) # Wait longer if circuit is open
                continue

            try:
                order_book = await exchange.watch_order_book(symbol)
                self._order_books[exchange_name][symbol] = order_book
                logger.trace(f"Received order book update for {symbol} on {exchange_name}")
                self.error_handler.reset_error(component_id) # Reset on success
            except Exception as e:
                logger.error(f"Error watching order book for {symbol} on {exchange_name}: {e}")
                self.error_handler.record_error(component_id)
                delay = await self.error_handler.get_backoff_delay(component_id)
                logger.info(f"Backing off for {delay:.2f}s before retrying {component_id}...")
                await asyncio.sleep(delay)

    def start_monitoring(self):
        if self._monitoring_task:
            logger.warning("Monitoring is already running.")
            return

        self._is_monitoring = True
        tasks = []
        for exchange_name, symbols in self.active_symbols.items():
            for symbol in symbols:
                tasks.append(self._watch_order_book(exchange_name, symbol))
        
        self._monitoring_task = asyncio.gather(*tasks)
        logger.info("Started data fetcher monitoring.")

    async def stop_monitoring(self):
        """Stops the monitoring task gracefully."""
        logger.debug("Attempting to stop monitoring...")
        if not self._is_monitoring or not self._monitoring_task:
            logger.debug("Monitoring was not active or task does not exist.")
            return
            
        self._is_monitoring = False
        
        if self._monitoring_task.done():
            logger.info("Monitoring task was already done.")
            return

        logger.debug(f"Cancelling monitoring task {id(self._monitoring_task)}...")
        self._monitoring_task.cancel()
        
        try:
            await self._monitoring_task
            logger.debug("Monitoring task awaited successfully after cancel.")
        except asyncio.CancelledError:
            logger.debug("Successfully caught expected CancelledError for monitoring task.")
        finally:
            self._monitoring_task = None
            logger.info("Stopped data fetcher monitoring.")

    def get_order_book(self, exchange_name: str, symbol: str) -> Dict[str, Any]:
        """Returns the latest order book for a specific exchange and symbol."""
        return self._order_books.get(exchange_name, {}).get(symbol)

    def get_all_order_books(self) -> Dict[str, Dict[str, Any]]:
        """Returns all currently stored order books."""
        return self._order_books 