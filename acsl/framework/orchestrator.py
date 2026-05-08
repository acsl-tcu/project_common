from __future__ import annotations
from dataclasses import field
from typing import Any, Callable, Dict, List, Optional
import selectors
import socket
import threading
import time as time_mod

from acsl.framework.agent import Agent
from acsl.framework.pipeline_engine import PipelineEngine
from acsl.framework.phase_manager import PhaseManager
from acsl.framework.blackboard import Blackboard
from acsl.framework.safety_monitor import SafetyMonitor
from acsl.types.context import StepContext, Time, Result
from acsl.types.safety import SafetyConfig, SafetyAlert


class Orchestrator:
    """制御システム全体を俯瞰する統括クラス。

    2つの実行モードをサポート:

    sync (デフォルト):
        Orchestrator が PipelineEngine で全ツールを順次実行する。
        シミュレーションやテストで使用。
        呼び出し: orchestrator.step()

    async:
        各ツールは外部（ROS2 タイマー等）で独立に実行される。
        Orchestrator はフェーズ管理・安全監視・ログ・Blackboard 同期のみ行う。
        呼び出し: orchestrator.monitor()

    どちらのモードでも以下の機能を提供:
        - PhaseManager による状態遷移とツール切替
        - SafetyMonitor による入力サチュレーション・ウォッチドッグ
        - Blackboard によるマルチエージェント通信
        - Contract 検証（IntegrityChecker 経由）
        - 統一ログ収集
    """

    def __init__(
        self,
        agents: Optional[List[Agent]] = None,
        pipeline_engine: Optional[PipelineEngine] = None,
        phase_manager: Optional[PhaseManager] = None,
        blackboard: Optional[Blackboard] = None,
        safety_monitor: Optional[SafetyMonitor] = None,
        dt: float = 0.025,
        mode: str = "sync",
        console_port: int = 0,
        console_handler: Optional[Any] = None,
    ):
        self.agents: List[Agent] = agents or []
        self.pipeline_engine = pipeline_engine or PipelineEngine("standard")
        self.phase_manager = phase_manager or PhaseManager()
        self.blackboard = blackboard or Blackboard()
        self.safety_monitor = safety_monitor
        self.mode = mode
        self._dt = dt
        self._time = 0.0
        self._step_count = 0
        self._log: List[Dict[str, Any]] = []
        self._console_handler = console_handler
        self._console_srv = None

        if console_port > 0:
            self._start_console_server(console_port)

    def add_agent(self, agent: Agent) -> None:
        self.agents.append(agent)

    # ---- sync mode: Orchestrator が実行を駆動 ----

    def step(self) -> StepContext:
        """sync モード: 全ツールを順次実行し、俯瞰処理も行う。"""
        context = self._advance_time()

        # 1. フェーズ評価
        self._evaluate_phase(context)

        # 2. 全エージェントのパイプライン実行
        for i, agent in enumerate(self.agents):
            agent_ctx = StepContext(
                time=context.time,
                phase=context.phase,
                agent_index=i,
                agent_states=context.agent_states,
                parameter=agent.config.parameter,
            )
            self.pipeline_engine.execute_step(agent, agent_ctx)
            state = agent.update_state_snapshot(agent_ctx)
            self.blackboard.write(i, state)
            # パイプライン結果を親 context に反映
            context.results.update(agent_ctx.results)

        # 3. 安全チェック
        self._check_safety(context)

        # 4. Blackboard 同期
        self.blackboard.swap()

        return context

    def run(self, steps: int) -> List[StepContext]:
        """sync モード: 複数ステップを実行。"""
        history = []
        for _ in range(steps):
            ctx = self.step()
            history.append(ctx)
        return history

    # ---- async mode: 外部が実行、Orchestrator は俯瞰のみ ----

    def monitor(self) -> StepContext:
        """async モード: ツール実行は行わず、俯瞰処理のみ。

        各ツールは ROS2 タイマー等で独立に実行されている前提。
        Agent の state snapshot は外部から update_state_snapshot() で更新される。
        """
        context = self._advance_time()

        # 1. フェーズ評価
        self._evaluate_phase(context)

        # 2. 各エージェントの最新状態を Blackboard に反映
        for i, agent in enumerate(self.agents):
            state = agent.get_state_snapshot()
            self.blackboard.write(i, state)

        # 3. 安全チェック
        self._check_safety(context)

        # 4. Blackboard 同期
        self.blackboard.swap()

        return context

    # ---- 共通の内部メソッド ----

    def _advance_time(self) -> StepContext:
        self._time += self._dt
        self._step_count += 1
        wall_time = time_mod.time()
        time = Time(now=self._time, dt=self._dt, step_count=self._step_count, wall_time=wall_time)
        context = StepContext(time=time, phase=self.phase_manager.current_phase)
        context.agent_states = {k: v for k, v in self.blackboard.read_all().items()}
        return context

    def _evaluate_phase(self, context: StepContext) -> None:
        new_phase = self.phase_manager.evaluate(context)
        if new_phase:
            allocation = self.phase_manager.transition(new_phase, context)
            context.phase = new_phase
            for agent in self.agents:
                agent.apply_allocation(allocation)

    def _check_safety(self, context: StepContext) -> None:
        if self.safety_monitor:
            alerts = self.safety_monitor.check(context)
            if self.safety_monitor.has_critical(alerts):
                self.phase_manager.force_transition("emergency", context)

    @property
    def time(self) -> float:
        return self._time

    @property
    def step_count(self) -> int:
        return self._step_count

    # ---- TCP console server ----

    def _start_console_server(self, port: int):
        """バックグラウンドで TCP ソケットサーバーを起動。"""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", port))
        srv.listen(2)
        srv.setblocking(False)
        self._console_srv = srv
        t = threading.Thread(target=self._console_loop, daemon=True)
        t.start()

    def _console_loop(self):
        sel = selectors.DefaultSelector()
        sel.register(self._console_srv, selectors.EVENT_READ)
        while True:
            events = sel.select(timeout=1.0)
            for key, _ in events:
                if key.fileobj is self._console_srv:
                    conn, _ = self._console_srv.accept()
                    sel.register(conn, selectors.EVENT_READ)
                else:
                    conn = key.fileobj
                    try:
                        data = conn.recv(1024)
                        if data:
                            cmd = data.decode().strip()
                            resp = self._handle_console(cmd)
                            conn.sendall((resp + "\n").encode())
                        else:
                            sel.unregister(conn)
                            conn.close()
                    except Exception:
                        sel.unregister(conn)
                        conn.close()

    def _handle_console(self, cmd: str) -> str:
        """console コマンド処理。console_handler があれば委譲。"""
        if self._console_handler:
            return self._console_handler(cmd)
        return f"OK {cmd}"

    def __repr__(self) -> str:
        return f"Orchestrator(mode={self.mode}, agents={len(self.agents)}, phase={self.phase_manager.current_phase})"
