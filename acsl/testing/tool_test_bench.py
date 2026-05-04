"""ToolTestBench — rosbag を使った Tool 単体テスト

rosbag のデータを時刻順に StepContext に変換し、
対象 Tool の step() を毎ステップ呼んで Result を収集する。

Usage:
    from acsl.testing import ToolTestBench

    bench = ToolTestBench.from_rosbag("recording.mcap")
    bench.set_tool(MyController(gain=3.0), category="controller")
    bench.map_topic("/odom", to_upstream="sensor", msg_to_result=odom_to_result)
    results = bench.run()
    bench.plot("input")
"""

from __future__ import annotations
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from acsl.types.context import StepContext, Time, Result


@dataclass
class TopicMapping:
    """rosbag トピック → upstream Result のマッピング"""
    topic: str
    upstream_name: str
    msg_to_result: Optional[Callable] = None
    msg_type: Optional[str] = None


@dataclass
class StepRecord:
    """1ステップの記録"""
    time: float
    context: StepContext
    result: Optional[Result]
    upstream: Dict[str, Result]


class ToolTestBench:
    """rosbag ベースの Tool 単体テスト環境

    rosbag からデータを読み込み、Tool の step() を
    各タイムスタンプで呼び出して結果を収集する。
    Tool 自体のコードは一切変更不要。
    """

    def __init__(self):
        self._tool = None
        self._tool_category: str = ""
        self._mappings: List[TopicMapping] = []
        self._messages: List[Tuple[float, str, Any]] = []  # (time, topic, msg)
        self._results: List[StepRecord] = []
        self._dt: float = 0.02
        self._parameter: Optional[Any] = None
        self._cascade_tools: List[Any] = []

    @classmethod
    def from_rosbag(cls, bag_path: str, storage_id: str = "") -> "ToolTestBench":
        """rosbag ファイルからテストベンチを作成する。

        Args:
            bag_path: .mcap ファイルまたは rosbag ディレクトリのパス
            storage_id: "mcap" or "sqlite3"。空文字なら自動検出。
        """
        bench = cls()
        bench._load_rosbag(bag_path, storage_id)
        return bench

    @classmethod
    def from_messages(cls, messages: List[Tuple[float, str, Any]]) -> "ToolTestBench":
        """テスト用のメッセージリストから作成（rosbag なしでテスト可能）。

        Args:
            messages: [(timestamp, upstream_name, result_or_value), ...]
        """
        bench = cls()
        bench._messages = messages
        return bench

    def set_tool(self, tool, category: str = "controller"):
        """テスト対象の Tool を設定する。"""
        self._tool = tool
        self._tool_category = category
        return self

    def set_cascade(self, tools: list):
        """cascade の Tool チェーンを設定する。対象 Tool の前段として実行される。"""
        self._cascade_tools = tools
        return self

    def set_parameter(self, parameter):
        """AgentParameter を設定する。"""
        self._parameter = parameter
        return self

    def set_dt(self, dt: float):
        """制御周期を設定する。"""
        self._dt = dt
        return self

    def map_topic(self, topic: str, to_upstream: str,
                  msg_to_result: Optional[Callable] = None):
        """rosbag トピック → upstream 名のマッピングを追加する。

        Args:
            topic: rosbag のトピック名 (例: "/odom")
            to_upstream: StepContext の upstream 名 (例: "sensor", "estimator")
            msg_to_result: ROS2 メッセージ → Result 変換関数。
                           None なら自動変換を試みる。
        """
        self._mappings.append(TopicMapping(
            topic=topic,
            upstream_name=to_upstream,
            msg_to_result=msg_to_result,
        ))
        return self

    def run(self, max_steps: Optional[int] = None) -> List[StepRecord]:
        """テストを実行する。

        Returns:
            各ステップの StepRecord リスト
        """
        if self._tool is None:
            raise ValueError("set_tool() でテスト対象を設定してください")

        self._results = []

        # トピック別に最新メッセージを保持
        latest: Dict[str, Any] = {}

        # メッセージを時刻順にソート
        sorted_msgs = sorted(self._messages, key=lambda m: m[0])

        if not sorted_msgs:
            return []

        t0 = sorted_msgs[0][0]
        step_count = 0

        # dt 間隔でステップを生成
        if sorted_msgs:
            t_end = sorted_msgs[-1][0]
            t_current = t0

            msg_idx = 0
            while t_current <= t_end:
                if max_steps is not None and step_count >= max_steps:
                    break

                # この時刻までのメッセージを消化
                while msg_idx < len(sorted_msgs) and sorted_msgs[msg_idx][0] <= t_current:
                    _, topic_or_upstream, msg = sorted_msgs[msg_idx]
                    latest[topic_or_upstream] = msg
                    msg_idx += 1

                # StepContext を構築
                time = Time(now=t_current - t0, dt=self._dt, step_count=step_count)
                ctx = StepContext(time=time, parameter=self._parameter)

                # upstream を設定
                upstream = {}
                for mapping in self._mappings:
                    raw = latest.get(mapping.topic)
                    if raw is None:
                        continue
                    if mapping.msg_to_result:
                        result = mapping.msg_to_result(raw, time)
                    else:
                        result = self._auto_convert(raw, time)
                    upstream[mapping.upstream_name] = result
                    ctx.update_results(mapping.upstream_name, result)

                # from_messages で直接 upstream 名が指定されている場合
                for key, val in latest.items():
                    if key.startswith("/"):
                        continue  # トピック名はスキップ
                    if key not in ctx.results:
                        if isinstance(val, Result):
                            ctx.update_results(key, val)
                        else:
                            ctx.update_results(key, Result(state=val, timestamp=time.now))

                # cascade 前段を実行
                for cascade_tool in self._cascade_tools:
                    cascade_result = cascade_tool.step(ctx)
                    if cascade_result is not None:
                        ctx._cascade_input = cascade_result
                        cat_name = getattr(cascade_tool, 'name', 'cascade')
                        ctx.update_results(f"{self._tool_category}.{cat_name}", cascade_result)

                # テスト対象 Tool を実行
                result = self._tool.step(ctx)

                self._results.append(StepRecord(
                    time=time.now,
                    context=ctx,
                    result=result,
                    upstream=dict(upstream),
                ))

                step_count += 1
                t_current += self._dt

        return self._results

    def get_timeseries(self, field: str = "input") -> Tuple[np.ndarray, np.ndarray]:
        """結果から時系列データを抽出する。

        Args:
            field: "input", "state", "output" or metadata key

        Returns:
            (times, values) の ndarray ペア
        """
        times = []
        values = []
        for record in self._results:
            if record.result is None:
                continue
            times.append(record.time)
            if field == "input" and record.result.input is not None:
                values.append(record.result.input)
            elif field == "state" and record.result.state is not None:
                values.append(np.atleast_1d(record.result.state))
            elif field == "output" and record.result.output is not None:
                values.append(np.atleast_1d(record.result.output))
            elif field in record.result.metadata:
                values.append(np.atleast_1d(record.result.metadata[field]))
            else:
                continue

        if not values:
            return np.array([]), np.array([])
        return np.array(times), np.array(values)

    def plot(self, field: str = "input", labels: Optional[List[str]] = None,
             title: Optional[str] = None):
        """結果をプロットする。

        Args:
            field: "input", "state", "output" or metadata key
            labels: 各次元のラベル
            title: グラフタイトル
        """
        import matplotlib.pyplot as plt

        times, values = self.get_timeseries(field)
        if len(times) == 0:
            print(f"No data for field '{field}'")
            return

        tool_name = getattr(self._tool, 'name', 'tool')
        title = title or f"{tool_name} — {field}"

        if values.ndim == 1:
            plt.figure(figsize=(10, 4))
            plt.plot(times, values, label=labels[0] if labels else field)
            plt.xlabel("time [s]")
            plt.ylabel(field)
            plt.title(title)
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.show()
        else:
            n_dims = values.shape[1]
            fig, axes = plt.subplots(n_dims, 1, figsize=(10, 3 * n_dims), sharex=True)
            if n_dims == 1:
                axes = [axes]
            for i in range(n_dims):
                label = labels[i] if labels and i < len(labels) else f"dim[{i}]"
                axes[i].plot(times, values[:, i], label=label)
                axes[i].set_ylabel(label)
                axes[i].legend()
                axes[i].grid(True, alpha=0.3)
            axes[-1].set_xlabel("time [s]")
            fig.suptitle(title)
            plt.tight_layout()
            plt.show()

    def summary(self) -> Dict[str, Any]:
        """テスト結果のサマリーを返す。"""
        if not self._results:
            return {"steps": 0}

        valid = [r for r in self._results if r.result is not None]
        none_count = len(self._results) - len(valid)

        summary = {
            "steps": len(self._results),
            "valid": len(valid),
            "none_results": none_count,
            "duration": self._results[-1].time - self._results[0].time if len(self._results) > 1 else 0,
        }

        # input の統計
        times, inputs = self.get_timeseries("input")
        if len(inputs) > 0:
            summary["input_mean"] = np.mean(inputs, axis=0).tolist()
            summary["input_std"] = np.std(inputs, axis=0).tolist()
            summary["input_min"] = np.min(inputs, axis=0).tolist()
            summary["input_max"] = np.max(inputs, axis=0).tolist()

        return summary

    def to_csv(self, path: str, field: str = "input"):
        """結果を CSV に保存する。"""
        times, values = self.get_timeseries(field)
        if len(times) == 0:
            print(f"No data for field '{field}'")
            return

        if values.ndim == 1:
            values = values.reshape(-1, 1)

        header = "time," + ",".join(f"{field}_{i}" for i in range(values.shape[1]))
        data = np.column_stack([times, values])
        np.savetxt(path, data, delimiter=",", header=header, comments="")
        print(f"Saved {len(times)} rows to {path}")

    # --- 内部メソッド ---

    def _load_rosbag(self, bag_path: str, storage_id: str = ""):
        """rosbag を読み込んでメッセージリストに変換する。"""
        from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message

        path = Path(bag_path)
        if not path.exists():
            raise FileNotFoundError(f"rosbag not found: {bag_path}")

        # storage_id を自動検出
        if not storage_id:
            if path.suffix == ".mcap" or (path.is_dir() and any(path.glob("*.mcap"))):
                storage_id = "mcap"
            else:
                storage_id = "sqlite3"

        # ディレクトリの場合はそのまま、ファイルの場合は親ディレクトリ
        if path.is_file():
            uri = str(path)
        else:
            uri = str(path)

        reader = SequentialReader()
        storage_options = StorageOptions(uri=uri, storage_id=storage_id)
        converter_options = ConverterOptions(
            input_serialization_format="cdr",
            output_serialization_format="cdr",
        )
        reader.open(storage_options, converter_options)

        # トピック型の取得
        topic_types = {}
        for topic_info in reader.get_all_topics_and_types():
            topic_types[topic_info.name] = topic_info.type

        # メッセージ読み込み
        self._messages = []
        while reader.has_next():
            topic, data, timestamp = reader.read_next()
            t_sec = timestamp / 1e9  # nanoseconds → seconds

            msg_type_str = topic_types.get(topic, "")
            if not msg_type_str:
                continue

            try:
                msg_class = get_message(msg_type_str)
                msg = deserialize_message(data, msg_class)
                self._messages.append((t_sec, topic, msg))
            except Exception:
                continue

        print(f"Loaded {len(self._messages)} messages from {bag_path}")
        print(f"Topics: {list(topic_types.keys())}")

    def _auto_convert(self, msg: Any, time: Time) -> Result:
        """ROS2 メッセージを Result に自動変換する（ベストエフォート）。"""
        # Odometry
        if hasattr(msg, 'pose') and hasattr(msg.pose, 'pose') and hasattr(msg.pose.pose, 'position'):
            pos = msg.pose.pose.position
            ori = msg.pose.pose.orientation
            yaw = 2.0 * np.arctan2(ori.z, ori.w)
            return Result(
                state=np.array([pos.x, pos.y, yaw]),
                timestamp=time.now,
            )

        # PoseWithCovarianceStamped
        if hasattr(msg, 'pose') and hasattr(msg.pose, 'pose') and hasattr(msg, 'header'):
            pos = msg.pose.pose.position
            ori = msg.pose.pose.orientation
            yaw = 2.0 * np.arctan2(ori.z, ori.w)
            return Result(
                state=np.array([pos.x, pos.y, yaw]),
                metadata={"covariance": list(msg.pose.covariance) if hasattr(msg.pose, 'covariance') else []},
                timestamp=time.now,
            )

        # Twist
        if hasattr(msg, 'linear') and hasattr(msg, 'angular'):
            return Result(
                input=np.array([msg.linear.x, msg.angular.z]),
                timestamp=time.now,
            )

        # LaserScan
        if hasattr(msg, 'ranges') and hasattr(msg, 'angle_min'):
            return Result(
                state=np.array(msg.ranges),
                metadata={
                    "angle_min": msg.angle_min,
                    "angle_max": msg.angle_max,
                    "angle_increment": msg.angle_increment,
                    "scan_msg": msg,
                },
                timestamp=time.now,
            )

        # fallback: そのまま state に入れる
        return Result(state=msg, timestamp=time.now)
