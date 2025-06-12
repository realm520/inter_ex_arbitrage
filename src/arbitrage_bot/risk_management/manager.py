from __future__ import annotations
from typing import TYPE_CHECKING
from loguru import logger

from arbitrage_bot.config.settings import config
from arbitrage_bot.model import Opportunity
from arbitrage_bot.execution.order_manager import OrderManager
from arbitrage_bot.models.order import Order
import json
from pathlib import Path
from typing import List

if TYPE_CHECKING:
    from arbitrage_bot.execution.order_manager import OrderManager

class RiskManager:
    """
    Manages overall portfolio risk and makes decisions on whether to execute trades.
    """
    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
        # TODO: Load these from config
        self.max_open_trades = 5
        self.emergency_stop_loss_usd = 100.0 # Emergency stop if total PnL drops below this (in USD)
        self.pnl = 0.0 # Placeholder for Profit and Loss tracking
        logger.info("Risk Manager initialized.")
        logger.info(f" - Max open trades: {self.max_open_trades}")
        logger.info(f" - Emergency stop-loss threshold: -${self.emergency_stop_loss_usd:.2f}")
        logger.info(f" - Initial PnL loaded: ${self.pnl:.2f}")

    def update_pnl(self, pnl_change: float):
        """Updates the portfolio's PnL. For simulation and future use."""
        self.pnl += pnl_change
        logger.info(f"PnL updated by ${pnl_change:.2f}. Current PnL: ${self.pnl:.2f}")

    def check_emergency_stop(self) -> bool:
        """Checks if the emergency stop-loss has been triggered."""
        if self.pnl < -self.emergency_stop_loss_usd:
             logger.critical(f"EMERGENCY STOP TRIGGERED: Portfolio PnL (${self.pnl:.2f}) has dropped below threshold (-${self.emergency_stop_loss_usd:.2f}).")
             return True
        return False

    def is_trade_safe(self, opportunity: Opportunity) -> bool:
        """
        Checks if a given trade opportunity is safe to execute based on current risk exposure.
        """
        # 1. Check against emergency stop loss. This is the most critical check.
        if self.check_emergency_stop():
             return False

        # 2. Check against max open trades
        if self.order_manager.get_open_order_count() >= self.max_open_trades:
            logger.warning(f"Risk Check FAILED: Exceeds max open trades ({self.max_open_trades}).")
            return False

        # TODO: Add more sophisticated checks
        # - Check for sufficient balance on both exchanges
        # - Check exposure to the specific currency
        # - Check recent volatility of the symbol

        logger.info(f"Risk Check PASSED for opportunity: {opportunity.symbol}")
        return True
    
    def update_pnl(self, buy_order: Order, sell_order: Order):
        """
        Updates the total Profit and Loss after a trade is completed.
        This is a simplified PnL calculation.
        """
        # Assuming fees are in the quote currency (e.g., USD)
        cost = buy_order.cost + (buy_order.fee['cost'] if buy_order.fee else 0)
        revenue = sell_order.cost - (sell_order.fee['cost'] if sell_order.fee else 0)

        trade_pnl = revenue - cost
        self.pnl += trade_pnl

        logger.success(f"PnL Updated. Trade PnL: ${trade_pnl:.2f}, Total PnL: ${self.pnl:.2f}")
        self._save_pnl()
    
    def emergency_stop(self):
        """
        Disables all further trading and could trigger alerts.
        """
        logger.critical("!!! EMERGENCY STOP TRIGGERED !!!")
        logger.critical("All further trading has been disabled due to exceeding loss limits.")
        self.trading_enabled = False
        # In a real system, you might add logic here to cancel all open orders. 

    def _save_pnl(self):
        """Saves the current PnL to a file."""
        try:
            with open(self.pnl_file, 'w') as f:
                json.dump({'total_pnl_usd': self.pnl}, f, indent=4)
        except IOError as e:
            logger.error(f"Failed to save PnL report to {self.pnl_file}: {e}")

    def _load_pnl(self) -> float:
        """Loads the PnL from a file, returning 0.0 if not found."""
        if not self.pnl_file.exists():
            return 0.0
        try:
            with open(self.pnl_file, 'r') as f:
                data = json.load(f)
                return data.get('total_pnl_usd', 0.0)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load PnL report from {self.pnl_file}: {e}")
            return 0.0 