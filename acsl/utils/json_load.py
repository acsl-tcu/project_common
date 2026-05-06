"""コメント付きJSONファイルの読み込みユーティリティ

// 行コメントを除去してからパースする。
config_dir を指定して呼び出す:
    json_load("floor_map", config_dir="/path/to/config")
"""

import json
import re
import os


def json_load(name: str, config_dir: str = "") -> dict:
    """config_dir/<name>.json を読み込む。// コメント対応。

    Args:
        name: ファイル名（拡張子なし）
        config_dir: 検索ディレクトリ。未指定なら呼び出し元の config/ を探す。
    """
    if config_dir:
        path = os.path.join(config_dir, f"{name}.json")
    else:
        import inspect
        caller_dir = os.path.dirname(os.path.abspath(inspect.stack()[1].filename))
        path = os.path.join(caller_dir, "config", f"{name}.json")

    with open(path, "r") as f:
        data = f.read()
    return json.loads(re.sub(r"//.*\n", "\n", data))
