from __future__ import annotations

import copy
import logging
import re
from typing import Any

from ...exceptions import ValidationError
from ..range_expansion import MATCH_PATTERN, range_expansion
from .data_processor import DataProcessor

log = logging.getLogger("infrahub_sdk")


class RangeExpandDataProcessor(DataProcessor):
    """Process data with range expansion"""

    @classmethod
    async def process_data(
        cls,
        data: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Expand any item in data with range pattern in any value. Supports multiple fields, requires equal expansion length."""
        range_pattern = re.compile(MATCH_PATTERN)
        expanded = []
        for item in data:
            # Find all fields to expand
            expand_fields = {}
            for key, value in item.items():
                if isinstance(value, str) and range_pattern.search(value):
                    try:
                        expand_fields[key] = range_expansion(value)
                    except (ValueError, TypeError, KeyError):
                        # If expansion fails, treat as no expansion
                        log.debug(
                            f"Range expansion failed for value '{value}' in key '{key}'. Treating as no expansion."
                        )
                        expand_fields[key] = [value]
            if not expand_fields:
                expanded.append(item)
                continue
            # Check all expanded lists have the same length
            lengths = [len(v) for v in expand_fields.values()]
            if len(set(lengths)) > 1:
                raise ValidationError(
                    identifier="range_expansion",
                    message=f"Range expansion mismatch: fields expanded to different lengths: {lengths}",
                )
            n = lengths[0]
            # Zip expanded values and produce new items
            for i in range(n):
                new_item = copy.deepcopy(item)
                for key, values in expand_fields.items():
                    new_item[key] = values[i]
                expanded.append(new_item)
        return expanded
