###############################################################################
# Name: calibration_transform.py
# Uses: Pure 2D affine-transform fitting and residual interpolation helpers
#       used by the manual calibration workflow. No I/O or shared state.
# Date: 2026-05-31
###############################################################################

import math


EPSILON = 1e-9


def _apply_transform(transform, xValue, yValue):
    return (
        transform["a"] * xValue + transform["b"] * yValue + transform["c"],
        transform["d"] * xValue + transform["e"] * yValue + transform["f"],
    )


def _translation_transform(pair):
    sourceX, sourceY, targetX, targetY = pair
    return {
        "a": 1.0,
        "b": 0.0,
        "c": targetX - sourceX,
        "d": 0.0,
        "e": 1.0,
        "f": targetY - sourceY,
    }


def _rigid_transform(pairs):
    if len(pairs) < 2:
        return None

    count = float(len(pairs))
    sourceCenterX = sum(pair[0] for pair in pairs) / count
    sourceCenterY = sum(pair[1] for pair in pairs) / count
    targetCenterX = sum(pair[2] for pair in pairs) / count
    targetCenterY = sum(pair[3] for pair in pairs) / count

    dot = 0.0
    cross = 0.0
    sourceSpread = 0.0
    for sourceX, sourceY, targetX, targetY in pairs:
        centeredSourceX = sourceX - sourceCenterX
        centeredSourceY = sourceY - sourceCenterY
        centeredTargetX = targetX - targetCenterX
        centeredTargetY = targetY - targetCenterY
        dot += centeredSourceX * centeredTargetX + centeredSourceY * centeredTargetY
        cross += centeredSourceX * centeredTargetY - centeredSourceY * centeredTargetX
        sourceSpread += (
            centeredSourceX * centeredSourceX + centeredSourceY * centeredSourceY
        )

    if sourceSpread < EPSILON:
        return _translation_transform(pairs[0])

    rotation = math.atan2(cross, dot)
    cosine = math.cos(rotation)
    sine = math.sin(rotation)

    return {
        "a": cosine,
        "b": -sine,
        "c": targetCenterX - cosine * sourceCenterX + sine * sourceCenterY,
        "d": sine,
        "e": cosine,
        "f": targetCenterY - sine * sourceCenterX - cosine * sourceCenterY,
    }


def _farthest_pair(pairs):
    farthest = None
    farthestDistance = -1.0
    for firstIndex in range(len(pairs)):
        sourceAX = pairs[firstIndex][0]
        sourceAY = pairs[firstIndex][1]
        for secondIndex in range(firstIndex + 1, len(pairs)):
            sourceBX = pairs[secondIndex][0]
            sourceBY = pairs[secondIndex][1]
            distance = (sourceBX - sourceAX) ** 2 + (sourceBY - sourceAY) ** 2
            if distance > farthestDistance:
                farthestDistance = distance
                farthest = (pairs[firstIndex], pairs[secondIndex])

    return farthest


def build_transform(pairs):
    if len(pairs) == 0:
        return (
            {"a": 1.0, "b": 0.0, "c": 0.0, "d": 0.0, "e": 1.0, "f": 0.0},
            "identity",
        )

    if len(pairs) == 1:
        return (_translation_transform(pairs[0]), "translation")

    transform = _rigid_transform(pairs)
    if transform is not None:
        return (transform, "rigid")

    farthest = _farthest_pair(pairs)
    if farthest is not None:
        fallback = _rigid_transform([farthest[0], farthest[1]])
        if fallback is not None:
            return (fallback, "rigid")

    return (_translation_transform(pairs[0]), "translation")


def _cyclic_pin_distance(pinA, pinB, pinMax):
    delta = abs(pinA - pinB)
    return min(delta, pinMax - delta)


def _interpolate_residual(pinA, residualA, pinB, residualB, pinValue):
    if pinA == pinB:
        return residualA

    fraction = float(pinValue - pinA) / float(pinB - pinA)
    return (
        residualA[0] + (residualB[0] - residualA[0]) * fraction,
        residualA[1] + (residualB[1] - residualA[1]) * fraction,
    )
