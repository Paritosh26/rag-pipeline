from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    """Load a YAML file as a mapping, returning `{}` if it is missing or empty."""
    file_path = Path(path)
    if not file_path.exists():
        return {}
    with file_path.open('r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}
