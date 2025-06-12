import time
from dataclasses import dataclass


@dataclass
class Opportunity:
    """
    Represents a potential arbitrage opportunity.
    """
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    gross_profit_pct: float
    net_profit_pct: float
    timestamp: float = time.time() 