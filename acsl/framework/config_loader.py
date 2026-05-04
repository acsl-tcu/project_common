"""YAML config loader with profile overlay and Agent/PhaseManager builder."""

from __future__ import annotations
import copy
import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)


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


def _load_class(class_path: str) -> Optional[Type]:
    """'module.path.ClassName' から Class を import する。"""
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except Exception as e:
        logger.warning(f"Failed to load class '{class_path}': {e}")
        return None


# --- Guard 関数レジストリ ---

_GUARD_REGISTRY: Dict[str, Callable] = {}


def register_guard(name: str, fn: Callable):
    """guard 関数を名前で登録する。YAML の guard.type で参照。"""
    _GUARD_REGISTRY[name] = fn


def _build_guard(guard_spec: Dict) -> Callable:
    """YAML の guard 定義から guard 関数を生成する。"""
    guard_type = guard_spec.get("type", "")

    if guard_type in _GUARD_REGISTRY:
        return _GUARD_REGISTRY[guard_type]

    if guard_type == "command":
        value = guard_spec.get("value", "")
        return lambda ctx: ctx.config.get("command") == value

    if guard_type == "always":
        return lambda ctx: True

    logger.warning(f"Unknown guard type '{guard_type}', using always-false")
    return lambda ctx: False


class ConfigLoader:
    def __init__(self):
        self._config: Dict[str, Any] = {}

    def load(self, config_path: str, profile: Optional[str] = None) -> Dict[str, Any]:
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required: pip install pyyaml")

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

    def load_dict(self, config: Dict, profile_overlay: Optional[Dict] = None) -> Dict:
        self._config = copy.deepcopy(config)
        if profile_overlay:
            self._config = _deep_merge(self._config, profile_overlay)
        return self._config

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    # --- Agent 構築 ---

    def build_agent(self, config: Optional[Dict] = None):
        """YAML config から Agent + ToolCategory を構築する。

        config 構成:
          robot:
            dt: 0.025
          agent:
            parameter: {mass: 1.0, ...}
            sensor:
              tools:
                direct: {class: acsl.tools.sensor.DirectSensor, config: {}}
              cascade: [direct]
            estimator: ...
            controller: ...
        """
        from acsl.framework.agent import Agent, AgentConfig
        from acsl.framework.tool_category import ToolCategory
        from acsl.types.parameter import AgentParameter

        cfg = config or self._config
        robot_cfg = cfg.get("robot", {})
        agent_cfg = cfg.get("agent", {})

        dt = float(robot_cfg.get("dt", 0.025))
        param_cfg = agent_cfg.get("parameter", {})
        param = AgentParameter(
            mass=float(param_cfg.get("mass", 1.0)),
            gravity=float(param_cfg.get("gravity", 9.81)),
            arm_length=float(param_cfg.get("arm_length", 0.17)),
        )

        agent = Agent(AgentConfig(agent_id=0, dt=dt, parameter=param))

        categories = ["sensor", "estimator", "reference", "controller",
                       "input_transform", "plant"]

        for cat_name in categories:
            cat_cfg = agent_cfg.get(cat_name)
            if not cat_cfg:
                continue

            tools_cfg = cat_cfg.get("tools", {})
            cascade = cat_cfg.get("cascade", [])
            mode = "cascade" if len(cascade) > 1 or cat_cfg.get("mode") == "parallel" else "cascade"

            category = ToolCategory(cat_name, mode=cat_cfg.get("mode", "cascade"))

            for tool_name, tool_spec in tools_cfg.items():
                if isinstance(tool_spec, str):
                    tool_spec = {"class": tool_spec}
                class_path = tool_spec.get("class", "")
                tool_cls = _load_class(class_path)
                if tool_cls is None:
                    logger.warning(f"Skipping tool '{tool_name}': class '{class_path}' not found")
                    continue
                tool_config = tool_spec.get("config", {})
                try:
                    tool = tool_cls(**tool_config) if tool_config else tool_cls()
                except Exception as e:
                    logger.warning(f"Failed to instantiate '{tool_name}': {e}")
                    continue

                if not hasattr(tool, 'name'):
                    tool.name = tool_name
                category.add_tool(tool)

            if cascade:
                try:
                    category.set_cascade(cascade)
                except ValueError as e:
                    logger.warning(f"cascade error in '{cat_name}': {e}")

            agent.add_category(category)

        return agent, dt

    # --- PhaseManager 構築 ---

    def build_phase_manager(self, config: Optional[Dict] = None):
        """YAML config の phases セクションから PhaseManager を構築する。

        config 構成:
          phases:
            idle:
              transitions:
                - to: arm
                  guard: {type: command, value: arm}
            arm:
              allocation:
                reference: [hold]
              transitions:
                - to: takeoff
                  guard: {type: command, value: takeoff}
        """
        from acsl.framework.phase_manager import (
            PhaseManager, PhaseTransition, PhaseConfig, PhaseAllocation,
        )

        cfg = config or self._config
        phases_cfg = cfg.get("phases", {})

        if not phases_cfg:
            return None

        pm = PhaseManager()

        for phase_name, phase_spec in phases_cfg.items():
            if not isinstance(phase_spec, dict):
                pm.add_phase(phase_name)
                continue

            alloc = None
            alloc_cfg = phase_spec.get("allocation")
            if alloc_cfg and isinstance(alloc_cfg, dict):
                alloc = PhaseAllocation(**{
                    k: v for k, v in alloc_cfg.items()
                    if k in PhaseAllocation.__dataclass_fields__
                })

            pm.add_phase(phase_name, PhaseConfig(allocation=alloc))

        # 遷移定義
        first_phase = None
        for phase_name, phase_spec in phases_cfg.items():
            if first_phase is None:
                first_phase = phase_name
            if not isinstance(phase_spec, dict):
                continue

            transitions = phase_spec.get("transitions", [])
            for i, tr in enumerate(transitions):
                to_phase = tr.get("to", "")
                guard_spec = tr.get("guard", {"type": "always"})
                priority = int(tr.get("priority", 0))
                description = tr.get("description", f"{phase_name}->{to_phase}")

                guard_fn = _build_guard(guard_spec)

                pm.add_transition(PhaseTransition(
                    from_phase=phase_name,
                    to_phase=to_phase,
                    guard=guard_fn,
                    priority=priority,
                    description=description,
                ))

        if first_phase:
            pm.set_initial(first_phase)

        return pm

    # --- 一括構築 ---

    def build_all(self, config: Optional[Dict] = None):
        """YAML config から Agent + PhaseManager + Orchestrator を一括構築する。

        Returns:
            (orchestrator, agent, phase_manager)
        """
        from acsl.framework.orchestrator import Orchestrator
        from acsl.framework.pipeline_engine import PipelineEngine

        cfg = config or self._config
        agent, dt = self.build_agent(cfg)
        pm = self.build_phase_manager(cfg)

        meta = cfg.get("meta", {})
        pipeline_preset = meta.get("pipeline", "standard")

        orch = Orchestrator(
            agents=[agent],
            pipeline_engine=PipelineEngine(pipeline_preset),
            phase_manager=pm,
            dt=dt,
        )

        return orch, agent, pm

    # --- diff ---

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
