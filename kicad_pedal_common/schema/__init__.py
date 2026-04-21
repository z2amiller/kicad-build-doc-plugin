"""JSON schema files for manifest and BOM entry validation."""

import json
import os
from typing import Any, Dict

_SCHEMA_DIR = os.path.dirname(os.path.abspath(__file__))


def load_schema(name: str) -> Dict[str, Any]:
    """Load a JSON schema by filename (e.g. 'manifest-v1.schema.json')."""
    path = os.path.join(_SCHEMA_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


MANIFEST_V1_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "manifest-v1.schema.json")
BOM_ENTRY_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "bom-entry.schema.json")
