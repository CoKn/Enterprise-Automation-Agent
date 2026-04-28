from fastmcp import FastMCP
from statistics import mean, pstdev
from typing import Any
import math


mcp = FastMCP(name="Data Quality")


def _get_value_case_insensitive(mapping: dict[str, Any], key: str) -> Any | None:
    if key in mapping:
        return mapping[key]

    wanted = key.casefold()
    for current_key, current_value in mapping.items():
        if isinstance(current_key, str) and current_key.casefold() == wanted:
            return current_value
    return None


def _extract_property_value(record: dict[str, Any], property_name: str) -> Any | None:
    """Resolve property value from either top-level record or Notion-style nested properties."""
    top_level_value = _get_value_case_insensitive(record, property_name)
    if top_level_value is not None:
        return top_level_value

    nested_properties = record.get("properties")
    if isinstance(nested_properties, dict):
        nested_value = _get_value_case_insensitive(nested_properties, property_name)
        if nested_value is not None:
            return nested_value

    return None


def _is_valid_numeric(value: Any) -> bool:
    """
    Return True only for real numeric values that are safe for statistics.

    Excludes:
    - None
    - strings
    - booleans
    - NaN
    - infinity
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    if not math.isfinite(float(value)):
        return False
    return True


@mcp.tool()
def filter_out_outliers(
    records: list[dict[str, Any]]
) -> dict[str, Any]:
    """Filter records by one-standard-deviation distance from the mean.

    What this tool does:
    - Reads a numeric property from each input record.
    - Automatically skips records where the property is missing or non-numeric.
    - Computes the population mean and population standard deviation.
    - Splits valid numeric records into:
      - filtered_records: values within [mean - std_dev, mean + std_dev]
      - outlier_records: values outside that interval

    Parameters:
    - records:
        List of dictionary records to evaluate.

    Returns:
    A dictionary with:
    - property_name: The property key used for filtering.
    - mean: The computed mean for valid numeric values.
    - std_dev: The computed population standard deviation.
    - filtered_records: Records within one standard deviation of the mean.
    - outlier_records: Records outside one standard deviation of the mean.
    - skipped_records: Records skipped because the property was missing or invalid.
    """
    property_name = "Price"
    if not records:
        return {
            "property_name": property_name,
            # "mean": 0.0,
            # "std_dev": 0.0,
            "filtered_records": [],
            # "outlier_records": [],
            # "skipped_records": [],
        }

    numeric_values: list[float] = []
    numeric_records: list[tuple[dict[str, Any], float]] = []
    skipped_records: list[dict[str, Any]] = []

    for record in records:
        value = _extract_property_value(record, property_name)
        if not _is_valid_numeric(value):
            skipped_records.append(record)
            continue

        numeric_value = float(value)
        numeric_values.append(numeric_value)
        numeric_records.append((record, numeric_value))

    if not numeric_records:
        return {
            "property_name": property_name,
            # "mean": 0.0,
            # "std_dev": 0.0,
            "filtered_records": [],
            # "outlier_records": [],
            # "skipped_records": skipped_records,
        }

    if len(numeric_records) == 1:
        return {
            "property_name": property_name,
            # "mean": numeric_values[0],
            # "std_dev": 0.0,
            "filtered_records": [numeric_records[0][0]],
            # "outlier_records": [],
            # "skipped_records": skipped_records,
        }

    avg = mean(numeric_values)
    std_dev = pstdev(numeric_values)

    lower = avg - std_dev
    upper = avg + std_dev

    filtered_records = [
        record
        for record, numeric_value in numeric_records
        if lower <= numeric_value <= upper
    ]
    outlier_records = [
        record
        for record, numeric_value in numeric_records
        if numeric_value < lower or numeric_value > upper
    ]

    return {
        # "property_name": property_name,
        # "mean": float(avg),
        # "std_dev": float(std_dev),
        "filtered_records": filtered_records,
        # "outlier_records": outlier_records,
        # "skipped_records": skipped_records,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8030)