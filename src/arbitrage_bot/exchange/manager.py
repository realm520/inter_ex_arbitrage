import asyncio
import ccxt.pro as ccxtpro
from typing import Dict

from arbitrage_bot.config.settings import config

class ExchangeManager:
    """
    Manages connections to multiple exchanges using ccxt.pro.
    Initializes and holds exchange instances for use throughout the application.
    """

    def __init__(self):
        self._config = config
        self.exchanges: Dict[str, ccxtpro.Exchange] = {}

    async def initialize_exchanges(self):
        """
        Initializes connections to all exchanges enabled in the configuration.
        It tests the connection by loading markets for each exchange.
        """
        enabled_exchanges = [
            (name, conf) for name, conf in self._config.exchanges.items() if conf.get('enabled')
        ]

        # Create tasks for each exchange connection
        connection_tasks = [
            self._connect_to_exchange(name, conf) for name, conf in enabled_exchanges
        ]
        
        # Run connection tasks concurrently
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)

        for name, instance in results:
            if instance:
                self.exchanges[name] = instance
                print(f"Successfully connected to {name} and loaded markets.")

    async def _connect_to_exchange(self, name: str, conf: dict) -> (str, ccxtpro.Exchange or None):
        """
        A helper method to connect to a single exchange.
        Returns a tuple of (exchange_name, exchange_instance) or (exchange_name, None) on failure.
        """
        try:
            exchange_class = getattr(ccxtpro, name)
            
            # Use a dictionary for exchange settings to avoid errors with None values
            exchange_settings = {
                'apiKey': conf.get('api_key'),
                'secret': conf.get('api_secret'),
                'enableRateLimit': True,
            }
            
            instance = exchange_class(exchange_settings)
            
            # Test the connection by loading markets. This is a crucial step.
            await instance.load_markets()
            
            return name, instance

        except (AttributeError, ccxtpro.base.errors.AuthenticationError) as e:
            print(f"Error connecting to {name}: {e}")
            print(f"Please ensure '{name}' is a valid ccxt exchange and your API keys are correct.")
        except Exception as e:
            print(f"An unexpected error occurred while connecting to {name}: {e}")

        return name, None

    def get_exchange(self, name: str) -> ccxtpro.Exchange or None:
        """
        Retrieves a connected exchange instance by its name.
        """
        return self.exchanges.get(name)

    async def close_all(self):
        """
        Closes all active exchange connections gracefully.
        """
        print("Closing all exchange connections...")
        close_tasks = [
            exchange.close() for exchange in self.exchanges.values() if hasattr(exchange, 'close')
        ]
        await asyncio.gather(*close_tasks, return_exceptions=True)
        self.exchanges.clear()
        print("All connections closed.")

# A single instance to be used across the application
exchange_manager = ExchangeManager() 