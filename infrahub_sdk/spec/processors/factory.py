from collections.abc import Sequence
from typing import Any

from ..models import InfrahubObjectParameters
from .data_processor import DataProcessor
from .range_expand_processor import RangeExpandDataProcessor

PROCESSOR_PER_KIND: dict[str, DataProcessor] = {}


class DataProcessorFactory:
    """Factory to create appropriate data processor based on strategy"""

    @classmethod
    def get_processors(cls, kind: str, parameters: InfrahubObjectParameters) -> Sequence[DataProcessor]:
        processors: list[DataProcessor] = []
        if parameters.expand_range:
            processors.append(RangeExpandDataProcessor())
        if kind in PROCESSOR_PER_KIND:
            processors.append(PROCESSOR_PER_KIND[kind])

        return processors

    @classmethod
    async def process_data(
        cls,
        kind: str,
        data: list[dict[str, Any]],
        parameters: InfrahubObjectParameters,
    ) -> list[dict[str, Any]]:
        processors = cls.get_processors(kind=kind, parameters=parameters)
        for processor in processors:
            data = await processor.process_data(data=data)
        return data
