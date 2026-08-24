from math import hypot, isfinite
from scipy.optimize import brentq


def solve_comb_pull(pullin: float) -> float:
    """
    Solve

        x = (32*c)/23 + 77*cos(atan(d/x))

    with x > 0 and x > 77.

    Since x > 0,

        cos(atan(d/x)) = x / sqrt(x^2 + d^2)

    so we solve

        x - B - 77*x/sqrt(x^2 + d^2) = 0

    where B = 32*c/23.

    Returns the admissible root x > max(77, B).
    Raises ValueError if no admissible root exists.
    """

    if not isfinite(pullin):
        raise ValueError("c must be a finite real number.")

    B: float = (32.0 * pullin) / 23.0

    def f(x: float) -> float:
        return x - B - 77 * x / hypot(x, 150.0)

    # The admissible root, if it exists, must satisfy x > 77 and x > B.
    lo: float = max(77, B)

    # Move just above the open lower bound.
    eps: float = 1e-12 * max(1.0, abs(lo))
    left: float = lo + eps

    if f(left) >= 0:
        raise ValueError("No admissible solution satisfying x > 77 and x > 32c/23.")

    # Find an upper bound with f(right) > 0.
    right: float = max(left * 2.0, left + 1.0)

    while f(right) <= 0:
        right *= 2.0
        if right > 1e300:
            raise RuntimeError("Failed to bracket the root.")

    return brentq(f, left, right, xtol=1e-12, rtol=1e-12, maxiter=100)
