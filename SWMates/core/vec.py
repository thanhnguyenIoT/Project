"""Small 3D vector helpers on plain tuples (no Fusion dependency, unit-testable)."""

import math

EPS = 1e-9


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    if n < EPS:
        return (0.0, 0.0, 0.0)
    return scale(a, 1.0 / n)


def perp(v, axis):
    """Component of v perpendicular to the (unit) axis."""
    a = unit(axis)
    return sub(v, scale(a, dot(v, a)))


def wrap_angle(angle):
    """Wrap an angle to (-pi, pi]."""
    a = math.fmod(angle + math.pi, 2.0 * math.pi)
    if a <= 0.0:
        a += 2.0 * math.pi
    return a - math.pi


def signed_angle(v1, v2, axis):
    """Signed angle from v1 to v2 measured around axis (right-hand rule)."""
    a = unit(axis)
    return math.atan2(dot(cross(v1, v2), a), dot(v1, v2))


def angle_between(d1, d2):
    """Unsigned angle between two directions, in [0, pi]."""
    c = dot(unit(d1), unit(d2))
    return math.acos(max(-1.0, min(1.0, c)))


def is_parallel(d1, d2, tol=1e-4):
    """True when two directions are parallel or anti-parallel."""
    return length(cross(unit(d1), unit(d2))) < tol


def is_perpendicular(d1, d2, tol=1e-4):
    return abs(dot(unit(d1), unit(d2))) < tol


def distance_point_to_line(p, line_point, line_dir):
    return length(perp(sub(p, line_point), line_dir))
