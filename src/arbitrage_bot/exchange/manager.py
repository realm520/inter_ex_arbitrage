import asyncio
import ccxt.pro as ccxt
from typing import Dict, Optional
from loguru import logger
import orjson

from arbitrage_bot.config.settings import config

class ExchangeManager:
    """Manages connections to multiple cryptocurrency exchanges."""

    def __init__(self, app_config: config, error_handler: "ErrorHandler"):
        self._config = app_config
        self.error_handler = error_handler
        self.exchanges: Dict[str, ccxt.Exchange] = {}

    async def initialize_exchanges(self):
        """Initializes and connects to all enabled exchanges from the config."""
        logger.info("Initializing exchange connections...")
        
        enabled_exchanges = []
        if hasattr(self._config, 'exchanges'):
             enabled_exchanges = [name for name, conf in self._config.exchanges.items() if conf.get('enabled')]

        if not enabled_exchanges:
            logger.warning("No exchanges are enabled in the configuration file.")
            return
        
        tasks = [self.add_exchange(name) for name in enabled_exchanges]
        await asyncio.gather(*tasks)
        logger.info(f"Finished exchange initialization. {len(self.exchanges)} connections active.")

    async def add_exchange(self, exchange_name: str):
        """
        Connects to a single exchange and adds it to the manager.
        """
        if exchange_name in self.exchanges:
            logger.warning(f"Exchange '{exchange_name}' is already connected.")
            return

        exchange_config = self._config.exchanges.get(exchange_name)
        if not exchange_config:
            logger.error(f"Configuration for exchange '{exchange_name}' not found.")
            return

        # Check circuit breaker before attempting to connect
        if self.error_handler.is_circuit_open(exchange_name):
            return

        exchange = None
        try:
            exchange_class = getattr(ccxt, exchange_name)
            exchange = exchange_class({
                'apiKey': exchange_config.get('api_key'),
                'secret': exchange_config.get('secret'),
                'password': exchange_config.get('password'), # For exchanges like KuCoin
                'options': {
                    'defaultType': 'spot',
                },
            })
            # --- Performance Optimization ---
            exchange.json = orjson.dumps
            exchange.unjson = orjson.loads
            # ------------------------------
            
            # Test connectivity by loading markets
            await exchange.load_markets()
            self.exchanges[exchange_name] = exchange
            logger.success(f"Successfully connected to {exchange_name}.")
            self.error_handler.reset_error(exchange_name) # Reset error count on success
        except AttributeError:
             logger.error(f"Exchange '{exchange_name}' is not supported by ccxt.pro.")
        except Exception as e:
            logger.error(f"Failed to connect to {exchange_name}: {e}")
            self.error_handler.record_error(exchange_name) # Record error
            if exchange:
                # Ensure the session is closed if the instance was created but connection failed
                await exchange.close()

    def get_exchange(self, exchange_name: str) -> Optional[ccxt.Exchange]:
        """Retrieves a connected exchange instance by its name."""
        exchange = self.exchanges.get(exchange_name)
        if exchange is None:
            logger.warning(f"Attempted to get a non-existent or disconnected exchange: {exchange_name}")
        return exchange

    async def close_all(self):
        """Closes all active exchange connections."""
        logger.info("Closing all exchange connections...")
        tasks = [exchange.close() for exchange in self.exchanges.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.exchanges.clear()
        logger.info("All exchange connections have been closed.")

    def set_error_handler(self, error_handler: "ErrorHandler"):
        """Sets the error handler after initialization."""
        self.error_handler = error_handler

# Singleton instance
exchange_manager = ExchangeManager(config, None) 