#!/usr/bin/env python3
"""Generic JSON validation utilities for x-news pipeline."""

import json
import sys
from pathlib import Path
from typing import Any


def load_json_file(path: str | Path) -> Any:
    """Load and parse a JSON file.

    Args:
        path: Path to JSON file

    Returns:
        Parsed JSON content

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_json_schema(data: Any, schema: dict, path: str = "root") -> list[str]:
    """Validate data against a JSON schema (simple implementation).

    This is a basic structural validator. For full JSON Schema validation,
    use the jsonschema library in environments where it's available.

    Args:
        data: Data to validate
        schema: Schema to validate against
        path: Current path for error messages

    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    schema_type = schema.get("type")

    # Handle array type at any level (including top-level)
    if schema_type == "array":
        if not isinstance(data, list):
            errors.append(f"{path}: expected array, got {type(data).__name__}")
            return errors
        item_schema = schema.get("items", {})
        for i, item in enumerate(data):
            item_path = f"{path}[{i}]"
            item_schema_type = item_schema.get("type")
            # Validate scalar array items (string, integer, number, boolean)
            if item_schema_type == "string":
                if not isinstance(item, str):
                    errors.append(f"{item_path}: expected string, got {type(item).__name__}")
            elif item_schema_type == "integer":
                if not isinstance(item, int) or isinstance(item, bool):
                    errors.append(f"{item_path}: expected integer, got {type(item).__name__}")
            elif item_schema_type == "number":
                if not isinstance(item, (int, float)) or isinstance(item, bool):
                    errors.append(f"{item_path}: expected number, got {type(item).__name__}")
            elif item_schema_type == "boolean":
                if not isinstance(item, bool):
                    errors.append(f"{item_path}: expected boolean, got {type(item).__name__}")
            elif item_schema_type == "object":
                if not isinstance(item, dict):
                    errors.append(f"{item_path}: expected object, got {type(item).__name__}")
                elif "properties" in item_schema:
                    errors.extend(validate_json_schema(item, item_schema, item_path))
            elif isinstance(item, dict) and "properties" in item_schema:
                # Array of objects without explicit item type but with properties
                errors.extend(validate_json_schema(item, item_schema, item_path))
        return errors

    # Handle object type
    if schema_type == "object":
        if not isinstance(data, dict):
            errors.append(f"{path}: expected object, got {type(data).__name__}")
            return errors

        # Check required fields
        for required in schema.get("required", []):
            if required not in data:
                errors.append(f"{path}: missing required field '{required}'")

        # Check properties
        properties = schema.get("properties", {})
        for key, value in data.items():
            if key in properties:
                prop_schema = properties[key]
                prop_type = prop_schema.get("type")

                # Handle nested array
                if prop_type == "array":
                    if not isinstance(value, list):
                        errors.append(f"{path}.{key}: expected array, got {type(value).__name__}")
                    elif "items" in prop_schema:
                        item_schema = prop_schema["items"]
                        for i, item in enumerate(value):
                            errors.extend(validate_json_schema(item, item_schema, f"{path}.{key}[{i}]"))

                # Handle nested object
                elif prop_type == "object":
                    if not isinstance(value, dict):
                        errors.append(f"{path}.{key}: expected object, got {type(value).__name__}")
                    elif "properties" in prop_schema:
                        errors.extend(validate_json_schema(value, prop_schema, f"{path}.{key}"))

                # Handle scalar types
                elif prop_type == "string":
                    if not isinstance(value, str):
                        errors.append(f"{path}.{key}: expected string, got {type(value).__name__}")
                elif prop_type == "integer":
                    if not isinstance(value, int) or isinstance(value, bool):
                        errors.append(f"{path}.{key}: expected integer, got {type(value).__name__}")
                elif prop_type == "number":
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        errors.append(f"{path}.{key}: expected number, got {type(value).__name__}")
                elif prop_type == "boolean":
                    if not isinstance(value, bool):
                        errors.append(f"{path}.{key}: expected boolean, got {type(value).__name__}")

        return errors

    # Scalar type at top level (not object or array)
    if schema_type == "string":
        if not isinstance(data, str):
            errors.append(f"{path}: expected string, got {type(data).__name__}")
    elif schema_type == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            errors.append(f"{path}: expected integer, got {type(data).__name__}")
    elif schema_type == "number":
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            errors.append(f"{path}: expected number, got {type(data).__name__}")
    elif schema_type == "boolean":
        if not isinstance(data, bool):
            errors.append(f"{path}: expected boolean, got {type(data).__name__}")

    return errors


def print_validation_errors(errors: list[str], file=sys.stderr) -> bool:
    """Print validation errors and return whether there were any.

    Args:
        errors: List of error messages
        file: Output file

    Returns:
        True if there were errors, False otherwise
    """
    if errors:
        for error in errors:
            print(error, file=file)
        return True
    return False
