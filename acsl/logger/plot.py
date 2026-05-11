"""plot — Logger 可視化ユーティリティ（phase 背景色など）

phase 毎の色は TABLEAU_COLORS から自動割当。
個別に指定したい場合は PHASE_COLORS 辞書に設定:

    from acsl.logger.plot import PHASE_COLORS
    PHASE_COLORS["takeoff"] = "#aaffaa"
    PHASE_COLORS["flight"]  = "#aaaaff"
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import matplotlib.colors as mcolors

from acsl.logger.logger import Logger

PHASE_COLORS: Dict[str, str] = {}


def get_phase_palette(phase_names: List[str]) -> Dict[str, str]:
    """phase名 → 背景色の辞書を返す。PHASE_COLORS の指定を優先。"""
    base = list(mcolors.TABLEAU_COLORS.values())
    palette = {}
    auto_idx = 0
    for name in phase_names:
        if name in PHASE_COLORS:
            palette[name] = PHASE_COLORS[name]
        else:
            palette[name] = base[auto_idx % len(base)]
            auto_idx += 1
    return palette


def get_phase_spans(
    logger: Logger,
) -> Tuple[List[str], List[Tuple[float, float, str]]]:
    """phase の切り替わり区間を (t_start, t_end, phase_name) のリストで返す。"""
    t = logger.query("t")
    phases = logger.query("phase")
    if not len(phases) or not len(t):
        return [], []
    spans: List[Tuple[float, float, str]] = []
    phase_names_ordered: List[str] = []
    cur = phases[0]
    start = t[0]
    for k in range(1, len(phases)):
        if phases[k] != cur:
            spans.append((start, t[k], cur))
            if cur not in phase_names_ordered:
                phase_names_ordered.append(cur)
            cur = phases[k]
            start = t[k]
    spans.append((start, t[-1], cur))
    if cur not in phase_names_ordered:
        phase_names_ordered.append(cur)
    return phase_names_ordered, spans


def shade_phases(
    logger: Logger,
    axes,
    palette: Optional[Dict[str, str]] = None,
    alpha: float = 0.08,
):
    """axes（単体または配列）に phase 毎の背景色を付ける。"""
    phase_names, spans = get_phase_spans(logger)
    if not spans:
        return
    if palette is None:
        palette = get_phase_palette(phase_names)
    if not isinstance(axes, (list, np.ndarray)):
        axes = [axes]
    for ax in axes:
        for t0, t1, name in spans:
            ax.axvspan(t0, t1, alpha=alpha, color=palette.get(name, "gray"))
