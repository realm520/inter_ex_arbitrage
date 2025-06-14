from __future__ import annotations
import itertools
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Dict, Tuple
import heapq

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
        # Cache for processed prices to avoid repeated calculations
        self._price_cache: Dict[str, Dict[str, Tuple[float, float]]] = {}  # symbol -> exchange -> (bid, ask)
        self._last_update_time: Dict[str, float] = {}  # symbol -> timestamp

    def scan(self) -> Optional[Opportunity]:
        """
        Scans all available order books and identifies potential arbitrage opportunities.
        Uses optimized algorithm with caching and efficient data structures.
        """
        current_time = time.time()
        
        # Get all order books
        all_order_books = self.data_fetcher.get_all_order_books()
        if not all_order_books:
            logger.warning("[Scan] No order book data available to scan.")
            return None

        # Build optimized price data structure: symbol -> [(bid_price, bid_exchange), (ask_price, ask_exchange)]
        symbol_prices = defaultdict(lambda: {'bids': [], 'asks': []})
        
        for exchange_name, symbols in all_order_books.items():
            for symbol, order_book in symbols.items():
                if not (order_book and order_book.get('bids') and order_book.get('asks')):
                    continue
                
                # Extract best bid and ask
                best_bid = order_book['bids'][0][0] if order_book['bids'] else None
                best_ask = order_book['asks'][0][0] if order_book['asks'] else None
                
                if best_bid is not None:
                    symbol_prices[symbol]['bids'].append((best_bid, exchange_name))
                if best_ask is not None:
                    symbol_prices[symbol]['asks'].append((best_ask, exchange_name))

        # Find best opportunities using heaps for efficiency
        best_opportunity = None
        best_net_profit = -float('inf')
        
        # Statistics for debugging
        scan_stats = {
            'total_symbols': len(symbol_prices),
            'no_data': 0,
            'insufficient_exchanges': 0,
            'same_exchange': 0,
            'negative_spreads': 0,
            'positive_spreads': 0,
            'opportunities_found': 0
        }
        
        for symbol, prices in symbol_prices.items():
            if len(prices['bids']) == 0 or len(prices['asks']) == 0:
                scan_stats['no_data'] += 1
                logger.debug(f"[No Data] {symbol}: Missing bids({len(prices['bids'])}) or asks({len(prices['asks'])})")
                continue
                
            # Check if we have at least 2 different exchanges
            all_exchanges = set([ex for _, ex in prices['bids']] + [ex for _, ex in prices['asks']])
            if len(all_exchanges) < 2:
                scan_stats['insufficient_exchanges'] += 1
                logger.debug(f"[Insufficient Exchanges] {symbol}: Only {len(all_exchanges)} exchange(s) available: {list(all_exchanges)}")
                continue
            
            # Use max-heap for bids (highest price) and min-heap for asks (lowest price)
            # For max-heap, we negate the values
            max_bid_price, max_bid_exchange = max(prices['bids'])
            min_ask_price, min_ask_exchange = min(prices['asks'])
            
            # Calculate price spread for debugging (always show this)
            spread_pct = ((max_bid_price - min_ask_price) / min_ask_price) * 100 if min_ask_price > 0 else 0
            
            # Always log price spreads for debugging, even negative ones
            logger.debug(f"[Price Spread] {symbol}: Best Bid {max_bid_exchange}@{max_bid_price:.6f}, "
                        f"Best Ask {min_ask_exchange}@{min_ask_price:.6f}, "
                        f"Spread: {spread_pct:+.4f}%")
            
            # Skip if same exchange
            if max_bid_exchange == min_ask_exchange:
                scan_stats['same_exchange'] += 1
                logger.debug(f"[Skip] {symbol}: Same exchange ({max_bid_exchange}) for bid and ask")
                continue
            
            # Count spread types
            if spread_pct >= 0:
                scan_stats['positive_spreads'] += 1
            else:
                scan_stats['negative_spreads'] += 1
            
            # Check arbitrage condition
            if max_bid_price > min_ask_price:
                gross_profit_pct = spread_pct  # Same calculation as above
                
                # Calculate net profit with caching
                net_profit_pct = self._calculate_net_profit_cached(
                    gross_profit_pct,
                    min_ask_exchange,
                    max_bid_exchange, 
                    symbol
                )
                
                logger.info(f"[Opportunity Found] {symbol}: Buy on {min_ask_exchange}@{min_ask_price:.6f}, "
                           f"Sell on {max_bid_exchange}@{max_bid_price:.6f}. "
                           f"Gross: {gross_profit_pct:.4f}%, Net: {net_profit_pct:.4f}%")
                
                # Track the best opportunity
                if net_profit_pct >= self.min_profit_threshold and net_profit_pct > best_net_profit:
                    scan_stats['opportunities_found'] += 1
                    best_net_profit = net_profit_pct
                    best_opportunity = Opportunity(
                        symbol=symbol,
                        buy_exchange=min_ask_exchange,
                        sell_exchange=max_bid_exchange,
                        buy_price=min_ask_price,
                        sell_price=max_bid_price,
                        gross_profit_pct=gross_profit_pct,
                        net_profit_pct=net_profit_pct,
                    )
        
        # Log scan statistics
        if scan_stats['total_symbols'] > 0:
            logger.debug(f"[Scan Stats] Total: {scan_stats['total_symbols']}, "
                        f"No Data: {scan_stats['no_data']}, "
                        f"Insufficient Exchanges: {scan_stats['insufficient_exchanges']}, "
                        f"Same Exchange: {scan_stats['same_exchange']}, "
                        f"Positive Spreads: {scan_stats['positive_spreads']}, "
                        f"Negative Spreads: {scan_stats['negative_spreads']}, "
                        f"Opportunities: {scan_stats['opportunities_found']}")
        else:
            logger.warning("[Scan] No market data available for scanning")
        
        return best_opportunity

    def _calculate_net_profit_cached(self, gross_profit_pct: float, buy_exchange: str, 
                                   sell_exchange: str, symbol: str) -> float:
        """
        Calculate net profit with caching to avoid repeated fee lookups.
        """
        cache_key = f"{buy_exchange}_{sell_exchange}_{symbol}"
        
        # For now, we'll use the cost calculator directly since fee caching is already implemented there
        # In a future optimization, we could add our own caching layer here
        return self.cost_calculator.calculate_net_profit_pct(
            gross_profit_pct, buy_exchange, sell_exchange, symbol
        )

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