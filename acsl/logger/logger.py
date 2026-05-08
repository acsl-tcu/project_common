"""Logger — 制御データ記録・クエリ・保存

log() はメモリ append のみ (制御ループを阻害しない)。
ファイル書き出しはバックグラウンドスレッドで定期 flush。

クエリショートカット:
  "t" → 時刻, "phase" → フェーズ
  属性: "s"=sensor, "e"=estimator, "r"=reference, "c"=controller, "a"=actuator
  変数: "p"=pos[0:3], "v"=vel[3:6], "q"=quat[6:10], "w"=angvel[10:13]
        "state"=全次元, "input"=controller出力
"""

from __future__ import annotations
import json
import os
import threading
import time as time_mod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from acsl.types.context import StepContext

_ATTR_MAP = {
    "s": "sensor", "e": "estimator", "r": "reference",
    "c": "controller", "a": "actuator",
}
_VAR_SLICES = {
    "p": slice(0, 3), "v": slice(3, 6),
    "q": slice(6, 10), "w": slice(10, 13),
}


@dataclass
class LogEntry:
    t: float
    phase: str
    sensor: Optional[np.ndarray] = None
    estimator: Optional[np.ndarray] = None
    reference: Optional[np.ndarray] = None
    controller: Optional[np.ndarray] = None
    actuator: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Logger:
    """制御データロガー。log() は append のみ、I/O は autosave で行う。"""

    DEFAULT_DIR = "/root/ros2_ws/Data"

    def __init__(self, name: str = "flight", directory: str = ""):
        self._entries: List[LogEntry] = []
        self._wall_start = time_mod.time()
        self._name = name
        self._directory = directory or self.DEFAULT_DIR
        self._autosave_thread: Optional[threading.Thread] = None
        self._autosave_stop = threading.Event()
        self._flush_cursor = 0
        self._flush_path: Optional[str] = None

    @property
    def size(self) -> int:
        return len(self._entries)

    def log(self, t: float, phase: str, ctx: StepContext):
        entry = LogEntry(t=t, phase=phase)
        meta = {}
        for cat_name in _ATTR_MAP.values():
            result = ctx.results.get(cat_name)
            if result is not None and result.state is not None:
                arr = np.asarray(result.state, dtype=np.float64).ravel()
                setattr(entry, cat_name, arr.copy())
                if result.metadata:
                    for k, v in result.metadata.items():
                        if isinstance(v, (int, float, bool, str)):
                            meta[f"{cat_name}.{k}"] = v
        entry.metadata = meta
        self._entries.append(entry)

    # --- autosave ---

    def start_autosave(self, interval: float = 30.0):
        if self._autosave_thread is not None:
            return
        os.makedirs(self._directory, exist_ok=True)
        ts = time_mod.strftime("%Y%m%d_%H%M%S")
        self._flush_path = os.path.join(
            self._directory, f"Log_{self._name}_{ts}.jsonl")
        self._autosave_stop.clear()
        self._autosave_thread = threading.Thread(
            target=self._autosave_loop, args=(interval,), daemon=True)
        self._autosave_thread.start()

    def stop_autosave(self):
        if self._autosave_thread is None:
            return
        self._autosave_stop.set()
        self._autosave_thread.join(timeout=5.0)
        self._autosave_thread = None
        self._flush_to_file()

    def _autosave_loop(self, interval: float):
        while not self._autosave_stop.wait(timeout=interval):
            self._flush_to_file()

    def _flush_to_file(self):
        if self._flush_path is None:
            return
        n = len(self._entries)
        if n <= self._flush_cursor:
            return
        batch = self._entries[self._flush_cursor:n]
        self._flush_cursor = n
        lines = [json.dumps(self._entry_to_dict(e)) for e in batch]
        with open(self._flush_path, "a") as f:
            f.write("\n".join(lines) + "\n")

    # --- クエリ ---

    def query(self, var: str, attr: str = "") -> np.ndarray:
        if var == "t":
            return np.array([e.t for e in self._entries])
        if var == "phase":
            return np.array([e.phase for e in self._entries])
        cat_name = _ATTR_MAP.get(attr, "estimator")
        if var == "input":
            cat_name = "controller"
            var = "state"
        data = []
        for e in self._entries:
            arr = getattr(e, cat_name, None)
            if arr is not None:
                data.append(arr if var == "state" else
                            arr[_VAR_SLICES[var]] if var in _VAR_SLICES else arr)
            else:
                data.append(None)
        if not data or all(d is None for d in data):
            return np.array([])
        dim = next(d.shape[0] for d in data if d is not None)
        result = np.full((len(data), dim), np.nan)
        for i, d in enumerate(data):
            if d is not None:
                result[i, :d.shape[0]] = d
        return result

    def query_metadata(self, key: str) -> np.ndarray:
        return np.array([e.metadata.get(key, np.nan) for e in self._entries])

    # --- 保存・読み込み ---

    @staticmethod
    def _entry_to_dict(e: LogEntry) -> dict:
        rec = {"t": e.t, "phase": e.phase}
        for cat in _ATTR_MAP.values():
            arr = getattr(e, cat, None)
            if arr is not None:
                rec[cat] = arr.tolist()
        if e.metadata:
            rec["metadata"] = e.metadata
        return rec

    def save(self, name: str = None, directory: str = None) -> str:
        name = name or self._name
        directory = directory or self._directory
        os.makedirs(directory, exist_ok=True)
        ts = time_mod.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(directory, f"Log_{name}_{ts}.json")
        records = [self._entry_to_dict(e) for e in self._entries]
        with open(path, "w") as f:
            json.dump(records, f)
        return path

    @classmethod
    def load(cls, path: str) -> "Logger":
        logger = cls()
        with open(path) as f:
            content = f.read().strip()
        if content.startswith("["):
            records = json.loads(content)
        else:
            records = [json.loads(ln) for ln in content.split("\n") if ln.strip()]
        for rec in records:
            entry = LogEntry(t=rec["t"], phase=rec["phase"])
            for cat in _ATTR_MAP.values():
                if cat in rec:
                    setattr(entry, cat, np.array(rec[cat]))
            entry.metadata = rec.get("metadata", {})
            logger._entries.append(entry)
        return logger

    def summary(self) -> Dict[str, Any]:
        if not self._entries:
            return {"size": 0}
        t = self.query("t")
        phases = self.query("phase")
        pos = self.query("p", "e")
        return {
            "size": self.size,
            "duration": float(t[-1] - t[0]) if len(t) > 1 else 0.0,
            "phases": list(dict.fromkeys(phases)),
            "pos_range": {
                ax: [float(np.nanmin(pos[:, i])), float(np.nanmax(pos[:, i]))]
                for i, ax in enumerate("xyz")
            } if pos.size else {},
        }
