from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, TYPE_CHECKING
from loguru import logger

from arbitrage_bot.model import Opportunity
from arbitrage_bot.exchange.manager import ExchangeManager
from arbitrage_bot.config.settings import config
from arbitrage_bot.execution.order_manager import OrderManager
from arbitrage_bot.models.order import Order

@dataclass
class ExecutedTrade:
    """
    Represents a completed arbitrage trade, including details from both legs.
    """
    opportunity: Opportunity
    buy_order_id: str
    sell_order_id: str
    status: str  # e.g., 'completed', 'failed', 'partial'
    timestamp: float = time.time()

if TYPE_CHECKING:
    from arbitrage_bot.exchange.manager import ExchangeManager
    from arbitrage_bot.execution.order_manager import OrderManager

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

    async def execute_opportunity(self, opportunity: Opportunity) -> Dict[str, any]:
        """
        Executes a buy and a sell order based on the provided arbitrage opportunity.
        Returns a dictionary with execution results.
        """
        logger.info(f"Attempting to execute trade for opportunity: {opportunity.symbol} "
                    f"| Buy on {opportunity.buy_exchange} | Sell on {opportunity.sell_exchange}")

        if self.paper_mode:
            logger.warning(f"[PAPER MODE] Skipping real execution for {opportunity.symbol}.")
            # Log the intended trade for simulation purposes
            self.order_manager.record_paper_trade(opportunity)
            return {
                'success': True,
                'paper_mode': True,
                'buy_order': None,
                'sell_order': None,
                'message': 'Paper trade recorded'
            }

        buy_exchange = self.exchange_manager.get_exchange(opportunity.buy_exchange)
        sell_exchange = self.exchange_manager.get_exchange(opportunity.sell_exchange)

        if not buy_exchange or not sell_exchange:
            logger.error("Could not get exchange instances for trade execution.")
            return {
                'success': False,
                'error': 'Exchange instances not available',
                'buy_order': None,
                'sell_order': None
            }

        buy_order = None
        sell_order = None

        try:
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
                return {
                    'success': True,
                    'buy_order': buy_order,
                    'sell_order': sell_order,
                    'message': 'Both orders executed successfully'
                }
            
            # Handle partial execution
            if buy_order and not sell_order:
                logger.warning(f"Only BUY order was successful. Attempting to cancel order {buy_order['id']}.")
                await self._handle_partial_execution(buy_exchange, buy_order, 'buy')
                return {
                    'success': False,
                    'error': 'Partial execution - buy order placed but sell order failed',
                    'buy_order': buy_order,
                    'sell_order': None
                }
            
            if sell_order and not buy_order:
                logger.warning(f"Only SELL order was successful. Attempting to cancel order {sell_order['id']}.")
                await self._handle_partial_execution(sell_exchange, sell_order, 'sell')
                return {
                    'success': False,
                    'error': 'Partial execution - sell order placed but buy order failed',
                    'buy_order': None,
                    'sell_order': sell_order
                }

            return {
                'success': False,
                'error': 'Both orders failed',
                'buy_order': None,
                'sell_order': None
            }
        except Exception as e:
            logger.error(f"Error executing trade for {opportunity.symbol}: {e}")
            
            # Attempt to clean up any successful orders
            if buy_order:
                await self._handle_partial_execution(buy_exchange, buy_order, 'buy')
            if sell_order:
                await self._handle_partial_execution(sell_exchange, sell_order, 'sell')
                
            return {
                'success': False,
                'error': f'Execution failed: {str(e)}',
                'buy_order': buy_order,
                'sell_order': sell_order
            }

    async def _handle_partial_execution(self, exchange, order: dict, side: str):
        """
        Handles partial execution by attempting to cancel the successful order.
        This prevents leaving unhedged positions.
        """
        try:
            logger.warning(f"Attempting to cancel {side} order {order['id']} due to partial execution")
            cancelled_order = await exchange.cancel_order(order['id'], order['symbol'])
            
            if cancelled_order['status'] == 'canceled':
                logger.success(f"Successfully cancelled {side} order {order['id']}")
                self.order_manager.update_order_status(order['id'], 'canceled')
            else:
                logger.warning(f"Order {order['id']} could not be cancelled - it may have been filled. Status: {cancelled_order['status']}")
                # If the order was filled, we need to handle the position
                if cancelled_order['status'] == 'closed':
                    logger.critical(f"Order {order['id']} was filled! Manual intervention required to hedge position.")
                    
        except Exception as e:
            logger.error(f"Failed to cancel {side} order {order['id']}: {e}")
            logger.critical(f"Manual intervention required for order {order['id']}")
            
    def _create_mock_order(self, opportunity: Opportunity, side: str, amount: float) -> Order:
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

    async def place_order(self, exchange_name: str, symbol: str, side: str, amount: float, price: float) -> dict:
        """A wrapper for placing an order with error handling."""
        exchange = self.exchange_manager.get_exchange(exchange_name)
        if not exchange:
            logger.error(f"Cannot place order: Exchange '{exchange_name}' is not available.")
            return None
        
        try:
            # Note: ccxt unified method is create_limit_buy_order, etc.
            # but create_order is the most general.
            order = await exchange.create_order(symbol, 'limit', side, amount, price)
            logger.info(f"Placed {side} order on {exchange_name} for {amount} {symbol} @ {price}")
            self.order_manager.record_order(order)
            return order
        except Exception as e:
            logger.error(f"Failed to place {side} order on {exchange_name}: {e}")
            # TODO: Implement order cancellation logic if one leg of the trade fails
            return None 

    async def liquidate_all_positions(self):
        """
        Connects to all exchanges, cancels all open orders, and liquidates all assets
        to the primary quote currency (e.g., USDT).
        """
        logger.warning("!!! INITIATING EMERGENCY LIQUIDATION !!!")
        quote_currencies = ['USDT', 'USD', 'BUSD', 'USDC'] # Currencies to keep
        
        for exchange_name, exchange in self.exchange_manager.exchanges.items():
            try:
                logger.info(f"--- Processing liquidation for {exchange_name} ---")
                
                # 1. Cancel all open orders for this exchange
                logger.info(f"Cancelling all open orders on {exchange_name}...")
                # In a real scenario, a more robust implementation would fetch open orders 
                # and cancel them one by one, as `cancel_all_orders` is not universally supported.
                if 'cancelAllOrders' in exchange.has and exchange.has['cancelAllOrders']:
                    await exchange.cancel_all_orders()
                else:
                    logger.warning(f"Exchange {exchange_name} does not support cancel_all_orders. Manual cancellation may be needed.")

                # 2. Fetch current balances
                balance = await exchange.fetch_balance()
                
                # 3. Find assets to liquidate
                assets_to_liquidate = []
                for currency, amount in balance['total'].items():
                    # Only consider assets with a meaningful amount
                    if amount > 0 and currency not in quote_currencies:
                        assets_to_liquidate.append((currency, amount))
                
                if not assets_to_liquidate:
                    logger.info(f"No assets to liquidate on {exchange_name}.")
                    continue
                
                logger.warning(f"Found assets to liquidate on {exchange_name}: {assets_to_liquidate}")

                # 4. Liquidate each asset
                for currency, amount in assets_to_liquidate:
                    # Find a market to sell this currency for a quote currency
                    market_symbol = None
                    for quote in quote_currencies:
                        symbol = f"{currency}/{quote}"
                        if symbol in exchange.markets:
                            market_symbol = symbol
                            break
                    
                    if not market_symbol:
                        logger.error(f"Could not find a market to sell {currency} on {exchange_name}. Manual intervention required.")
                        continue
                        
                    # Place a market sell order
                    logger.warning(f"Placing MARKET SELL order for {amount} {currency} on {exchange_name} via {market_symbol}")
                    if not self.paper_mode:
                        await exchange.create_market_sell_order(market_symbol, amount)
                    else:
                        logger.info(f"[PAPER MODE] Skipping MARKET SELL for {amount} {currency} on {exchange_name}")

            except Exception as e:
                logger.critical(f"An error occurred during liquidation on {exchange_name}: {e}. Manual intervention may be required!")

        logger.critical("!!! EMERGENCY LIQUIDATION COMPLETE !!!") 