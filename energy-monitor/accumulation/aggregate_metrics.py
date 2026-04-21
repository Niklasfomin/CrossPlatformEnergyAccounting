from abc import ABC, abstractmethod
from typing import Any, Dict


class MetricsAggregatorInterface(ABC):
    @abstractmethod
    def aggregate_metrics(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Aggregate metrics and return a dictionary of results.
        """
        pass
