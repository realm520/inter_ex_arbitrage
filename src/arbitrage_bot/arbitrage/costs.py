from __future__ import annotations
from typing import TYPE_CHECKING, Dict

from arbitrage_bot.config.settings import config

if TYPE_CHECKING:
    from arbitrage_bot.exchange.manager import ExchangeManager


class CostCalculator:
    """
    Calculates the costs associated with an arbitrage trade,
    primarily focusing on trading fees.
    """
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        fees_config = config.get("fees", {})
        self.default_fee_pct = fees_config.get('default_taker_fee_pct', 0.1)
        # Cache to store fee information for each exchange to avoid repeated lookups
        self.fee_cache: Dict[str, float] = {}

    def get_trading_fee_pct(self, exchange_name: str, symbol: str) -> float:
        """
        Gets the trading fee for a given exchange.
        
        For simplicity, we assume 'taker' fees as arbitrage orders are often
        market orders to ensure immediate execution. We also assume the fee
        is the same for all symbols on an exchange.
        
        Args:
            exchange_name: The name of the exchange.
            symbol: The trading symbol (may be used in more advanced fee models).

        Returns:
            The taker fee as a percentage (e.g., 0.1 for 0.1%).
        """
        if exchange_name in self.fee_cache:
            return self.fee_cache[exchange_name]

        exchange = self.exchange_manager.get_exchange(exchange_name)
        if not exchange or not exchange.markets:
            # Fallback to a default fee if exchange data is not available
            return self.default_fee_pct

        # Find the market for the symbol to get fee info
        market = exchange.markets.get(symbol)
        if market and market.get('taker') is not None:
            # CCXT provides fees as a fraction (e.g., 0.001), so we convert to percent
            fee = market['taker'] * 100
        else:
            # Fallback for exchanges that don't specify per-market fees
            fee = exchange.fees['trading']['taker'] * 100 if 'trading' in exchange.fees else self.default_fee_pct
        
        self.fee_cache[exchange_name] = fee
        return fee

    def calculate_net_profit_pct(self, gross_profit_pct: float, buy_exchange: str, sell_exchange: str, symbol: str) -> float:
        """
        Calculates the net profit after deducting trading fees from both exchanges.

        Args:
            gross_profit_pct: The potential profit before any fees.
            buy_exchange: The name of the exchange to buy from.
            sell_exchange: The name of the exchange to sell on.
            symbol: The trading symbol.

        Returns:
            The net profit as a percentage. Can be negative if fees exceed profit.
        """
        # Get the taker fee for the buy and sell exchanges
        buy_fee = self.get_trading_fee_pct(buy_exchange, symbol)
        sell_fee = self.get_trading_fee_pct(sell_exchange, symbol)
        
        total_fees = buy_fee + sell_fee
        
        net_profit_pct = gross_profit_pct - total_fees
        
        return net_profit_pct 