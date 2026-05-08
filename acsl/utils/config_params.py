"""config_params — Tool の設計パラメータを config から自動取得するデコレータ

Usage:
  @config_params({
      "dt": 0.025,
      "frame": "NED",
      "gains.Q1": [100, 1],
      "gains.Q23": [1500, 1000, 200, 1],
  })
  class HLCController:
      def __init__(self, config=None):
          # self.dt, self.gains_Q1 等が自動設定済み

  # パラメータ再読み込み
  changed = tool.reload_params(new_config)

  # テンプレート / ドキュメント生成
  print(HLCController.param_template())
  print(HLCController.param_doc())
"""

from typing import Any, Callable, Dict, List, Optional, Tuple


def _get_nested(d: dict, path: str, default: Any) -> Any:
    """ネストされた dict からドット区切りパスで値を取得。"""
    keys = path.split(".")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _attr_name(path: str) -> str:
    """config パス → 属性名。"gains.Q23" → "gains_Q23"."""
    return path.replace(".", "_")


def _format_default(val: Any) -> str:
    if isinstance(val, list):
        return f"[{', '.join(str(v) for v in val)}]"
    elif isinstance(val, str):
        return f'"{val}"'
    else:
        return str(val)


def config_params(spec: Dict[str, Any]):
    """Tool クラスに config パラメータ自動取得機能を付与するデコレータ。

    Args:
        spec: {config_path: default_value} の辞書。
              config_path は "." でネスト対応。
    """
    param_spec: List[Tuple[str, str, Any]] = [
        (_attr_name(path), path, default)
        for path, default in spec.items()
    ]
    param_defaults = {_attr_name(path): default for path, default in spec.items()}

    def decorator(cls):
        original_init = cls.__init__

        def new_init(self, *args, config=None, **kwargs):
            config = config or {}
            for attr, path, default in param_spec:
                val = _get_nested(config, path, default)
                setattr(self, attr, val)
            original_init(self, *args, config=config, **kwargs)

        cls.__init__ = new_init
        cls._param_defaults = param_defaults
        cls._param_spec = param_spec

        def reload_params(self, config: dict) -> List[str]:
            """config からパラメータを再読み込み。変更された属性名のリストを返す。"""
            config = config or {}
            changed = []
            for attr, path, default in param_spec:
                val = _get_nested(config, path, default)
                old = getattr(self, attr, None)
                if val != old:
                    setattr(self, attr, val)
                    changed.append(attr)
            return changed

        cls.reload_params = reload_params

        @classmethod
        def param_template(cls_) -> str:
            """config テンプレート文字列を生成。"""
            lines = [f"# {cls_.__name__} parameters"]
            prev_prefix = ""
            for attr, path, default in param_spec:
                parts = path.split(".")
                if len(parts) > 1:
                    prefix = parts[0]
                    key = ".".join(parts[1:])
                    if prefix != prev_prefix:
                        lines.append(f"{prefix}:")
                        prev_prefix = prefix
                    lines.append(f"  {key}: {_format_default(default)}")
                else:
                    prev_prefix = ""
                    lines.append(f"{path}: {_format_default(default)}")
            return "\n".join(lines)

        cls.param_template = param_template

        @classmethod
        def param_doc(cls_) -> str:
            """パラメータ一覧のドキュメント文字列。"""
            lines = [f"{cls_.__name__} config parameters:"]
            for attr, path, default in param_spec:
                lines.append(f"  {path}: {_format_default(default)}  "
                             f"(attr: self.{attr})")
            return "\n".join(lines)

        cls.param_doc = param_doc

        return cls

    return decorator
