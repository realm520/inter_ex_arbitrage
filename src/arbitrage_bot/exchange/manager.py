import asyncio
from typing import Dict, Optional, TYPE_CHECKING
import ccxt.pro as ccxt
from loguru import logger
import orjson

from arbitrage_bot.config.settings import config

if TYPE_CHECKING:
    from arbitrage_bot.utils.error_handler import ErrorHandler


class ExchangeManager:
    """
    Manages all exchange connections and provides a central point of access.
    Implements a singleton pattern to ensure only one instance exists.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ExchangeManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config: dict, error_handler: "ErrorHandler"):
        """
        Initializes the ExchangeManager.
        The check 'hasattr(self, 'config')' prevents re-initialization.
        """
        if hasattr(self, 'config'):
            return # Already initialized
            
        self.config = config.get("exchanges", {})
        self.exchanges: dict[str, ccxt.Exchange] = {}
        self.error_handler = error_handler

    async def initialize_exchanges(self):
        """
        Initializes connections to all exchanges enabled in the config.
        """
        logger.info("Initializing exchange connections...")
        enabled_exchanges = [
            name for name, conf in self.config.items() if conf.get("enabled")
        ]

        if not enabled_exchanges:
            logger.warning("No exchanges enabled in the configuration.")
            return

        tasks = [self.add_exchange(name) for name in enabled_exchanges]
        await asyncio.gather(*tasks)
        logger.info(f"Finished exchange initialization. {len(self.exchanges)} connections active.")

    async def add_exchange(self, exchange_name: str) -> bool:
        """
        Creates and adds a single exchange connection.

        Returns:
            True if the connection was successful, False otherwise.
        """
        exchange_config = self.config.get(exchange_name)
        if not exchange_config:
            logger.error(f"Configuration for exchange '{exchange_name}' not found.")
            return False

        # Use the exchange's name as id if 'id' is not specified in config
        exchange_id = exchange_config.get("id", exchange_name)
        
        if not hasattr(ccxt, exchange_id):
            logger.error(f"Exchange '{exchange_id}' is not supported by ccxt.")
            return False

        params = exchange_config.get("params", {})
        exchange = getattr(ccxt, exchange_id)(params)

        try:
            # Test connection - load_markets is a good way to do this
            await exchange.load_markets()
            self.exchanges[exchange_name] = exchange
            logger.success(f"Successfully connected to {exchange_name}.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {exchange_name}: {e}")
            await exchange.close()
        return False

    def get_exchange(self, exchange_name: str) -> Optional[ccxt.Exchange]:
        """
        Retrieves an active exchange instance by name.

        Returns:
            An active exchange instance or None if not found or circuit is open.
        """
        exchange = self.exchanges.get(exchange_name)
        if not exchange:
            # This is a critical failure if it happens after initialization.
            logger.error(
                f"FATAL: Exchange '{exchange_name}' not found in the initialized exchanges dictionary. This should not happen."
            )
            return None
        
        # Check circuit breaker status
        if self.error_handler.is_circuit_open(exchange_name):
            logger.warning(f"Circuit for {exchange_name} is open. Temporarily skipping.")
            return None
            
        return exchange

    async def close_all(self):
        """
        Closes all active exchange connections.
        """
        logger.info("Closing all exchange connections...")
        tasks = [ex.close() for ex in self.exchanges.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.exchanges.clear()
        logger.info("All exchange connections have been closed.")

