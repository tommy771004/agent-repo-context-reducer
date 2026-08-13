from __future__ import annotations

import json
import pathlib
from typing import Any

from .storage import prepare_state_dir, state_dir

DEFAULT = {"version": 1, "trusted_providers": [], "preferred_providers": {}}


def config_path(root: pathlib.Path) -> pathlib.Path:
    return state_dir(root) / "config.json"


def load_config(root: pathlib.Path) -> dict[str, Any]:
    path = config_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") == 1:
            return {"version": 1,
                    "trusted_providers": list(data.get("trusted_providers", [])),
                    "preferred_providers": dict(data.get("preferred_providers", {}))}
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "trusted_providers": [], "preferred_providers": {}}


def save_config(root: pathlib.Path, data: dict[str, Any]) -> pathlib.Path:
    path = config_path(root)
    prepare_state_dir(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def is_trusted(root: pathlib.Path, provider_id: str) -> bool:
    return provider_id in set(load_config(root).get("trusted_providers", []))


def trust_provider(root: pathlib.Path, provider_id: str, trusted: bool = True) -> dict[str, Any]:
    data = load_config(root)
    items = set(data.get("trusted_providers", []))
    if trusted:
        items.add(provider_id)
    else:
        items.discard(provider_id)
    data["trusted_providers"] = sorted(items)
    save_config(root, data)
    return data


def prefer_provider(root: pathlib.Path, capability: str, provider_id: str | None) -> dict[str, Any]:
    data = load_config(root)
    prefs = data.setdefault("preferred_providers", {})
    if provider_id:
        prefs[capability] = provider_id
    else:
        prefs.pop(capability, None)
    save_config(root, data)
    return data
