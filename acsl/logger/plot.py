"""plot — Logger 可視化ユーティリティ（phase 背景色・3Dアニメーション）

phase 毎の色は TABLEAU_COLORS から自動割当。
個別に指定したい場合は PHASE_COLORS 辞書に設定:

    from acsl.logger.plot import PHASE_COLORS
    PHASE_COLORS["takeoff"] = "#aaffaa"
    PHASE_COLORS["flight"]  = "#aaaaff"
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

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


# ---------------------------------------------------------------------------
# 3D trajectory animation
# ---------------------------------------------------------------------------

def animate_trajectory(
    logger: Logger,
    zup: bool = True,
    speed: float = 1.0,
    draw_body_fn: Optional[Callable] = None,
    save_path: Optional[str] = None,
):
    """3D 軌跡アニメーション。

    Parameters
    ----------
    logger : Logger
    zup : bool
        True なら z-up (ENU)、False なら -z を altitude として描画。
    speed : float
        再生速度倍率。
    draw_body_fn : callable(ax, pos_xyz, quat_wxyz, size) -> list[Artist], optional
        機体形状を描画するコールバック。省略時は点のみ。
    save_path : str, optional
        指定時は MP4/GIF に保存。None なら plt.show()。
    """
    t = logger.query("t")
    pos = logger.query("p", "e")
    ref = logger.query("p", "r")
    quat = logger.query("q", "e")
    phases = logger.query("phase")

    if not pos.size:
        print("No position data to animate.")
        return

    z_sign = 1.0 if zup else -1.0
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.02
    # 30fps 相当にダウンサンプル
    step = max(1, int(1.0 / 30.0 / dt / speed))
    indices = list(range(0, len(t), step))
    if indices[-1] != len(t) - 1:
        indices.append(len(t) - 1)
    interval_ms = 1000.0 / 30.0

    phase_names, _ = get_phase_spans(logger)
    palette = get_phase_palette(phase_names)

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    # 軸範囲を事前計算
    margin = 0.3
    x_range = [np.nanmin(pos[:, 0]) - margin, np.nanmax(pos[:, 0]) + margin]
    y_range = [np.nanmin(pos[:, 1]) - margin, np.nanmax(pos[:, 1]) + margin]
    z_vals = z_sign * pos[:, 2]
    z_range = [np.nanmin(z_vals) - margin, np.nanmax(z_vals) + margin]

    # reference 軌跡（静的）
    if ref.size:
        ax.plot3D(ref[:, 0], ref[:, 1], z_sign * ref[:, 2],
                  "r--", alpha=0.3, label="reference")

    trail_line, = ax.plot3D([], [], [], "b-", alpha=0.6, linewidth=1)
    marker, = ax.plot3D([], [], [], "ko", markersize=6)
    time_text = ax.text2D(0.02, 0.95, "", transform=ax.transAxes, fontsize=11)
    phase_text = ax.text2D(0.02, 0.90, "", transform=ax.transAxes, fontsize=10)
    body_artists = []

    def init():
        ax.set_xlim(*x_range)
        ax.set_ylim(*y_range)
        ax.set_zlim(*z_range)
        ax.set_xlabel("x [m]")
        ax.set_ylabel("y [m]")
        ax.set_zlabel("altitude [m]")
        trail_line.set_data_3d([], [], [])
        marker.set_data_3d([], [], [])
        time_text.set_text("")
        phase_text.set_text("")
        return [trail_line, marker, time_text, phase_text]

    def update(frame_idx):
        nonlocal body_artists
        k = indices[frame_idx]
        # trail
        trail_line.set_data_3d(
            pos[:k + 1, 0], pos[:k + 1, 1], z_sign * pos[:k + 1, 2])
        # current position
        cx, cy, cz = pos[k, 0], pos[k, 1], z_sign * pos[k, 2]
        marker.set_data_3d([cx], [cy], [cz])
        # phase color for marker
        if len(phases):
            phase = phases[k]
            color = palette.get(phase, "black")
            marker.set_color(color)
            phase_text.set_text(phase)
            phase_text.set_color(color)
        time_text.set_text(f"t = {t[k]:.2f} s")
        # body drawing
        for a in body_artists:
            a.remove()
        body_artists = []
        if draw_body_fn is not None and quat.size:
            q = quat[k]
            if not np.any(np.isnan(q)):
                p = np.array([cx, cy, cz])
                body_artists = draw_body_fn(ax, p, q, z_sign) or []
        return [trail_line, marker, time_text, phase_text] + body_artists

    anim = FuncAnimation(
        fig, update, init_func=init,
        frames=len(indices), interval=interval_ms, blit=False)

    if save_path:
        anim.save(save_path, fps=30, dpi=100)
        print(f"Saved: {save_path}")
    else:
        plt.show()
