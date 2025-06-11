# Inter-Exchange Arbitrage Bot

A high-performance, low-latency cryptocurrency arbitrage bot that discovers and capitalizes on price discrepancies between various digital asset exchanges. Built with Python, `ccxt`, `asyncio`, and `uv`.

## ✨ Features

- **Multi-Exchange Support**: Easily connect to any exchange supported by the CCXT library.
- **High Performance**: Built on `asyncio` for non-blocking I/O and `orjson` for fast JSON parsing to handle real-time data streams with minimal latency.
- **Resilient by Design**: Features an integrated circuit breaker and exponential backoff, making the bot robust against network issues and exchange API errors.
- **Risk Management**: Includes configurable risk controls, such as max trade size, to protect capital.
- **Paper Trading Mode**: Test strategies and bot performance safely without executing real trades.
- **Professional CLI**: Comes with a clean, `typer`-based command-line interface for starting, stopping, and configuring the bot.
- **Structured Logging**: Uses `loguru` for clear, configurable, and insightful logging.

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv): A fast Python package installer and resolver.

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/inter_exchange_arbitrage.git
    cd inter_exchange_arbitrage
    ```

2.  **Create a virtual environment:**
    ```bash
    uv venv
    ```

3.  **Activate the environment:**
    - On macOS/Linux:
      ```bash
      source .venv/bin/activate
      ```
    - On Windows:
      ```bash
      .venv\Scripts\activate
      ```

4.  **Install dependencies (in editable mode):**
    This command installs all required packages and makes the `arb-bot` command available in your terminal.
    ```bash
    uv pip install -e .
    ```

### Configuration

1.  **Environment Variables for API Keys:**
    Create a `.env` file in the root of the project by copying the example:
    ```bash
    cp .env.example .env
    ```
    Now, edit the `.env` file and add your exchange API keys.

2.  **Bot Configuration:**
    Review and adjust the bot's parameters in `config/config.yaml`. You can enable/disable exchanges, set arbitrage thresholds, and configure risk management settings here.

### Running the Bot

-   **Start in Paper Trading Mode (Recommended):**
    ```bash
    arb-bot start --paper
    ```

-   **Start in Live Trading Mode (Use with caution!):**
    ```bash
    arb-bot start
    ```

-   **View all commands:**
    ```bash
    arb-bot --help
    ```

## Architecture Overview

The bot is designed with a modular architecture, where each component has a specific responsibility:

-   `Config`: Loads and manages configuration from `config.yaml` and environment variables.
-   `ExchangeManager`: Handles connections to all exchanges.
-   `DataFetcher`: Subscribes to real-time order book data via WebSockets.
-   `ArbitrageScanner`: Analyzes the data to find potential arbitrage opportunities.
-   `TradeExecutor`: Executes trades when an opportunity is confirmed.
-   `OrderManager`: Tracks the status of all placed orders.
-   `RiskManager`: Provides a final check before any trade is executed.
-   `ErrorHandler`: A centralized circuit breaker and error handling utility.
-   `cli.py`: The command-line interface entry point.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details. 