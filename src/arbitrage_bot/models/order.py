from enum import Enum
from dataclasses import dataclass, field
import time

class OrderStatus(Enum):
    OPEN = 'open'
    CLOSED = 'closed'
    CANCELED = 'canceled'
    FILLED = 'filled' # Custom status for fully filled
    PARTIALLY_FILLED = 'partially_filled' # Custom for partially filled but still open

@dataclass
class Order:
    id: str
    exchange: str
    symbol: str
    side: str
    type: str
    amount: float
    price: float
    status: OrderStatus
    timestamp: float = field(default_factory=time.time)
    cost: float = 0.0
    filled: float = 0.0
    fee: dict = field(default_factory=dict)

    @classmethod
    def from_ccxt_order(cls, ccxt_order: dict) -> 'Order':
        """Creates an Order object from a ccxt order dictionary."""
        
        # Normalize status
        status_str = ccxt_order.get('status')
        if status_str == 'closed' and ccxt_order.get('filled', 0.0) == ccxt_order.get('amount', -1.0):
            status = OrderStatus.FILLED
        elif status_str == 'open' and ccxt_order.get('filled', 0.0) > 0:
            status = OrderStatus.PARTIALLY_FILLED
        elif status_str:
            try:
                status = OrderStatus(status_str)
            except ValueError:
                status = OrderStatus.OPEN # Default for unknown statuses
        else:
            status = OrderStatus.OPEN

        return cls(
            id=ccxt_order['id'],
            exchange=ccxt_order['exchange'],
            symbol=ccxt_order['symbol'],
            side=ccxt_order['side'],
            type=ccxt_order['type'],
            amount=ccxt_order.get('amount'),
            price=ccxt_order.get('price') or ccxt_order.get('average'),
            status=status,
            timestamp=ccxt_order.get('timestamp') / 1000 if ccxt_order.get('timestamp') else time.time(), # ms to s
            cost=ccxt_order.get('cost', 0.0),
            filled=ccxt_order.get('filled', 0.0),
            fee=ccxt_order.get('fee')
        ) 