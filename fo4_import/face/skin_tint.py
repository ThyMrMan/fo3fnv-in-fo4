"""Fallout 4's skin tint: a skin-tint part (body, rear head) is drawn as the soft light of its texture with the skin
tint (QNAM), both in gamma space, as the lighting shader blends them; a tint of 0.5 leaves the texture as it is. The
CK bakes the skin tone into a face the same way, over the face set's untinted diffuse.

See: docs/fork/fo4_look_races_plan.md#skin-tint
"""

import numpy as np


def tinted(texture, tint) -> np.ndarray:
    """`texture` (0..255) as drawn under skin tint `tint` (0..1 per channel), 0..255."""
    b, t = np.asarray(texture, float) / 255, np.asarray(tint, float)
    low = 2 * b * t + b * b * (1 - 2 * t)
    high = 2 * b * (1 - t) + np.sqrt(b) * (2 * t - 1)
    return np.where(t < 0.5, low, high) * 255


def untinted(drawn, tint) -> np.ndarray:
    """The texture (0..255) that tinted() draws as `drawn` (0..255) under `tint`: the soft light solved for it."""
    d = np.clip(np.asarray(drawn, float) / 255, 0, None)
    t = np.broadcast_to(np.asarray(tint, float), d.shape)
    low = t < 0.5
    a, k = np.where(low, 1 - 2 * t, 2 * (1 - t)), np.where(low, 2 * t, 2 * t - 1)
    flat = a < 1e-9
    root = np.where(flat, d / np.where(flat, np.maximum(k, 1e-9), 1),
                    (-k + np.sqrt(k * k + 4 * a * d)) / np.where(flat, 1, 2 * a))
    return np.clip(np.where(low, root, root * root), 0, 1) * 255


def tint_for(drawn, texture) -> np.ndarray:
    """Per channel, the skin tint (0..1) under which `texture` (0..255) is drawn as `drawn` (0..255)."""
    b, d = np.asarray(texture, float) / 255, np.asarray(drawn, float) / 255
    root = np.sqrt(b)
    low = (d - b * b) / np.maximum(2 * (b - b * b), 1e-9)
    high = (d - 2 * b + root) / np.maximum(2 * (root - b), 1e-9)
    return np.clip(np.where(d < b, low, high), 0, 1)
