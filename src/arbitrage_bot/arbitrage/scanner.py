from __future__ import annotations
import itertools
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

from loguru import logger

from arbitrage_bot.config.settings import config
from arbitrage_bot.arbitrage.costs import CostCalculator
from arbitrage_bot.model import Opportunity

if TYPE_CHECKING:
    from arbitrage_bot.data.fetcher import DataFetcher
    from arbitrage_bot.exchange.manager import ExchangeManager

class ArbitrageScanner:
    """
    Scans for arbitrage opportunities across multiple exchanges
    by analyzing the real-time order book data.
    """
    def __init__(self, data_fetcher: DataFetcher, exchange_manager: ExchangeManager):
        self.data_fetcher = data_fetcher
        arbitrage_config = config.get("arbitrage", {})
        self.min_profit_threshold = arbitrage_config.get('min_profit_threshold', 0.1)
        # Initialize the cost calculator
        self.cost_calculator = CostCalculator(exchange_manager)

    def scan(self) -> Optional[Opportunity]:
        """
        Scans all available order books and identifies potential arbitrage opportunities.
        """
        opportunities = []
        
        # 1. Group order books by symbol
        order_books_by_symbol = defaultdict(dict)
        all_order_books = self.data_fetcher.get_all_order_books()
        if not all_order_books:
            logger.warning("[Scan] No order book data available to scan.")
            return None

        for exchange_name, symbols in all_order_books.items():
            for symbol, order_book in symbols.items():
                if order_book and order_book.get('bids') and order_book.get('asks'):
                     order_books_by_symbol[symbol][exchange_name] = order_book

        # 2. Iterate through each symbol and compare exchanges
        for symbol, exchanges in order_books_by_symbol.items():
            if len(exchanges) < 2:
                continue  # Need at least two exchanges to find an opportunity

            # Find the best ask (lowest price to buy) and best bid (highest price to sell) across all exchanges for this symbol
            prices = self._get_best_prices_for_symbol(exchanges)
            if not prices['bids'] or not prices['asks']:
                continue

            best_bid_exchange, best_bid = max(prices['bids'].items(), key=lambda item: item[1])
            best_ask_exchange, best_ask = min(prices['asks'].items(), key=lambda item: item[1])

            if not all([best_bid_exchange, best_bid, best_ask_exchange, best_ask]):
                continue

            if best_ask_exchange == best_bid_exchange:
                # Cannot arbitrage on the same exchange
                continue

            # The core arbitrage condition: can we sell higher than we buy?
            if best_bid > best_ask:
                gross_profit_pct = ((best_bid - best_ask) / best_ask) * 100

                # --- NEW: Calculate Net Profit ---
                net_profit_pct = self.cost_calculator.calculate_net_profit_pct(
                    gross_profit_pct,
                    buy_exchange=best_ask_exchange,
                    sell_exchange=best_bid_exchange,
                    symbol=symbol
                )

                # --- Display all positive-spread calculations for debugging/visibility ---
                logger.trace(f"[Scan] {symbol}: Buy on {best_ask_exchange}@{best_ask}, Sell on {best_bid_exchange}@{best_bid}. Gross: {gross_profit_pct:.4f}%, Net: {net_profit_pct:.4f}%")

                if net_profit_pct >= self.min_profit_threshold:
                    # For now, let's just return the best single opportunity
                    # In a real scenario, you might want to handle multiple opportunities
                    return Opportunity(
                        symbol=symbol,
                        buy_exchange=best_ask_exchange,
                        sell_exchange=best_bid_exchange,
                        buy_price=best_ask,
                        sell_price=best_bid,
                        gross_profit_pct=gross_profit_pct,
                        net_profit_pct=net_profit_pct,
                    )
        
        return None

    def _get_best_prices_for_symbol(self, symbol_order_books: dict) -> dict:
        """
        Retrieves the best bid and ask for a given symbol from pre-fetched order books.
        
        Args:
            symbol_order_books: A dictionary where keys are exchange names and values are order book data.
            
        Returns:
            A dictionary with 'bids' and 'asks'.
        """
        bids = {}
        asks = {}
        for exchange_name, order_book in symbol_order_books.items():
            if order_book.get('bids'):
                bids[exchange_name] = order_book['bids'][0][0]  # [price, amount]
            if order_book.get('asks'):
                asks[exchange_name] = order_book['asks'][0][0]
        return {'bids': bids, 'asks': asks} 