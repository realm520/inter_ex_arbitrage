import asyncio
import time

from arbitrage_bot.exchange.manager import exchange_manager
from arbitrage_bot.data.fetcher import DataFetcher
from arbitrage_bot.arbitrage.scanner import ArbitrageScanner

async def main():
    """
    The main execution function for the arbitrage bot.
    Connects, fetches data, and scans for opportunities.
    """
    # 1. Initialize exchange connections
    print("Initializing exchange connections...")
    await exchange_manager.initialize_exchanges()

    if len(exchange_manager.exchanges) < 2:
        print("Arbitrage requires at least two connected exchanges. Exiting.")
        await exchange_manager.close_all()
        return

    # 2. Initialize the DataFetcher and start monitoring
    data_fetcher = DataFetcher(exchange_manager)
    data_fetcher.start_monitoring()

    # Give some time for the first order book data to arrive
    print("Waiting for initial data...")
    await asyncio.sleep(5)

    # 3. Initialize the ArbitrageScanner
    arbitrage_scanner = ArbitrageScanner(data_fetcher)
    print("Starting arbitrage scanner...")

    # 4. Main loop to continuously scan for opportunities
    try:
        while True:
            opportunities = arbitrage_scanner.scan()
            
            if opportunities:
                for opp in opportunities:
                    print("\n" + "="*20)
                    print(f"!!! ARBITRAGE OPPORTUNITY FOUND !!!")
                    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(opp.timestamp))}")
                    print(f"Symbol: {opp.symbol}")
                    print(f"Buy on '{opp.buy_exchange}' at {opp.buy_price}")
                    print(f"Sell on '{opp.sell_exchange}' at {opp.sell_price}")
                    print(f"Potential Profit: {opp.potential_profit_pct:.4f}%")
                    print("="*20 + "\n")

            # Scan every second
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        print("Main task cancelled.")
    finally:
        # 5. Clean up on exit
        print("Cleaning up...")
        data_fetcher.stop_monitoring()
        await exchange_manager.close_all()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Shutting down.") 