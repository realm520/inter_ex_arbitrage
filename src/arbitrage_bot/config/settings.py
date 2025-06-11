import os
import yaml
from dotenv import load_dotenv
from pathlib import Path

# Important: The user should create a `.env` file in the project root.
# They can copy the structure from `.env.example`.
# --- .env.example ---
# BINANCE_API_KEY="YOUR_BINANCE_API_KEY"
# BINANCE_API_SECRET="YOUR_BINANCE_API_SECRET"
# KRAKEN_API_KEY="YOUR_KRAKEN_API_KEY"
# KRAKEN_API_SECRET="YOUR_KRAKEN_API_SECRET"
# --------------------

# Load environment variables from .env file
# The search path for the .env file starts from this file's location and goes upwards.
env_path = Path(__file__).parent.parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """
    A class to manage configuration for the arbitrage bot.
    It loads settings from a YAML file and integrates them with
    API credentials from environment variables.
    """
    def __init__(self, config_path: str = 'config.yaml'):
        # Construct the full path to the config file relative to the project root
        self.config_file_path = Path(__file__).parent.parent.parent.parent / config_path
        if not self.config_file_path.is_file():
            raise FileNotFoundError(f"Configuration file not found at: {self.config_file_path}")

        # Load the base configuration from the YAML file
        with open(self.config_file_path, 'r') as f:
            self._config = yaml.safe_load(f)

        # Inject API credentials from environment variables into the config
        self._load_api_credentials()

    def _load_api_credentials(self):
        """
        Private method to load API credentials from environment variables
        for all exchanges defined in the config file.
        """
        if 'exchanges' in self._config:
            for exchange_name in self._config['exchanges']:
                api_key_var = f"{exchange_name.upper()}_API_KEY"
                api_secret_var = f"{exchange_name.upper()}_API_SECRET"
                
                api_key = os.getenv(api_key_var)
                api_secret = os.getenv(api_secret_var)
                
                # Store the credentials in the exchange's config dictionary
                self._config['exchanges'][exchange_name]['api_key'] = api_key
                self._config['exchanges'][exchange_name]['api_secret'] = api_secret

    def get(self, key, default=None):
        """
        Retrieves a configuration value for a given key.
        """
        return self._config.get(key, default)

    @property
    def exchanges(self) -> dict:
        """
        Returns the configuration for all exchanges.
        """
        return self.get('exchanges', {})

    @property
    def arbitrage(self) -> dict:
        """
        Returns the arbitrage parameters.
        """
        return self.get('arbitrage', {})
        
    @property
    def risk(self) -> dict:
        """
        Returns the risk management parameters.
        """
        return self.get('risk', {})

    @property
    def logging(self) -> dict:
        """
        Returns the logging configuration.
        """
        return self.get('logging', {})

# Create a global config instance to be used throughout the application
config = Config() 