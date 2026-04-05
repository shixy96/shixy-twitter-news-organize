"""Tests for x_news_shared.validate module."""

import pytest
from io import StringIO
from x_news_shared import validate_json_schema
from x_news_shared.validate import print_validation_errors


class TestValidateJsonSchemaObject:
    def test_valid_object(self):
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        errors = validate_json_schema({"name": "test"}, schema)
        assert errors == []

    def test_missing_required_field(self):
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        errors = validate_json_schema({}, schema)
        assert "root: missing required field 'name'" in errors

    def test_wrong_type_string(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        errors = validate_json_schema({"name": 123}, schema)
        assert "root.name: expected string, got int" in errors

    def test_boolean_not_integer(self):
        schema = {"type": "object", "properties": {"flag": {"type": "integer"}}}
        errors = validate_json_schema({"flag": True}, schema)
        assert "root.flag: expected integer, got bool" in errors

    def test_root_not_object(self):
        schema = {"type": "object"}
        errors = validate_json_schema("not an object", schema)
        assert errors == ["root: expected object, got str"]


class TestValidateJsonSchemaArray:
    def test_valid_string_array(self):
        schema = {"type": "array", "items": {"type": "string"}}
        errors = validate_json_schema(["a", "b", "c"], schema)
        assert errors == []

    def test_array_item_wrong_type(self):
        schema = {"type": "array", "items": {"type": "string"}}
        errors = validate_json_schema(["a", 123, "c"], schema)
        assert len(errors) == 1
        assert "expected string, got int" in errors[0]

    def test_valid_integer_array(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        errors = validate_json_schema([1, 2, 3], schema)
        assert errors == []

    def test_boolean_not_integer_in_array(self):
        schema = {"type": "array", "items": {"type": "integer"}}
        errors = validate_json_schema([1, True, 3], schema)
        assert "expected integer, got bool" in errors[0]


class TestValidateJsonSchemaNested:
    def test_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
        }
        errors = validate_json_schema({"user": {"name": "test"}}, schema)
        assert errors == []

    def test_nested_object_wrong_type(self):
        schema = {
            "type": "object",
            "properties": {"user": {"type": "object", "properties": {"name": {"type": "string"}}}},
        }
        errors = validate_json_schema({"user": "not an object"}, schema)
        assert "root.user: expected object, got str" in errors

    def test_nested_array_of_objects(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "string"}}},
                }
            },
        }
        data = {"items": [{"id": "1"}, {"id": "2"}]}
        errors = validate_json_schema(data, schema)
        assert errors == []


class TestValidateJsonSchemaScalar:
    def test_valid_string(self):
        schema = {"type": "string"}
        errors = validate_json_schema("hello", schema)
        assert errors == []

    def test_invalid_string(self):
        schema = {"type": "string"}
        errors = validate_json_schema(123, schema)
        assert "root: expected string, got int" in errors

    def test_valid_integer(self):
        schema = {"type": "integer"}
        errors = validate_json_schema(42, schema)
        assert errors == []

    def test_valid_boolean(self):
        schema = {"type": "boolean"}
        errors = validate_json_schema(True, schema)
        assert errors == []


class TestPrintValidationErrors:
    def test_no_errors(self):
        stderr = StringIO()
        result = print_validation_errors([], file=stderr)
        assert result is False
        assert stderr.getvalue() == ""

    def test_with_errors(self):
        stderr = StringIO()
        result = print_validation_errors(["error 1", "error 2"], file=stderr)
        assert result is True
        assert "error 1" in stderr.getvalue()
        assert "error 2" in stderr.getvalue()
