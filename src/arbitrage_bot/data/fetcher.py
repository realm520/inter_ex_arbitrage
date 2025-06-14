import asyncio
import ccxt.pro
from loguru import logger
from typing import Dict, List, Any, Callable, Optional
from collections import defaultdict
import time

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
        
        # Event-driven architecture
        self._scan_callback: Optional[Callable[[str], Any]] = None
        self._last_scan_time = 0
        # Get scan cooldown from config (convert ms to seconds)
        from arbitrage_bot.config.settings import config
        cooldown_ms = config.arbitrage.get('scan_cooldown_ms', 500)
        self._scan_cooldown = cooldown_ms / 1000.0  # Convert to seconds
        self._pending_symbols = set()  # Symbols that need scanning
        
        # Heartbeat and activity tracking
        self._last_heartbeat = 0
        self._heartbeat_interval = 30  # seconds
        self._update_counts = defaultdict(int)  # Track updates per symbol
        self._level1_change_counts = defaultdict(int)  # Track Level 1 changes per symbol

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

    def register_scan_callback(self, callback: Callable[[str], Any]):
        """
        Register a callback function that will be called when order book changes
        should trigger a scan for the given symbol.
        """
        self._scan_callback = callback
        logger.info("Registered scan callback for event-driven arbitrage scanning")

    def _has_level1_changed(self, old_book: Dict[str, Any], new_book: Dict[str, Any]) -> bool:
        """
        Check if Level 1 data (best bid/ask) has changed significantly.
        """
        if not old_book or not new_book:
            return True  # First update or missing data
            
        # Check if best bid or ask has changed
        old_best_bid = old_book.get('bids', [[None]])[0][0] if old_book.get('bids') else None
        new_best_bid = new_book.get('bids', [[None]])[0][0] if new_book.get('bids') else None
        
        old_best_ask = old_book.get('asks', [[None]])[0][0] if old_book.get('asks') else None
        new_best_ask = new_book.get('asks', [[None]])[0][0] if new_book.get('asks') else None
        
        return (old_best_bid != new_best_bid) or (old_best_ask != new_best_ask)

    async def _trigger_scan_if_needed(self, symbol: str):
        """
        Trigger scan callback if conditions are met and cooldown has passed.
        """
        if not self._scan_callback:
            return
            
        current_time = time.time()
        
        # Add symbol to pending list
        self._pending_symbols.add(symbol)
        
        # Check cooldown
        if current_time - self._last_scan_time < self._scan_cooldown:
            return  # Wait for cooldown
            
        # Trigger scan for all pending symbols
        if self._pending_symbols:
            pending_count = len(self._pending_symbols)
            logger.trace(f"Triggering scan for {pending_count} symbols: {self._pending_symbols}")
            
            # Call the scan callback (non-blocking)
            try:
                # Create a task to run the callback without blocking WebSocket updates
                asyncio.create_task(self._run_scan_callback())
                self._last_scan_time = current_time
                self._pending_symbols.clear()
                logger.trace(f"Scan task created successfully")
            except Exception as e:
                logger.error(f"Error triggering scan callback: {e}")
                
    async def _run_scan_callback(self):
        """
        Run the scan callback in a separate task to avoid blocking WebSocket updates.
        """
        try:
            if self._scan_callback:
                await self._scan_callback()
        except Exception as e:
            logger.error(f"Error in scan callback: {e}")

    def _log_heartbeat(self):
        """
        Log periodic heartbeat to show the system is alive and working.
        """
        current_time = time.time()
        if current_time - self._last_heartbeat >= self._heartbeat_interval:
            total_updates = sum(self._update_counts.values())
            total_level1_changes = sum(self._level1_change_counts.values())
            
            logger.info(f"[HEARTBEAT] WebSocket active - "
                       f"Total updates: {total_updates}, "
                       f"Level 1 changes: {total_level1_changes}, "
                       f"Monitoring {len(self.active_symbols)} exchanges")
            
            # Log detailed stats if there's activity
            if total_updates > 0:
                logger.debug(f"[ACTIVITY] Update stats: {dict(self._update_counts)}")
                logger.debug(f"[ACTIVITY] Level 1 change stats: {dict(self._level1_change_counts)}")
            
            self._last_heartbeat = current_time

    async def _watch_order_book(self, exchange_name: str, symbol: str):
        exchange = self.exchange_manager.exchanges[exchange_name]
        logger.info(f"Subscribing to order book for {symbol} on {exchange_name}")
        
        component_id = f"{exchange_name}_{symbol}_orderbook"

        while self._is_monitoring:
            if self.error_handler.is_circuit_open(component_id):
                await asyncio.sleep(10) # Wait longer if circuit is open
                continue

            try:
                # Store old order book for comparison
                old_order_book = self._order_books[exchange_name].get(symbol)
                
                # Get new order book
                new_order_book = await exchange.watch_order_book(symbol)
                
                # Check if Level 1 data has changed
                level1_changed = self._has_level1_changed(old_order_book, new_order_book)
                
                # Update stored order book
                self._order_books[exchange_name][symbol] = new_order_book
                
                # Track activity stats
                symbol_key = f"{exchange_name}:{symbol}"
                self._update_counts[symbol_key] += 1
                
                if level1_changed:
                    self._level1_change_counts[symbol_key] += 1
                    logger.trace(f"Level 1 change detected for {symbol} on {exchange_name}")
                    # Trigger scan asynchronously
                    await self._trigger_scan_if_needed(symbol)
                else:
                    logger.trace(f"Order book update (no Level 1 change) for {symbol} on {exchange_name}")
                
                # Log periodic heartbeat
                self._log_heartbeat()
                
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
        total_streams = 0
        for exchange_name, symbols in self.active_symbols.items():
            for symbol in symbols:
                tasks.append(self._watch_order_book(exchange_name, symbol))
                total_streams += 1
        
        self._monitoring_task = asyncio.gather(*tasks)
        logger.info(f"Started data fetcher monitoring for {total_streams} WebSocket streams across {len(self.active_symbols)} exchanges")
        logger.info(f"Heartbeat interval: {self._heartbeat_interval}s, Scan cooldown: {self._scan_cooldown}s")

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