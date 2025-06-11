import asyncio
from typing import Dict, List

from arbitrage_bot.exchange.manager import ExchangeManager

class DataFetcher:
    """
    Fetches and manages real-time market data (order books) from multiple exchanges
    using WebSocket streams provided by ccxt.pro.
    """

    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        # A nested dictionary to store order books: {exchange_name: {symbol: order_book}}
        self.order_books: Dict[str, Dict[str, Dict]] = {}
        self._monitoring_tasks: List[asyncio.Task] = []

    def start_monitoring(self):
        """
        Starts the monitoring tasks for all trading pairs specified in the config
        for all enabled and connected exchanges.
        """
        print("Starting data monitoring...")
        for exchange_name, exchange in self.exchange_manager.exchanges.items():
            # Get the trading pairs for the current exchange from the config
            trading_pairs = self.exchange_manager._config.exchanges[exchange_name].get('trading_pairs', [])
            
            for symbol in trading_pairs:
                if symbol in exchange.markets:
                    # Create a background task for each symbol on each exchange
                    task = asyncio.create_task(self._watch_order_book_loop(exchange_name, symbol))
                    self._monitoring_tasks.append(task)
                else:
                    print(f"Warning: Symbol {symbol} not found in {exchange_name}. Skipping.")
        
        if not self._monitoring_tasks:
            print("No monitoring tasks were started. Check your config for enabled exchanges and trading pairs.")

    async def _watch_order_book_loop(self, exchange_name: str, symbol: str):
        """
        The core loop that continuously watches the order book for a specific symbol on an exchange.
        This method is designed to run indefinitely as a background task.
        """
        exchange = self.exchange_manager.get_exchange(exchange_name)
        if not exchange:
            return

        print(f"Starting order book monitoring for {symbol} on {exchange_name}...")
        while True:
            try:
                # ccxt.pro's watch_order_book fetches the full order book on the first call,
                # and then receives incremental updates via WebSocket.
                order_book = await exchange.watch_order_book(symbol)
                
                # Store the latest order book data
                if exchange_name not in self.order_books:
                    self.order_books[exchange_name] = {}
                self.order_books[exchange_name][symbol] = order_book
                
                # Optional: Print a small part of the data to show it's working
                # best_bid = order_book['bids'][0][0] if order_book['bids'] else 'N/A'
                # best_ask = order_book['asks'][0][0] if order_book['asks'] else 'N/A'
                # print(f"[{exchange_name} - {symbol}] Best Bid: {best_bid}, Best Ask: {best_ask}")

            except Exception as e:
                print(f"Error watching order book for {symbol} on {exchange_name}: {e}")
                # In a real application, you'd want more robust reconnection logic.
                # For now, we'll wait and try again.
                await asyncio.sleep(5)

    def stop_monitoring(self):
        """
        Stops all background monitoring tasks.
        """
        print("Stopping all data monitoring tasks...")
        for task in self._monitoring_tasks:
            task.cancel()
        self._monitoring_tasks.clear()
        print("Monitoring stopped.")

    def get_order_book(self, exchange_name: str, symbol: str) -> Dict or None:
        """
        Retrieves the latest order book for a given exchange and symbol.
        """
        return self.order_books.get(exchange_name, {}).get(symbol) 