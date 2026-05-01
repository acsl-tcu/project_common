from __future__ import annotations
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _deep_merge(base: Dict, overlay: Dict) -> Dict:
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif isinstance(value, list) and value and isinstance(value[0], str) and value[0].startswith("+"):
            existing = result.get(key, [])
            if isinstance(existing, list):
                result[key] = existing + [v.lstrip("+") if isinstance(v, str) else v for v in value]
            else:
                result[key] = value
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigLoader:
    def __init__(self):
        self._config: Dict[str, Any] = {}

    def load(self, config_path: str, profile: Optional[str] = None) -> Dict[str, Any]:
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required for config loading: pip install pyyaml")

        path = Path(config_path)
        with open(path) as f:
            self._config = yaml.safe_load(f) or {}

        if profile:
            profile_path = path.parent / "profiles" / f"{profile}.yaml"
            if profile_path.exists():
                with open(profile_path) as f:
                    overlay = yaml.safe_load(f) or {}
                self._config = _deep_merge(self._config, overlay)

        return self._config

    def load_dict(self, config: Dict[str, Any], profile_overlay: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._config = copy.deepcopy(config)
        if profile_overlay:
            self._config = _deep_merge(self._config, profile_overlay)
        return self._config

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def diff(self, base_path: str, profile: str) -> Dict[str, Tuple[Any, Any]]:
        try:
            import yaml
        except ImportError:
            return {}

        path = Path(base_path)
        with open(path) as f:
            base = yaml.safe_load(f) or {}

        profile_path = path.parent / "profiles" / f"{profile}.yaml"
        if not profile_path.exists():
            return {}

        with open(profile_path) as f:
            overlay = yaml.safe_load(f) or {}

        return self._collect_diffs(base, overlay)

    def _collect_diffs(self, base: Dict, overlay: Dict, prefix: str = "") -> Dict[str, Tuple[Any, Any]]:
        diffs = {}
        for key, new_val in overlay.items():
            full_key = f"{prefix}.{key}" if prefix else key
            old_val = base.get(key)
            if isinstance(new_val, dict) and isinstance(old_val, dict):
                diffs.update(self._collect_diffs(old_val, new_val, full_key))
            elif old_val != new_val:
                diffs[full_key] = (old_val, new_val)
        return diffs
