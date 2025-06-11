import time
from collections import defaultdict

class CircuitBreaker:
    """
    A simple circuit breaker implementation to prevent repeated calls to a failing component.
    """
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        """
        Initializes the CircuitBreaker.

        Args:
            failure_threshold (int): The number of consecutive failures before opening the circuit.
            recovery_timeout (int): The number of seconds to wait before moving from OPEN to HALF-OPEN state.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state: defaultdict[str, str] = defaultdict(lambda: "CLOSED")
        self._failure_count: defaultdict[str, int] = defaultdict(int)
        self._last_failure_time: defaultdict[str, float] = defaultdict(float)

    def is_open(self, component_id: str) -> bool:
        """Checks if the circuit is open for a given component."""
        if self._state[component_id] == "OPEN":
            if time.time() - self._last_failure_time[component_id] > self.recovery_timeout:
                self._state[component_id] = "HALF-OPEN"
            return True
        return False

    def record_failure(self, component_id: str):
        """Records a failure for a component."""
        self._failure_count[component_id] += 1
        self._last_failure_time[component_id] = time.time()
        if self._failure_count[component_id] >= self.failure_threshold:
            self._state[component_id] = "OPEN"

    def record_success(self, component_id: str):
        """Records a success for a component, resetting its state."""
        self.reset(component_id)

    def reset(self, component_id: str):
        """Resets the state for a given component."""
        self._state[component_id] = "CLOSED"
        self._failure_count[component_id] = 0
        self._last_failure_time[component_id] = 0.0

    def get_state(self, component_id: str) -> str:
        """Returns the current state of a component."""
        # Update state to HALF-OPEN if recovery timeout has passed
        self.is_open(component_id)
        return self._state[component_id] 