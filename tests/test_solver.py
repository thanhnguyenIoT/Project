"""Tests for the numeric joint-parameter solver, with the Fusion API mocked out."""

import math
import os
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_adsk = mock.MagicMock()
with mock.patch.dict(sys.modules, {'adsk': _adsk, 'adsk.core': _adsk.core, 'adsk.fusion': _adsk.fusion}):
    from SWMates.bridge import joints  # noqa: E402
from SWMates.core import mates as m  # noqa: E402
from SWMates.core import vec  # noqa: E402


class FakeJoint:
    def __init__(self):
        self.offset = SimpleNamespace(value=0.0)
        self.angle = SimpleNamespace(value=0.0)


class LinearMeasurer:
    """Measurement = slope * parameter + intercept (wrapped for angles)."""

    def __init__(self, joint, param, slope, intercept, periodic):
        self.joint, self.param, self.slope, self.intercept, self.periodic = joint, param, slope, intercept, periodic

    def value(self, step):
        v = self.slope * getattr(self.joint, self.param).value + self.intercept
        return vec.wrap_angle(v) if self.periodic else v


def _analysis(mate_type, **kw):
    f = m.Feature(m.PLANE, (0, 0, 0), (0, 0, 1))
    c = m.make_constraint(m.MateOptions(mate_type, **kw), f, f)
    return SimpleNamespace(constraints=[c], records=[{'anti': kw.get('alignment') == m.ANTI_ALIGNED}])


@pytest.mark.parametrize('slope', [1.0, -1.0, 2.5, -0.3])
def test_offset_solve(slope):
    joint = FakeJoint()
    analysis = _analysis(m.DISTANCE, distance=2.0)
    meas = LinearMeasurer(joint, 'offset', slope, 7.0, False)
    step = m.SolveStep(m.P_OFFSET, 0, m.MEAS_SLIDE)
    assert joints._solve_step(joint, step, analysis, meas)
    assert meas.value(step) == pytest.approx(2.0, abs=1e-4)


@pytest.mark.parametrize('slope,intercept', [(1.0, 2.0), (-1.0, -2.9), (1.0, math.pi - 0.05)])
def test_angle_solve_wraps(slope, intercept):
    joint = FakeJoint()
    analysis = _analysis(m.ANGLE, angle=math.radians(40))
    meas = LinearMeasurer(joint, 'angle', slope, intercept, True)
    step = m.SolveStep(m.P_ANGLE, 0, m.MEAS_ROT_DIR)
    assert joints._solve_step(joint, step, analysis, meas)
    assert abs(abs(meas.value(step)) - math.radians(40)) < 1e-5


def test_parameter_without_effect_fails_cleanly():
    joint = FakeJoint()
    analysis = _analysis(m.DISTANCE, distance=1.0)
    meas = LinearMeasurer(joint, 'offset', 0.0, 5.0, False)
    step = m.SolveStep(m.P_OFFSET, 0, m.MEAS_SLIDE)
    assert not joints._solve_step(joint, step, analysis, meas)
