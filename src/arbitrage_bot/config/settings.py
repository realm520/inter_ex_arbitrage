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
    Manages application configuration by loading from a YAML file
    and environment variables. Allows nested access to config values
    using dot notation.
    """
    def __init__(self, config_path: str = 'config.yaml'):
        # Load environment variables from .env file
        load_dotenv()

        # Load base configuration from YAML
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_file, 'r') as f:
            yaml_config = yaml.safe_load(f)

        # Recursively set attributes
        self._set_attributes(yaml_config)

        # Override with environment variables if they exist
        self._override_with_env_vars()

    def _set_attributes(self, data: dict):
        """
        Recursively sets attributes on the Config object.
        Nested dictionaries are converted to new Config instances.
        """
        for key, value in data.items():
            if isinstance(value, dict):
                # If the value is a dictionary, create a new "sub-Config"
                setattr(self, key, self._make_nested_config(value))
            else:
                setattr(self, key, value)

    def _make_nested_config(self, data: dict):
        """Helper to create a nested Config object."""
        nested_config = Config.__new__(Config) # Create a new instance without calling __init__
        nested_config._set_attributes(data)
        return nested_config

    def _override_with_env_vars(self):
        """
        Overrides YAML config with environment variables.
        Specifically looks for API keys and secrets for exchanges.
        """
        if hasattr(self, 'exchanges'):
            # self.exchanges is a Config object, but .items() will work
            for exchange_name, exchange_config in self.exchanges.items():
                api_key_env = f"{exchange_name.upper()}_API_KEY"
                secret_env = f"{exchange_name.upper()}_SECRET"

                if os.getenv(api_key_env):
                    setattr(exchange_config, 'api_key', os.getenv(api_key_env))
                if os.getenv(secret_env):
                    setattr(exchange_config, 'secret', os.getenv(secret_env))

    def get(self, key, default=None):
        """Provides a .get() method, similar to a dictionary."""
        return getattr(self, key, default)

    def items(self):
        """Allows iterating over key-value pairs, like a dictionary."""
        return vars(self).items()

# Singleton instance to be used across the application
config = Config() 