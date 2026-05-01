# project_common

ロボット制御システムの共通フレームワーク。
ドローン・地上車両など、異なるロボットに対して統一的な制御パイプラインを提供する。

先進制御システム学研究室 (ACSL) / 東京都市大学

## 構造

```
project_common/
├── acsl/                        # Python パッケージ
│   ├── framework/               # フレームワークコア
│   ├── types/                   # 共通型定義
│   ├── tools/                   # 基本ツール群
│   └── logger/                  # ロギング
├── config/                      # 共通設定テンプレート
│   ├── exec_plans/              # 実行プラン例 (YAML)
│   ├── profiles/                # sim/exp プロファイル例
│   └── gains/                   # 制御ゲインテンプレート
└── tests/                       # テスト
```

## セットアップ

project_common は Docker ベースイメージに pip install される。
各 project_\* のコンテナ内では `from acsl.framework import ...` がそのまま使える。

```bash
# 開発・テスト時（ローカル）
cd project_common
pip install -e .
python3 -m pytest tests/ -v
```

依存: `numpy`, `pyyaml`。オプション: `scipy`, `h5py`。

## ワークスペース構成

`acsl robot 30 rf robot` で生成されるワークスペース:

```
robot/                              # ワークスペースルート
├── .acsl/                          # 運用基盤 (Docker, dup/dbuild — 隠蔽)
│
├── common/                         # project_common (参照用 — 読むだけ)
│   └── acsl/                       #   フレームワークソース
│
├── packages/                       # ROS2/Python パッケージ群
│   ├── rf/                         #   project 固有パッケージ
│   └── rplidar/                    #   acsl install で追加
│
├── tools/                          # プロジェクト固有ツール (学生が書く)
│   └── my_controller.py            #   acsl.tools.base.Tool を実装
│
├── config/                         # プロジェクト固有設定 (学生が書く)
│   ├── exec_plans/                 #   YAML ExecPlan
│   └── profiles/                   #   sim.yaml / exp.yaml
│
├── launcher/                       # コンテナ起動スクリプト
├── dockerfiles/                    # プロジェクト固有 Dockerfile
├── *.rules                         # udev ルール
└── project_launch_robot.sh         # dup 群の起動
```

**学生が触るのは `tools/` と `config/` だけ。**
`common/` はフレームワークのソースを参照するためにクローンされるが、
実際に使われるのはベースイメージに pip install された版。
`common/` を編集しても反映されないし、する必要もない。

## コンセプト

各ロボットは **Agent** として抽象化され、以下の **ToolCategory** を持つ:

| カテゴリ | 役割 | 例 |
|---|---|---|
| sensor | センサ入力 | モーキャプ, IMU, カメラ, LiDAR |
| estimator | 状態推定 | EKF, UKF, パススルー |
| reference | 目標軌道 | 位置保持, 離陸, 円軌道, ウェイポイント |
| controller | 制御則 | PID, HLC, MPC, DNN |
| input_transform | 入力変換 | 推力→スロットル |
| plant | 物理モデル/実機通信 | シミュレーションモデル, FCU通信 |

これらは **PipelineEngine** により DAG 順に実行され、
**PhaseManager** (FSM) がフェーズ毎にツールを切り替える。

```
sensor → estimator → reference → controller → input_transform → plant
         (standard パイプライン)
```

## 新しいロボットへの適用

### Step 1: ツールを作る

ワークスペースの `tools/` にロボット固有のツールを追加する。
1ツール = 1ファイル。必要なのは `name`, `contract()`, `step()` の3つだけ。

```python
# tools/my_controller.py

from acsl.types.context import StepContext, Result
from acsl.tools.base import tool_contract
import numpy as np

@tool_contract(
    inputs={
        "estimate": {"dtype": "State3D"},
        "reference": {"dtype": "State3D"},
    },
    outputs={
        "cmd_input": {"dtype": "ndarray"},
    },
)
class MyController:
    name = "my_ctrl"

    def __init__(self, gain: float = 1.0):
        self._gain = gain

    def step(self, context: StepContext):
        est = context.get_upstream("estimator")
        ref = context.get_upstream("reference")
        if est is None or ref is None:
            return None

        error = ref.state.p - est.state.p
        thrust = self._gain * error[2] + context.parameter.mass * context.parameter.gravity
        u = np.array([thrust, 0.0, 0.0, 0.0])

        return Result(input=u)
```

`common/acsl/tools/controller/pid.py` 等を参照してコピー・改変するのが最も早い。

### Step 2: ExecPlan を書く

ワークスペースの `config/exec_plans/` に YAML ファイルを作成し、
どのツールをどう組み合わせるかを宣言する。

```yaml
# config/exec_plans/my_robot.yaml

version: "2.0"
meta:
  name: "my_robot_sim"
  pipeline: standard       # standard / dnn / estimation_only / mpc_hybrid / custom

robot:
  dt: 0.025               # 制御周期 [s]
  num_agents: 1

agent:
  parameter:
    mass: 1.5
    arm_length: 0.20

  sensor:
    tools:
      direct: {class: acsl.tools.sensor.DirectSensor}
    cascade: [direct]

  estimator:
    tools:
      direct: {class: acsl.tools.estimator.DirectEstimator}
    cascade: [direct]

  reference:
    tools:
      hold: {class: acsl.tools.reference.HoldReference}
      circle:
        class: acsl.tools.reference.TimeVaryingReference
        config: {trajectory: circle, radius: 2.0, period: 15.0}

  controller:
    tools:
      my_ctrl:
        class: tools.my_controller.MyController
        config: {gain: 3.0}
    cascade: [my_ctrl]

  plant:
    tools:
      model: {class: acsl.tools.plant.ModelQuat13}
    cascade: [model]

phases:
  idle:
    transitions:
      - to: flight
        guard: {type: command, value: start}
  flight:
    allocation:
      reference: [circle]
    transitions:
      - to: idle
        guard: {type: command, value: stop}

safety:
  saturation:
    thrust_max: 20.0
    torque_max: [1.5, 1.5, 0.8]
```

ツールのクラスパス:
- `acsl.tools.*` → project_common 提供の基本ツール（ベースイメージに入っている）
- `tools.*` → ワークスペースの `tools/` にある自作ツール

### Step 3: 組み立てて動かす

```python
from acsl.framework import Orchestrator, Agent, AgentConfig, PipelineEngine
from acsl.framework import PhaseManager, ToolCategory
from acsl.types import AgentParameter

# --- Agent 構築 ---
param = AgentParameter(mass=1.5, arm_length=0.20)
agent = Agent(AgentConfig(agent_id=0, dt=0.025, parameter=param))

# ツールをカテゴリに登録
from acsl.tools.sensor import DirectSensor
from acsl.tools.estimator import DirectEstimator
from acsl.tools.reference import TimeVaryingReference
from tools.my_controller import MyController       # 自作ツール
from acsl.tools.plant import ModelQuat13

for name, tool in [
    ("sensor",     DirectSensor()),
    ("estimator",  DirectEstimator()),
    ("reference",  TimeVaryingReference(radius=2.0, period=15.0)),
    ("controller", MyController(gain=3.0)),
    ("plant",      ModelQuat13()),
]:
    cat = ToolCategory(name)
    cat.add_tool(tool)
    agent.add_category(cat)

# --- 実行 ---
orch = Orchestrator(
    agents=[agent],
    pipeline_engine=PipelineEngine("standard"),
    dt=0.025,
)
history = orch.run(steps=400)  # 10秒間のシミュレーション
```

### Step 4: 実機に切り替える

`config/profiles/exp.yaml` でセンサとプラントを差し替える:

```yaml
# config/profiles/exp.yaml
agent:
  sensor:
    tools:
      motive:
        class: acsl.tools.sensor.MotiveSensor
        config: {server_ip: "192.168.100.43"}
  plant:
    tools:
      exp:
        class: acsl.tools.plant.DroneExpModel
        config: {port: "/dev/ttyACM0"}
    cascade: [exp]
```

制御則・FSM・安全設定は一切変更不要。

## リファレンス

### パイプラインプリセット

| プリセット | 実行順序 | 用途 |
|---|---|---|
| `standard` | sensor → estimator → reference → controller → input_transform → plant | 一般的な制御 |
| `dnn` | sensor → controller → input_transform → plant | End-to-End学習 |
| `estimation_only` | sensor → estimator | キャリブレーション・デバッグ |
| `mpc_hybrid` | sensor → estimator → [reference, mpc_async] → controller → plant | MPC併用 |
| `custom` | YAML/Python で DAG 定義 | 上級者向け |

### cascade / parallel

同一カテゴリ内で複数ツールを使う場合:

```yaml
estimator:
  tools:
    ekf: {class: acsl.tools.estimator.EKF}
    loadstate: {class: acsl.tools.estimator.LoadStateManager}
  cascade: [ekf, loadstate]     # この順で実行
```

### フェーズ管理 (FSM)

飛行フェーズ毎に使うツールを切り替える（MATLAB `cha_allocation` の後継）:

```yaml
phases:
  takeoff:
    allocation:
      reference: [takeoff]       # 離陸中は takeoff 参照を使う
    transitions:
      - to: flight
        guard: {type: altitude_reached, target: 1.0}
  flight:
    allocation:
      reference: [circle]        # 飛行中は circle 参照に切替
```

### マルチエージェント

複数ロボットは Orchestrator に Agent を追加するだけ。
エージェント間通信は **Blackboard**（ダブルバッファ方式）で行う。

```python
for i in range(4):
    drone = Agent(AgentConfig(agent_id=i, parameter=param))
    # ... ツール登録 ...
    orch.add_agent(drone)

# Blackboard 経由で他エージェントの状態を読む
other_state = context.get_agent_state(agent_id=0)
```

### 安全機構

3層構造。**サチュレーション閾値の設定は必須**（デフォルトなし、未設定はエラー）。

1. **入力サチュレーション** — 推力・トルクのクリッピング + 変化率制限
2. **ウォッチドッグ** — 通信タイムアウト、推定値staleness 検知
3. **フェイルセーフ** — 異常検知時に Pixhawk の Land/RTL モードを発行

## 設計ドキュメント

フレームワークの設計経緯は `docs/` (リポジトリルート) に記録:

| ファイル | 内容 |
|---|---|
| `docs/phase1/T1_matlab_analysis.md` | MATLAB構造解析 |
| `docs/phase1/T2_python_ros2_analysis.md` | Python/ROS2構造解析 |
| `docs/phase1/T3_requirements.md` | 要件定義 (MoSCoW分類) |
| `docs/phase2/T4_architecture_design.md` | アーキテクチャ設計書 |
| `docs/phase2/T5_poc_report.md` | PoC検証レポート |
| `docs/phase3/T5_test_plan.md` | テスト計画書 |
| `docs/phase3/T6_migration_guide.md` | 既存システムからの移行ガイド |
