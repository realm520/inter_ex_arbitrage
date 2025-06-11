from loguru import logger

from arbitrage_bot.config.settings import config
from arbitrage_bot.arbitrage.scanner import ArbitrageOpportunity
from arbitrage_bot.execution.order_manager import OrderManager
from arbitrage_bot.models.order import Order
import json
from pathlib import Path
from typing import List

class RiskManager:
    """
    Manages overall trading risk by enforcing rules set in the configuration.
    It acts as a final checkpoint before a trade is executed.
    """
    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
        
        # Load risk parameters from config
        self.max_open_trades = config.risk_management.get('max_open_trades', 5)
        self.emergency_stop_loss_pct = config.risk_management.get('emergency_stop_loss_pct', 10.0)
        
        # PnL tracking
        self.pnl_file = Path(config.risk_management.get('pnl_file', 'pnl_report.json'))
        self.total_pnl_usd = self._load_pnl()

        logger.info("Risk Manager initialized.")
        logger.info(f" - Max open trades: {self.max_open_trades}")
        logger.info(f" - Emergency stop-loss threshold: {self.emergency_stop_loss_pct}%")
        logger.info(f" - Initial PnL loaded: ${self.total_pnl_usd:.2f}")

    def is_trade_safe(self, opportunity: ArbitrageOpportunity) -> bool:
        """
        Checks if executing a given opportunity is within risk parameters.

        Args:
            opportunity: The arbitrage opportunity to be checked.

        Returns:
            True if the trade is safe to execute, False otherwise.
        """
        if not self.trading_enabled:
            logger.warning("[Risk Check] FAILED: Trading is disabled by emergency stop.")
            return False

        # Check 1: Number of open trades
        # We count orders that are not yet fully filled or canceled.
        open_trades = self.order_manager.get_open_orders()
        if len(open_trades) >= self.max_open_trades:
            logger.warning(f"Risk Check FAILED: Too many open trades ({len(open_trades)}). Max is {self.max_open_trades}.")
            return False

        # 2. Check emergency stop-loss
        if self.total_pnl_usd < 0 and abs(self.total_pnl_usd) / 1000 > self.emergency_stop_loss_pct: # Assuming initial capital for pct calculation
             logger.critical(f"EMERGENCY STOP LOSS TRIGGERED! Current PnL (${self.total_pnl_usd:.2f}) exceeds threshold. No new trades allowed.")
             return False
        
        # 3. Check trade volume against order book depth (simplified)
        # A real implementation would check if the volume would cause significant slippage.
        # This is a placeholder for that logic.
        if opportunity.volume > 1000 / opportunity.buy_price: # Example: Don't trade more than $1000
             logger.warning(f"Risk Check FAILED: Trade volume too large for {opportunity.symbol}.")
             return False

        logger.success("Risk Check PASSED. Trade is safe to execute.")
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
        self.total_pnl_usd += trade_pnl

        logger.success(f"PnL Updated. Trade PnL: ${trade_pnl:.2f}, Total PnL: ${self.total_pnl_usd:.2f}")
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
                json.dump({'total_pnl_usd': self.total_pnl_usd}, f, indent=4)
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