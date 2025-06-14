from typing import Dict, Optional
from loguru import logger
import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field

from arbitrage_bot.exchange.manager import ExchangeManager
from arbitrage_bot.models.order import Order, OrderStatus

class OrderStatus(Enum):
    """
    Represents the status of an order.
    """
    OPEN = 'open'
    PARTIALLY_FILLED = 'partially_filled'
    FILLED = 'filled'
    CANCELED = 'canceled'
    FAILED = 'failed'

@dataclass
class Order:
    """
    Represents a single order placed on an exchange.
    """
    id: str
    exchange_name: str
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.OPEN
    filled: float = 0.0
    average: Optional[float] = None
    timestamp: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)

class OrderManager:
    """
    Manages the lifecycle of orders, including creation, tracking, and cancellation.
    """
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        self.orders: Dict[str, Order] = {}

    async def update_order_status(self, order_id: str) -> Optional[Order]:
        """
        Fetches the latest status of a single order from the exchange
        and updates the local record.

        Args:
            order_id: The ID of the order to update.

        Returns:
            The updated Order object, or None if the order is not found or an error occurs.
        """
        order = self.orders.get(order_id)
        if not order:
            logger.error(f"Cannot update status for unknown order ID: {order_id}")
            return None
        
        exchange = self.exchange_manager.get_exchange(order.exchange_name)
        if not exchange:
            logger.error(f"Cannot get exchange instance '{order.exchange_name}' to update order {order_id}.")
            return None

        try:
            logger.debug(f"Fetching status for order {order_id} on {order.exchange_name}...")
            fetched_order_data = await exchange.fetch_order(order_id, order.symbol)
            updated_order = Order.from_ccxt_order(fetched_order_data)

            if order.status != updated_order.status:
                logger.success(f"Order {order_id} status changed: {order.status.value} -> {updated_order.status.value}")
                self.orders[order_id] = updated_order
            else:
                logger.info(f"Order {order_id} status remains '{order.status.value}'.")
            
            return self.orders[order_id]

        except Exception as e:
            logger.error(f"Failed to fetch status for order {order_id} on {order.exchange_name}: {e}")
            return None

    def add_order(self, order_data: dict):
        if order_data['id'] in self.orders:
            logger.warning(f"Order {order_data['id']} already being managed.")
            return
            
        order = Order.from_ccxt_order(order_data)
        self.orders[order.id] = order
        logger.info(f"Now managing order {order.id} on {order.exchange_name} ({order.status.value}).")

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)
    
    def get_open_order_count(self) -> int:
        """Returns the number of open (non-closed) orders."""
        open_count = 0
        for order in self.orders.values():
            if order.status not in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.FAILED]:
                open_count += 1
        return open_count
    
    def record_paper_trade(self, opportunity):
        """Records a paper trade for simulation purposes."""
        logger.info(f"[PAPER TRADE] Would execute {opportunity.symbol}: "
                   f"Buy {opportunity.volume} on {opportunity.buy_exchange} @ {opportunity.buy_price}, "
                   f"Sell {opportunity.volume} on {opportunity.sell_exchange} @ {opportunity.sell_price}")
    
    def update_order_status(self, order_id: str, status: str):
        """Updates an order's status manually."""
        if order_id in self.orders:
            old_status = self.orders[order_id].status
            self.orders[order_id].status = OrderStatus(status)
            logger.info(f"Order {order_id} status updated: {old_status.value} -> {status}")
        else:
            logger.warning(f"Cannot update status for unknown order ID: {order_id}") 