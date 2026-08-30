"""CPU mirror of the StaticRain droplet field (exact float32 arithmetic).

Reproduces the GPU hash field bit-for-close in IEEE float32 so the launcher and
tests can report/prove the final droplet counts and diameters that the shader
will render. Same formulas, same operation order, np.float32 throughout.

Field model (must stay in sync with shaders/StaticRain.frag):
   GRID / D_MIN / D_MAX / DENS      — per-layer quota (layer 0..3 = micro..large)
   hash11 / hash21                  — stable hashes
   vnoise / cluster_mask            — low-frequency wet/dry spatial modulation
                                      (dry regions + sparse regions + small
                                      clusters, NOT uniform coverage)
   presence:  hash11(idx) < DENS[layer] * cluster_mask(centre)
   diameter:  mix(D_MIN, D_MAX, hash11(h * 53.1))   (nominal; debug rings)
   aspect:    per-layer height/width, 0.88-1.26 (medium slightly stretched)
   wobble:    rendering-only boundary variation, amp <= 6.2% (no metaball)
"""

from __future__ import annotations

import numpy as np

WIDTH = 1440
HEIGHT = 900

GRID = np.array([9.0, 22.0, 60.0, 180.0], dtype=np.float32)
D_MIN = np.array([1.5, 4.0, 8.0, 15.0], dtype=np.float32)
D_MAX = np.array([4.0, 8.0, 15.0, 25.0], dtype=np.float32)
# Global per-cell presence weights (before cluster mask). u_density=1.0.
DENS = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)  # set by _set_dens()
# Tuned values (see tune_dens() history); kept in one place on purpose.
# Iteration 3: high-contrast cluster_mask. Mirrors DENS in StaticRain.frag.
# micro ~431, small ~100, medium ~22, large ~3, total ~556 (target 500-600).
DENS_TUNED = np.array([0.0581, 0.0866, 0.1341, 0.1356], dtype=np.float32)
DENS[:] = DENS_TUNED

# Boundary wobble (rendering only; shape, not count/diameter stats).
# r_eff = radius * (1 + WOB_AMP1*cos(2*angle+phase) + WOB_AMP2*cos(3*angle+1.7*phase))
WOB_AMP1 = 0.040
WOB_AMP2 = 0.022

# Acceptance quota (user review, iteration 2)
QUOTA = {
    "micro": (300, 500),
    "small": (70, 120),
    "medium": (12, 25),
    "large": (1, 3),
    "total_max": 800,
    "diameter_max": 30.0,
}
LAYER_NAMES = ("micro", "small", "medium", "large")


def _fract(x: np.ndarray) -> np.ndarray:
    return (x - np.floor(x)).astype(np.float32)


def hash11(p: np.ndarray) -> np.ndarray:
    p = _fract(p * np.float32(0.1031))
    p = (p * (p + np.float32(33.33))).astype(np.float32)
    p = (p * (p + p)).astype(np.float32)
    return _fract(p)


def hash21(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """GLSL vec2 hash21 — returns (x, y) components, float32 throughout."""
    x = _fract(p * np.float32(0.1031))
    y = _fract(p * np.float32(0.1030))
    z = _fract(p * np.float32(0.0973))
    # p3 += dot(p3, p3.yzx + 33.33)
    d = (x * (y + np.float32(33.33))
         + y * (z + np.float32(33.33))
         + z * (x + np.float32(33.33))).astype(np.float32)
    x = (x + d).astype(np.float32)
    y = (y + d).astype(np.float32)
    z = (z + d).astype(np.float32)
    # fract((p3.xx + p3.yz) * p3.zy) => vec2((x+y)*z, (x+z)*y)
    rx = _fract((x + y) * z)
    ry = _fract((x + z) * y)
    return rx, ry


def vnoise(p: np.ndarray) -> np.ndarray:
    """Bilinear value noise; p: (N, 2) float32."""
    i = np.floor(p).astype(np.float32)
    f = (p - i).astype(np.float32)
    u = (f * f * (np.float32(3.0) - np.float32(2.0) * f)).astype(np.float32)

    def h(ix: np.ndarray, iy: np.ndarray) -> np.ndarray:
        return hash11(ix * np.float32(127.1) + iy * np.float32(311.7))

    a = h(i[:, 0], i[:, 1])
    b = h(i[:, 0] + np.float32(1.0), i[:, 1])
    c = h(i[:, 0], i[:, 1] + np.float32(1.0))
    d = h(i[:, 0] + np.float32(1.0), i[:, 1] + np.float32(1.0))
    ab = (a + (b - a) * u[:, 0]).astype(np.float32)
    cd = (c + (d - c) * u[:, 0]).astype(np.float32)
    return (ab + (cd - ab) * u[:, 1]).astype(np.float32)


def cluster_mask(p: np.ndarray) -> np.ndarray:
    """Low-frequency wet/dry modulation, 0..1, evaluated at droplet centres.

    High contrast: sharp smoothstep creates dry regions, sparse regions and
    small clusters. Synced 1:1 with clusterMask() in shaders/StaticRain.frag.
    """
    n = (np.float32(0.52) * vnoise(p * np.float32(0.0038))
         + np.float32(0.30) * vnoise(p * np.float32(0.0105) + np.float32([37.2, 91.5]))
         + np.float32(0.18) * vnoise(p * np.float32(0.0240) + np.float32([11.7, 45.3])))
    t = np.clip((n - np.float32(0.28)) / np.float32(0.44), np.float32(0.0), np.float32(1.0)).astype(np.float32)
    return (t * t * (np.float32(3.0) - np.float32(2.0) * t)).astype(np.float32)


def _aspect(layer: int, seed: np.ndarray) -> np.ndarray:
    """Per-droplet aspect (height/width). Synced with aspectOf() in the shader."""
    if layer == 0:
        return (np.float32(0.92) + seed * np.float32(0.16)).astype(np.float32)
    if layer == 1:
        return (np.float32(0.88) + seed * np.float32(0.24)).astype(np.float32)
    if layer == 2:
        return (np.float32(0.94) + seed * np.float32(0.32)).astype(np.float32)
    return (np.float32(0.95) + seed * np.float32(0.20)).astype(np.float32)


def compute_field(width: int = WIDTH, height: int = HEIGHT,
                  dens: np.ndarray | None = None) -> dict:
    """Enumerate every droplet the shader would render (incl. edge-clipped)."""
    dens = DENS if dens is None else np.asarray(dens, dtype=np.float32)
    per_layer = []
    for layer in range(4):
        cell = float(GRID[layer])
        max_influence = float(D_MAX[layer]) * 0.5 * 1.15
        idx_x = np.arange(np.int32(-2), np.int32(np.ceil(width / cell)) + 2, dtype=np.float32)
        idx_y = np.arange(np.int32(-2), np.int32(np.ceil(height / cell)) + 2, dtype=np.float32)
        ix, iy = np.meshgrid(idx_x, idx_y, indexing="xy")
        ix = ix.ravel()
        iy = iy.ravel()

        h = hash11(ix * np.float32(127.1) + iy * np.float32(311.7)
                   + np.float32(layer) * np.float32(57.31))
        rnd_x, rnd_y = hash21(h * np.float32(913.7) + np.float32(layer) * np.float32(57.31))
        cx = (cell * (ix + np.float32(0.5) + (rnd_x - np.float32(0.5)) * np.float32(0.5))).astype(np.float32)
        cy = (cell * (iy + np.float32(0.5) + (rnd_y - np.float32(0.5)) * np.float32(0.5))).astype(np.float32)

        # visible if the lens influence can touch the frame
        on_screen = ((cx > -max_influence) & (cx < width + max_influence)
                     & (cy > -max_influence) & (cy < height + max_influence))
        h = h[on_screen]
        cx = cx[on_screen]
        cy = cy[on_screen]

        # presence: h < DENS[layer] * cluster_mask(centre)  (mask clamped 0..1)
        cl = cluster_mask(np.stack([cx, cy], axis=1))
        present = h < (dens[layer] * cl)
        h = h[present]
        cx = cx[present]
        cy = cy[present]
        cl = cl[present]

        diameter = (D_MIN[layer] + (D_MAX[layer] - D_MIN[layer])
                    * hash11(h * np.float32(53.1))).astype(np.float32)
        aspect = _aspect(layer, hash11(h * np.float32(191.3) + np.float32(layer) * np.float32(13.7)))
        per_layer.append({
            "count": int(h.size),
            "cx": cx, "cy": cy,
            "diameter": diameter,
            "aspect": aspect,
        })
    return per_layer


def summarize(per_layer: list[dict]) -> dict:
    counts = {LAYER_NAMES[i]: per_layer[i]["count"] for i in range(4)}
    diams = np.concatenate([per_layer[i]["diameter"] for i in range(4)])
    return {
        **counts,
        "total": sum(counts.values()),
        "diameter_min": float(diams.min()) if diams.size else 0.0,
        "diameter_max": float(diams.max()) if diams.size else 0.0,
        "diameter_mean": float(diams.mean()) if diams.size else 0.0,
    }


def check_quota(stats: dict) -> list[str]:
    """Return a list of violations (empty = acceptance passed)."""
    out = []
    for name in LAYER_NAMES:
        lo, hi = QUOTA[name]
        if not (lo <= stats[name] <= hi):
            out.append(f"{name}: {stats[name]} outside [{lo}, {hi}]")
    if stats["total"] > QUOTA["total_max"]:
        out.append(f"total: {stats['total']} > {QUOTA['total_max']}")
    if stats["diameter_max"] > QUOTA["diameter_max"]:
        out.append(f"diameter_max: {stats['diameter_max']:.2f} > {QUOTA['diameter_max']}")
    return out


def tune_dens(targets: tuple[float, ...] = (400.0, 95.0, 18.0, 2.0),
              iters: int = 4) -> np.ndarray:
    """Iterate DENS toward target counts (mask is independent of DENS)."""
    dens = DENS_TUNED.copy()
    last = None
    for _ in range(iters):
        stats = summarize(compute_field(dens=dens))
        last = stats
        for i, name in enumerate(LAYER_NAMES):
            target = targets[i]
            cur = stats[name]
            if cur > 0:
                dens[i] = np.float32(float(dens[i]) * target / cur)
    return dens
