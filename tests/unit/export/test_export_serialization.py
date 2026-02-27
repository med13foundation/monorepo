"""
Serialization utility tests for the bulk export system.

These helpers are shared across kernel exports and need to remain stable and
type-safe.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import NamedTuple

from src.application.export.serialization import (
    coerce_scalar,
    item_to_csv_row,
    resolve_nested_value,
    serialize_item,
)
from src.application.export.utils import copy_filters


class _Point(NamedTuple):
    x: int
    y: int


def test_serialize_item_with_dict() -> None:
    data = {"key": "value", "number": 42}
    assert serialize_item(data) == data


def test_serialize_item_with_datetime() -> None:
    ts = datetime(2026, 2, 9, 12, 0, tzinfo=UTC)
    serialized = serialize_item(ts)
    assert isinstance(serialized, str)
    assert "2026-02-09T12:00:00" in serialized


def test_serialize_item_with_namedtuple() -> None:
    pt = _Point(1, 2)
    assert serialize_item(pt) == {"x": 1, "y": 2}


def test_serialize_item_with_object() -> None:
    class Obj:
        def __init__(self) -> None:
            self.name = "test"
            self.value = 7

    serialized = serialize_item(Obj())
    assert serialized == {"name": "test", "value": 7}


def test_resolve_nested_value_handles_missing_path() -> None:
    data = {"a": {"b": 1}}
    assert resolve_nested_value(data, ["a", "c"]) == ""


def test_item_to_csv_row_supports_dotted_paths() -> None:
    item = {"identifier": {"hpo_id": "HP:0000001"}, "name": "Phenotype"}
    row = item_to_csv_row(item, ["identifier.hpo_id", "name"])
    assert row["identifier.hpo_id"] == "HP:0000001"
    assert row["name"] == "Phenotype"


def test_coerce_scalar_leaves_primitives() -> None:
    assert coerce_scalar("x") == "x"
    assert coerce_scalar(1) == 1
    assert coerce_scalar(1.5) == 1.5
    flag = True
    assert coerce_scalar(flag) is True
    assert coerce_scalar(None) is None


def test_copy_filters_clones_mapping() -> None:
    original = {"limit": 10}
    cloned = copy_filters(original)
    assert cloned == {"limit": 10}
    assert cloned is not original


def test_export_json_serialization_round_trip() -> None:
    payload = {"entities": [{"id": "ent-1", "metadata_payload": {"k": "v"}}]}
    rendered = json.dumps(payload, default=str)
    parsed = json.loads(rendered)
    assert parsed["entities"][0]["metadata_payload"]["k"] == "v"
