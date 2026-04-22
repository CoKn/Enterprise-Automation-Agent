from fastmcp import FastMCP
from statistics import mean, pstdev
from typing import Any


mcp = FastMCP(name="Data Quality")



@mcp.tool()
def filter_out_outliers(
    records: list[dict[str, Any]], property_name: str
) -> dict[str, Any]:
        """Filter records by one-standard-deviation distance from the mean.

        The tool reads a numeric property from each input record, calculates the
        population mean and population standard deviation for that property, and
        splits the records into two groups:
        - filtered_records: records where value is within [mean - std_dev, mean + std_dev]
        - outlier_records: records where value is outside that interval

        Parameters:
        - records: List of dictionary records to evaluate.
            Rows missing property_name are skipped.
        - property_name: The key in each record that points to the numeric value
            used for outlier detection.

        Returns:
        A dictionary with:
        - property_name: The property key used for filtering.
        - mean: The computed mean for the selected property.
        - std_dev: The computed population standard deviation.
        - filtered_records: Records within one standard deviation of the mean.
        - outlier_records: Records outside one standard deviation of the mean.

        Raises:
        - ValueError: If a present property value is not numeric.
        """
        if not records:
            return {
                "property_name": property_name,
                "mean": 0.0,
                "std_dev": 0.0,
                "filtered_records": [],
                "outlier_records": [],
            }

        numeric_values: list[float] = []
        numeric_records: list[dict[str, Any]] = []
        for record in records:
            if property_name not in record:
                continue

            value = record[property_name]
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Property '{property_name}' must be numeric. Found value: {value!r}"
                )

            numeric_values.append(float(value))
            numeric_records.append(record)

        if not numeric_records:
            return {
                "property_name": property_name,
                "filtered_records": [],
            }

        if len(numeric_records) == 1:
            return {
                "property_name": property_name,
                "mean": numeric_values[0],
                "std_dev": 0.0,
                "filtered_records": numeric_records,
                "outlier_records": [],
            }

        avg = mean(numeric_values)
        std_dev = pstdev(numeric_values)

        lower = avg - std_dev
        upper = avg + std_dev

        filtered_records = [
            record
            for record in numeric_records
            if lower <= float(record[property_name]) <= upper
        ]
        outlier_records = [
            record
            for record in numeric_records
            if float(record[property_name]) < lower or float(record[property_name]) > upper
        ]

        return {
            "property_name": property_name,
            # "mean": float(avg),
            # "std_dev": float(std_dev),
            "filtered_records": filtered_records,
            # "outlier_records": outlier_records,
        }


if __name__ == '__main__':
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8030)