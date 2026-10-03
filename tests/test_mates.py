import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from SWMates.core import mates as m  # noqa: E402
from SWMates.core import vec  # noqa: E402

Z = (0.0, 0.0, 1.0)
X = (1.0, 0.0, 0.0)
Y = (0.0, 1.0, 0.0)
O = (0.0, 0.0, 0.0)


def F(kind, origin=O, direction=Z):
    return m.Feature(kind, origin, direction)


def C(mate_type, f1, f2, **kw):
    return m.make_constraint(m.MateOptions(mate_type, **kw), f1, f2)


# --- constraint kinds -------------------------------------------------------

@pytest.mark.parametrize('mate_type,k1,k2,expected', [
    (m.COINCIDENT, m.PLANE, m.PLANE, m.C_PLANE),
    (m.COINCIDENT, m.CIRCLE, m.PLANE, m.C_PLANE),
    (m.COINCIDENT, m.CIRCLE, m.CIRCLE, m.C_CIRCLE),
    (m.COINCIDENT, m.POINT, m.POINT, m.C_POINT),
    (m.CONCENTRIC, m.AXIS, m.CIRCLE, m.C_AXIS),
    (m.CONCENTRIC, m.SPHERE, m.POINT, m.C_POINT),
    (m.DISTANCE, m.PLANE, m.PLANE, m.C_PLANE),
    (m.ANGLE, m.PLANE, m.AXIS, m.C_ORIENT),
    (m.LOCK, m.POINT, m.PLANE, m.C_LOCK),
])
def test_constraint_kind(mate_type, k1, k2, expected):
    assert m.constraint_kind(mate_type, k1, k2) == expected


@pytest.mark.parametrize('mate_type,k1,k2', [
    (m.CONCENTRIC, m.PLANE, m.PLANE),
    (m.DISTANCE, m.POINT, m.POINT),
    (m.COINCIDENT, m.POINT, m.PLANE),
    (m.CONCENTRIC, m.POINT, m.POINT),
])
def test_constraint_kind_rejects(mate_type, k1, k2):
    with pytest.raises(m.MateError):
        m.constraint_kind(mate_type, k1, k2)


def test_suggestions():
    assert m.suggest_mate(m.PLANE, m.PLANE) == m.COINCIDENT
    assert m.suggest_mate(m.AXIS, m.AXIS) == m.CONCENTRIC
    assert m.suggest_mate(m.AXIS, m.CIRCLE) == m.CONCENTRIC
    assert m.suggest_mate(m.CIRCLE, m.CIRCLE) == m.COINCIDENT
    assert m.suggest_mate(m.SPHERE, m.SPHERE) == m.CONCENTRIC
    assert m.suggest_mate(m.FRAME, m.FRAME) == m.COINCIDENT
    assert m.suggest_mate(m.POINT, m.PLANE) == m.LOCK


# --- planner ---------------------------------------------------------------

def test_single_mates():
    assert m.make_plan([C(m.COINCIDENT, F(m.PLANE), F(m.PLANE))]).motion == m.M_PLANAR
    assert m.make_plan([C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS))]).motion == m.M_CYLINDRICAL
    assert m.make_plan([C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS), lock_rotation=True)]).motion == m.M_SLIDER
    assert m.make_plan([C(m.COINCIDENT, F(m.CIRCLE), F(m.CIRCLE))]).motion == m.M_REVOLUTE
    assert m.make_plan([C(m.COINCIDENT, F(m.POINT), F(m.POINT))]).motion == m.M_BALL
    assert m.make_plan([C(m.LOCK, F(m.POINT), F(m.PLANE))]).motion == m.M_AS_BUILT


def test_concentric_plus_coincident_is_revolute():
    plan = m.make_plan([
        C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS)),
        C(m.COINCIDENT, F(m.PLANE, (5, 0, 1)), F(m.PLANE, (3, 3, 2))),
    ])
    assert plan.motion == m.M_REVOLUTE
    assert plan.base_index == 0
    assert [(s.param, s.index, s.measure) for s in plan.steps] == [(m.P_OFFSET, 1, m.MEAS_SLIDE)]


def test_hinge_plus_parallel_is_rigid_and_solves_angle_first():
    plan = m.make_plan([
        C(m.COINCIDENT, F(m.CIRCLE), F(m.CIRCLE)),
        C(m.PARALLEL, F(m.PLANE, direction=X), F(m.PLANE, direction=Y)),
    ])
    assert plan.motion == m.M_RIGID
    assert plan.steps[0].param == m.P_ANGLE


def test_two_parallel_pins_is_slider():
    plan = m.make_plan([
        C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS)),
        C(m.CONCENTRIC, F(m.AXIS, (4, 0, 0)), F(m.AXIS, (0, 4, 0))),
    ])
    assert plan.motion == m.M_SLIDER
    assert plan.steps[0].measure == m.MEAS_ROT_AXIS


def test_base_is_chosen_by_priority_not_order():
    plan = m.make_plan([
        C(m.COINCIDENT, F(m.PLANE, (0, 0, 2)), F(m.PLANE, (0, 0, 7))),
        C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS)),
    ])
    assert plan.base_index == 1
    assert plan.motion == m.M_REVOLUTE


def test_over_defined():
    with pytest.raises(m.MateError):
        m.make_plan([
            C(m.COINCIDENT, F(m.CIRCLE), F(m.CIRCLE)),
            C(m.COINCIDENT, F(m.PLANE, (0, 0, 1)), F(m.PLANE, (0, 0, 1))),
        ])
    with pytest.raises(m.MateError):
        m.make_plan([
            C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS)),
            C(m.CONCENTRIC, F(m.AXIS, (0, 0, 5)), F(m.AXIS, (0, 0, 9))),
        ])


def test_unsupported_combinations():
    with pytest.raises(m.MateError):
        m.make_plan([C(m.PARALLEL, F(m.PLANE), F(m.PLANE))])
    with pytest.raises(m.MateError):
        m.make_plan([
            C(m.COINCIDENT, F(m.PLANE), F(m.PLANE)),
            C(m.COINCIDENT, F(m.PLANE, direction=X), F(m.PLANE, direction=X)),
        ])
    with pytest.raises(m.MateError):
        m.make_plan([C(m.LOCK, F(m.POINT), F(m.POINT)), C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS))])


def test_inconsistent_sides():
    with pytest.raises(m.MateError):
        m.make_plan([
            C(m.CONCENTRIC, F(m.AXIS), F(m.AXIS)),
            C(m.COINCIDENT, F(m.PLANE, direction=Z), F(m.PLANE, direction=X)),
        ])


# --- measurements / targets ---------------------------------------------------

def test_slide_measure_and_distance_target():
    c = C(m.DISTANCE, F(m.PLANE, (0, 0, 1)), F(m.PLANE, (0, 0, 4), (0, 0, -1)), distance=2.0)
    value = m.measure(m.MEAS_SLIDE, c.f1, c.f2, None, None)
    assert value == pytest.approx(3.0)
    assert m.target(m.MEAS_SLIDE, c, True, value) == pytest.approx(2.0)
    c.options.flip_dimension = True
    assert m.target(m.MEAS_SLIDE, c, True, value) == pytest.approx(-2.0)


def test_rot_dir_targets():
    base = F(m.AXIS)
    c = C(m.ANGLE, F(m.PLANE, direction=X), F(m.PLANE, direction=Y), angle=math.radians(30))
    value = m.measure(m.MEAS_ROT_DIR, c.f1, c.f2, base, base)
    assert value == pytest.approx(math.pi / 2)
    goal = m.target(m.MEAS_ROT_DIR, c, False, value)
    assert goal == pytest.approx(math.radians(30))
    goal_anti = m.target(m.MEAS_ROT_DIR, c, True, value)
    assert abs(vec.wrap_angle(goal_anti - math.radians(150))) < 1e-9

    perp = C(m.PERPENDICULAR, F(m.PLANE, direction=X), F(m.PLANE, direction=X))
    assert abs(m.target(m.MEAS_ROT_DIR, perp, False, 0.1)) == pytest.approx(math.pi / 2)


def test_rot_axis_measure():
    b1 = F(m.AXIS, (0, 0, 0))
    b2 = F(m.AXIS, (0, 0, 3))
    f1 = F(m.AXIS, (4, 0, 0))
    f2 = F(m.AXIS, (0, 4, 5))
    assert m.measure(m.MEAS_ROT_AXIS, f1, f2, b1, b2) == pytest.approx(math.pi / 2)


def test_residual_wraps_angles():
    assert m.residual(m.MEAS_ROT_DIR, math.pi - 0.01, -math.pi + 0.01) == pytest.approx(-0.02)
    assert m.residual(m.MEAS_SLIDE, 3.0, 1.0) == pytest.approx(2.0)


def test_resolve_alignment():
    opts = m.MateOptions(m.CONCENTRIC)
    assert m.resolve_alignment(opts, m.C_AXIS, F(m.AXIS, direction=Z), F(m.AXIS, direction=(0, 0, -1)))
    assert not m.resolve_alignment(opts, m.C_AXIS, F(m.AXIS), F(m.AXIS))
    assert m.resolve_alignment(m.MateOptions(m.COINCIDENT), m.C_PLANE, F(m.PLANE), F(m.PLANE))
    assert not m.resolve_alignment(m.MateOptions(m.COINCIDENT, m.ALIGNED), m.C_PLANE, F(m.PLANE), F(m.PLANE))


def test_options_roundtrip():
    o = m.MateOptions(m.ANGLE, m.ANTI_ALIGNED, 1.5, 0.3, True, True)
    assert m.MateOptions.from_dict(o.to_dict()) == o
