import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from loguru import logger

from arbitrage_bot.exchange.manager import ExchangeManager
from arbitrage_bot.arbitrage.scanner import ArbitrageOpportunity
from arbitrage_bot.config.settings import config
from arbitrage_bot.execution.order_manager import OrderManager
from arbitrage_bot.models.order import Order

@dataclass
class ExecutedTrade:
    """
    Represents a completed arbitrage trade, including details from both legs.
    """
    opportunity: ArbitrageOpportunity
    buy_order_id: str
    sell_order_id: str
    status: str  # e.g., 'completed', 'failed', 'partial'
    timestamp: float = time.time()

class TradeExecutor:
    """
    Handles the execution of arbitrage opportunities by placing orders
    on the respective exchanges.
    """

    def __init__(self, exchange_manager: ExchangeManager, order_manager: OrderManager, paper_mode: bool = False):
        self.exchange_manager = exchange_manager
        self.order_manager = order_manager
        self.paper_mode = paper_mode
        self.max_trade_size_usd = config.arbitrage.get('max_trade_size', 100.0)

    async def execute_opportunity(self, opportunity: ArbitrageOpportunity) -> Optional[Tuple[dict, dict]]:
        """
        Executes a buy and a sell order based on the provided arbitrage opportunity.
        """
        logger.info(f"Attempting to execute arbitrage opportunity: {opportunity.symbol}")
        logger.info(f" -> BUY on {opportunity.buy_exchange} at ~{opportunity.buy_price}")
        logger.info(f" -> SELL on {opportunity.sell_exchange} at ~{opportunity.sell_price}")

        buy_exchange = self.exchange_manager.get_exchange(opportunity.buy_exchange)
        sell_exchange = self.exchange_manager.get_exchange(opportunity.sell_exchange)

        if not buy_exchange or not sell_exchange:
            logger.error("Could not get exchange instances for trade execution.")
            return None

        try:
            if self.paper_mode:
                logger.info("[PAPER MODE] Skipping real order execution.")
                logger.info(f"[PAPER] Would place BUY order: {opportunity.volume} {opportunity.base_currency} on {opportunity.buy_exchange} at ~{opportunity.buy_price}")
                logger.info(f"[PAPER] Would place SELL order: {opportunity.volume} {opportunity.base_currency} on {opportunity.sell_exchange} at ~{opportunity.sell_price}")
                # Simulate order creation for tracking
                mock_buy_order = self._create_mock_order(opportunity, 'buy', opportunity.volume)
                mock_sell_order = self._create_mock_order(opportunity, 'sell', opportunity.volume)
                self.order_manager.add_order(mock_buy_order)
                self.order_manager.add_order(mock_sell_order)
                return

            # --- Real Order Execution ---
            logger.info(f"Placing BUY order: {opportunity.volume} {opportunity.base_currency} on {opportunity.buy_exchange}")
            buy_order = await buy_exchange.create_limit_buy_order(
                opportunity.symbol, 'limit', 'buy', opportunity.volume, opportunity.buy_price)
            self.order_manager.add_order(buy_order)
            logger.success(f"Successfully placed BUY order on {opportunity.buy_exchange}. Order ID: {buy_order['id']}")

            logger.info(f"Placing SELL order: {opportunity.volume} {opportunity.base_currency} on {opportunity.sell_exchange}")
            sell_order = await sell_exchange.create_limit_sell_order(
                opportunity.symbol, 'limit', 'sell', opportunity.volume, opportunity.sell_price)
            self.order_manager.add_order(sell_order)
            logger.success(f"Successfully placed SELL order on {opportunity.sell_exchange}. Order ID: {sell_order['id']}")

            if buy_order and sell_order:
                return buy_order, sell_order
            
            # TODO: Add logic to handle partial execution (e.g., cancel the successful order)
            if buy_order and not sell_order:
                logger.warning(f"Only BUY order was successful. Manual intervention may be required for order {buy_order['id']}.")
            
            if sell_order and not buy_order:
                logger.warning(f"Only SELL order was successful. Manual intervention may be required for order {sell_order['id']}.")

            return None
        except Exception as e:
            logger.error(f"Error executing trade for {opportunity.symbol}: {e}")
            # TODO: Implement more sophisticated error handling, e.g., cancel filled orders
            
    def _create_mock_order(self, opportunity: ArbitrageOpportunity, side: str, amount: float) -> Order:
        """Creates a mock order for paper trading."""
        return Order(
            id=f"paper-{side}-{int(time.time() * 1000)}",
            symbol=opportunity.symbol,
            exchange=opportunity.buy_exchange if side == 'buy' else opportunity.sell_exchange,
            side=side,
            type='limit',
            price=opportunity.buy_price if side == 'buy' else opportunity.sell_price,
            amount=amount,
            status='closed', # Assume filled instantly for paper trading
            timestamp=int(time.time() * 1000)
        )

    async def place_order(self, exchange, symbol: str, order_type: str, side: str, amount: float, price: float) -> dict:
        """A wrapper for placing an order with error handling."""
        try:
            # Note: ccxt unified method is create_limit_buy_order, etc.
            # but create_order is the most general.
            order = await exchange.create_order(symbol, order_type, side, amount, price)
            return order
        except Exception as e:
            logger.error(f"Failed to place {side} order on {exchange.id} for {symbol}: {e}")
            raise 