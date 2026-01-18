from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, Optional

import jsonschema
from jsonschema import Draft202012Validator, FormatChecker


@dataclass
class ValidationResult:
    ok: bool
    error: Optional[str] = None


class SchemaRegistry:
    """Loads JSON Schema files shipped with the package."""

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    def load(self, name: str) -> Dict[str, Any]:
        if name in self._cache:
            return self._cache[name]

        path = f"schemas/{name}"
        try:
            with resources.files("aos_context").joinpath(path).open("r", encoding="utf-8") as f:
                schema = json.load(f)
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Schema not found: {name} (looked for {path})") from e

        self._cache[name] = schema
        return schema


_registry = SchemaRegistry()


def validate_instance(schema_name: str, instance: Any) -> ValidationResult:
    """Validate instance against a packaged Draft 2020-12 JSON Schema."""

    schema = _registry.load(schema_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if not errors:
        return ValidationResult(ok=True)

    # Surface first error in a compact but useful string
    err = errors[0]
    location = ".".join(str(p) for p in err.path) if err.path else "<root>"
    msg = f"{location}: {err.message}"
    return ValidationResult(ok=False, error=msg)


def assert_valid(schema_name: str, instance: Any) -> None:
    res = validate_instance(schema_name, instance)
    if not res.ok:
        raise jsonschema.ValidationError(res.error or "Validation failed")
