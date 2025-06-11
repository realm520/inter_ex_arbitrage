import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from arbitrage_bot.data.fetcher import DataFetcher
from arbitrage_bot.config.settings import config

@dataclass
class ArbitrageOpportunity:
    """
    Represents a potential arbitrage opportunity found by the scanner.
    """
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    potential_profit_pct: float
    timestamp: float = time.time()

class ArbitrageScanner:
    """
    Scans for arbitrage opportunities across multiple exchanges
    by analyzing the real-time order book data.
    """
    def __init__(self, data_fetcher: DataFetcher):
        self.data_fetcher = data_fetcher
        self.min_profit_threshold = config.arbitrage.get('min_profit_threshold', 0.1)

    def scan(self) -> List[ArbitrageOpportunity]:
        """
        Scans all available symbols and exchanges for arbitrage opportunities.
        
        An arbitrage opportunity exists if we can buy on one exchange (at the ask price)
        and simultaneously sell on another (at the bid price) for a profit.
        
        Returns:
            A list of ArbitrageOpportunity objects.
        """
        opportunities = []
        # Get a set of all unique symbols being monitored across all exchanges
        all_symbols = set()
        for exchange_data in self.data_fetcher.order_books.values():
            all_symbols.update(exchange_data.keys())

        for symbol in all_symbols:
            # Extract the best bid and ask for the current symbol from all exchanges
            # that have data for it.
            prices = self._get_best_prices_for_symbol(symbol)
            
            if len(prices) < 2:
                # We need at least two exchanges to find an opportunity
                continue

            # Find the tuple with the lowest ask price (our best buy option)
            buy_candidate = min(prices, key=lambda x: x[1])
            # Find the tuple with the highest bid price (our best sell option)
            sell_candidate = max(prices, key=lambda x: x[2])

            best_ask_exchange, best_ask_price, _ = buy_candidate
            best_bid_exchange, _, best_bid_price = sell_candidate

            if best_ask_exchange == best_bid_exchange:
                # Cannot arbitrage on the same exchange
                continue

            # The core arbitrage condition: can we sell higher than we buy?
            if best_bid_price > best_ask_price:
                profit_pct = ((best_bid_price - best_ask_price) / best_ask_price) * 100

                # --- Display all positive-spread calculations for debugging/visibility ---
                print(f"[Scan] {symbol}: Buy on {best_ask_exchange}@{best_ask_price}, Sell on {best_bid_exchange}@{best_bid_price}. Spread: {profit_pct:.4f}%")

                # Check if the potential profit meets our minimum threshold
                if profit_pct >= self.min_profit_threshold:
                    opportunity = ArbitrageOpportunity(
                        symbol=symbol,
                        buy_exchange=best_ask_exchange,
                        sell_exchange=best_bid_exchange,
                        buy_price=best_ask_price,
                        sell_price=best_bid_price,
                        potential_profit_pct=profit_pct,
                    )
                    opportunities.append(opportunity)
        
        return opportunities

    def _get_best_prices_for_symbol(self, symbol: str) -> List[Tuple[str, float, float]]:
        """
        Helper to get the best bid and ask for a symbol from all exchanges.
        Returns a list of tuples: [(exchange_name, ask_price, bid_price), ...].
        """
        prices = []
        for exchange_name, symbols_data in self.data_fetcher.order_books.items():
            order_book = symbols_data.get(symbol)
            if order_book and order_book['asks'] and order_book['bids']:
                best_ask = order_book['asks'][0][0]
                best_bid = order_book['bids'][0][0]
                prices.append((exchange_name, best_ask, best_bid))
        return prices 