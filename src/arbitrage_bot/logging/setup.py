import sys
from pathlib import Path
from loguru import logger

from arbitrage_bot.config.settings import config

def setup_logging():
    """
    Sets up the loguru logging system for the application.
    - Removes default handlers.
    - Adds a colored console logger.
    - Adds a rotating file logger for all levels.
    - Catches all uncaught exceptions.
    """
    # 1. Remove the default handler to have full control
    logger.remove()

    # 2. Add a console logger with colors and a specific format
    log_level = config.logging.get('level', 'INFO').upper()
    logger.add(
        sys.stderr,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        colorize=True
    )

    # 3. Add a rotating file logger
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True) # Create the logs directory if it doesn't exist
    
    file_log_path = log_dir / "bot_{time:YYYY-MM-DD}.log"
    
    logger.add(
        file_log_path,
        level="DEBUG",  # Log everything to the file
        rotation="00:00",  # New file at midnight
        retention="7 days",  # Keep logs for 7 days
        enqueue=True,  # Make logging non-blocking
        backtrace=True, # Show full stack trace for exceptions
        diagnose=True, # Add exception variable values
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )

    # 4. Catch all uncaught exceptions
    logger.catch(onerror=lambda _: sys.exit(1))

    logger.info("Logging system initialized.") 