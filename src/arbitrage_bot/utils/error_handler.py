import asyncio
import time
from enum import Enum
from loguru import logger
from collections import defaultdict

from .circuit_breaker import CircuitBreaker

class ErrorSeverity(Enum):
    """Defines the severity levels for errors."""
    LOW = 1      # Non-critical, can be logged and ignored.
    MEDIUM = 2   # Requires attention, may need a retry.
    HIGH = 3     # Critical, may require a component restart or circuit breaking.
    FATAL = 4    # Cannot continue, the application must stop.

class ErrorHandler:
    """
    A centralized error handler that uses a circuit breaker and exponential backoff.
    """
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, backoff_base: int = 2):
        self._circuit_breaker = CircuitBreaker(failure_threshold, recovery_timeout)
        self._backoff_base = backoff_base
        self._error_counts: defaultdict[str, int] = defaultdict(int)

    def is_circuit_open(self, component_id: str) -> bool:
        """Checks if the circuit is open for a specific component."""
        is_open = self._circuit_breaker.is_open(component_id)
        if is_open:
            logger.warning(f"Circuit for {component_id} is OPEN. Temporarily suspending operations.")
        return is_open

    def record_error(self, component_id: str):
        """Records an error for a component, potentially tripping the circuit breaker."""
        logger.error(f"Error recorded for component: {component_id}")
        self._error_counts[component_id] += 1
        self._circuit_breaker.record_failure(component_id)

    def reset_error(self, component_id: str):
        """Resets the error state for a component upon successful operation."""
        if self._error_counts[component_id] > 0:
            logger.info(f"Component {component_id} has recovered. Resetting error state.")
            self._circuit_breaker.record_success(component_id)
            self._error_counts[component_id] = 0

    async def get_backoff_delay(self, component_id: str) -> float:
        """Calculates the exponential backoff delay for a component."""
        count = self._error_counts[component_id]
        delay = self._backoff_base ** count
        return min(delay, 60)  # Cap delay at 60 seconds 