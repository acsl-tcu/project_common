from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class State3D:
    p: np.ndarray = field(default_factory=lambda: np.zeros(3))
    v: np.ndarray = field(default_factory=lambda: np.zeros(3))
    q: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    w: np.ndarray = field(default_factory=lambda: np.zeros(3))

    @property
    def euler(self) -> np.ndarray:
        try:
            from scipy.spatial.transform import Rotation
            return Rotation.from_quat([self.q[1], self.q[2], self.q[3], self.q[0]]).as_euler('xyz')
        except Exception:
            phi = np.arctan2(2*(self.q[0]*self.q[1]+self.q[2]*self.q[3]), 1-2*(self.q[1]**2+self.q[2]**2))
            theta = np.arcsin(np.clip(2*(self.q[0]*self.q[2]-self.q[3]*self.q[1]), -1, 1))
            psi = np.arctan2(2*(self.q[0]*self.q[3]+self.q[1]*self.q[2]), 1-2*(self.q[2]**2+self.q[3]**2))
            return np.array([phi, theta, psi])

    @property
    def rotation_matrix(self) -> np.ndarray:
        try:
            from scipy.spatial.transform import Rotation
            return Rotation.from_quat([self.q[1], self.q[2], self.q[3], self.q[0]]).as_matrix()
        except Exception:
            w, x, y, z = self.q
            return np.array([
                [1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)],
            ])

    @property
    def xd(self) -> np.ndarray:
        yaw = self.euler[2]
        xd = np.zeros(20)
        xd[0:3] = self.p
        xd[3] = yaw
        xd[4:7] = self.v
        return xd

    def copy(self) -> State3D:
        return State3D(p=self.p.copy(), v=self.v.copy(), q=self.q.copy(), w=self.w.copy())


@dataclass
class State2D:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    wz: float = 0.0
