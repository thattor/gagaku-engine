"""Strict JSON documents with errors that do not disclose source data."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, SchemaError, ValidationError


class DocumentError(ValueError):
    """A fixed diagnostic code; never include input values or file paths."""


def decode_json_document(raw: bytes):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DocumentError("duplicate_json_key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise DocumentError("invalid_json_number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except DocumentError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise DocumentError("invalid_json") from None


def load_json_document(path: Path):
    try:
        raw = path.read_bytes()
    except OSError:
        raise DocumentError("document_unreadable") from None
    return decode_json_document(raw)


def validate_document(data, schema):
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(data)
    except SchemaError:
        raise DocumentError("invalid_schema_definition") from None
    except (ValidationError, RecursionError):
        raise DocumentError("schema_validation_failed") from None
