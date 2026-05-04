# PoC ワークフロー: 新しいツールの開発手順

## 概要

新しい制御ツール（コントローラ、推定器、参照生成器など）を開発するための手順。
**contract 定義なし**で PoC を回し、ロジック確定後に contract を自動生成して統合する。

```
Step 1: step() だけ書く（PoC）
  ↓
Step 2: ToolTestBench で rosbag テスト
  ↓
Step 3: ロジック確定 → /generate-contract で contract 自動生成
  ↓
Step 4: robot_building.py に組み込み（統合テスト）
```

## Step 1: ツールを書く

`tools/` に Python ファイルを作成。必要なのは `name` と `step()` だけ。

```python
# tools/my_controller.py
import numpy as np
from acsl.types.context import StepContext, Result

class MyController:
    name = "my_ctrl"

    def __init__(self, kp=1.0, kd=0.1):
        self._kp = kp
        self._kd = kd
        self._prev_error = np.zeros(3)

    def step(self, context):
        est = context.get_upstream("estimator")
        ref = context.get_upstream("reference")
        if est is None or ref is None:
            return None

        error = ref.state - est.state
        d_error = (error - self._prev_error) / context.time.dt
        self._prev_error = error.copy()

        u = self._kp * error + self._kd * d_error
        return Result(
            input=np.array([u[0], u[2]]),  # [vx, wz]
            metadata={"error_norm": float(np.linalg.norm(error))},
        )
```

**この時点で contract() は不要。**

## Step 2: ToolTestBench で単体テスト

### 方法 A: rosbag を使う（実データテスト）

実機や Isaac Sim で rosbag を録画済みの場合:

```python
from acsl.testing import ToolTestBench
from tools.my_controller import MyController

# rosbag からテストベンチを作成
bench = ToolTestBench.from_rosbag("launcher/rosbags/recording.mcap")

# テスト対象の Tool を設定
bench.set_tool(MyController(kp=2.0, kd=0.5), category="controller")

# rosbag のトピック → upstream 名をマッピング
bench.map_topic("/odom", to_upstream="sensor")          # Odometry → sensor
bench.map_topic("/slam_pose", to_upstream="estimator")   # PoseWithCov → estimator

# 実行
results = bench.run()

# 結果を可視化
bench.plot("input", labels=["vx", "wz"])

# 統計情報
print(bench.summary())
# {'steps': 500, 'valid': 498, 'input_mean': [0.3, 0.1], 'input_std': [0.15, 0.08], ...}

# CSV 出力
bench.to_csv("my_ctrl_test.csv", field="input")
```

### 方法 B: 手動データでテスト（rosbag 不要）

```python
import numpy as np
from acsl.testing import ToolTestBench
from acsl.types.context import Result
from tools.my_controller import MyController

# テストデータを手動で作成
msgs = []
for i in range(100):
    t = i * 0.02
    msgs.append((t, "estimator", Result(state=np.array([t * 0.1, 0.0, 0.0]))))
    msgs.append((t, "reference", Result(state=np.array([1.0, 0.5, 0.0]))))

bench = ToolTestBench.from_messages(msgs)
bench.set_tool(MyController(kp=2.0))
bench.set_dt(0.02)
results = bench.run()

bench.plot("input", labels=["vx", "wz"])
bench.plot("error_norm")  # metadata のフィールドもプロット可能
```

### 方法 C: cascade チェーン全体をテスト

```python
from acsl.testing import ToolTestBench
from tools.controller.tscf_controller import TSCFController
from tools.controller.obstacle_avoid import ObstacleAvoid
from tools.controller.saturation import Saturation

bench = ToolTestBench.from_rosbag("recording.mcap")

# cascade の前段を設定
bench.set_cascade([TSCFController(), ObstacleAvoid()])

# テスト対象は最終段
bench.set_tool(Saturation(maxv=0.8, maxw=1.5), category="controller")

bench.map_topic("/odom", to_upstream="estimator")
bench.map_topic("/scan_front", to_upstream="sensor")
bench.run()
bench.plot("input")
```

## Step 3: Contract 自動生成

ロジックが確定したら、Claude Code の `/generate-contract` スキルで contract を自動生成:

```
/generate-contract tools/my_controller.py の contract を生成して
```

生成される contract:

```python
def contract(self) -> IOContract:
    return {"step": {
        "inputs": {
            "estimate": {"dtype": "ndarray", "path": "estimator"},
            "reference": {"dtype": "ndarray", "path": "reference"},
        },
        "outputs": {
            "cmd_input": {"dtype": "ndarray"},
        },
    }}
```

## Step 4: 統合

`robot_building.py` に組み込む:

```python
from tools.my_controller import MyController

# ToolCategory に追加
controller_cat = ToolCategory("controller", mode="cascade")
controller_cat.add_tool(MyController(kp=2.0, kd=0.5))
controller_cat.add_tool(ObstacleAvoid())
controller_cat.add_tool(Saturation())
controller_cat.set_cascade(["my_ctrl", "obstacle", "saturation"])
```

IntegrityChecker が contract を検証し、upstream の型不整合を起動時に検出する。

## rosbag の録画方法

```bash
# コンテナ内で録画
ros2 bag record /odom /rover_twist /scan -o my_recording

# 特定のトピックだけ
ros2 bag record /odom /slam_pose /scan_front -o slam_test
```

録画ファイルは `launcher/rosbags/` に保存される。

## トピック → upstream 自動変換

`map_topic()` で `msg_to_result` を省略すると、ROS2 メッセージ型に応じて自動変換される:

| メッセージ型 | 変換先 | state の形式 |
|---|---|---|
| `nav_msgs/Odometry` | `Result(state=[x, y, yaw])` | ndarray[3] |
| `geometry_msgs/PoseWithCovarianceStamped` | `Result(state=[x, y, yaw])` | ndarray[3] |
| `geometry_msgs/Twist` | `Result(input=[vx, wz])` | ndarray[2] |
| `sensor_msgs/LaserScan` | `Result(state=ranges, metadata={"angle_min": ...})` | ndarray[N] |

カスタム変換が必要な場合:

```python
def my_converter(msg, time):
    return Result(
        state=np.array([msg.pose.pose.position.x, msg.pose.pose.position.y]),
        timestamp=time.now,
    )

bench.map_topic("/custom_pose", to_upstream="sensor", msg_to_result=my_converter)
```
