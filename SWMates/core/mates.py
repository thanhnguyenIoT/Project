"""SolidWorks-style mate logic, independent from the Fusion API.

SolidWorks mates are individual constraints that each remove some degrees of
freedom (DOF).  Fusion only knows *joints*: one joint between two components
that describes the complete relative motion (rigid, revolute, slider, ...).

This module translates a *stack* of SolidWorks mates between the same pair of
components into a single Fusion joint plan:

* the most constraining mate (circle > axis > plane > point > frame) becomes
  the joint "base" and defines the joint geometry and its Z axis;
* every additional mate consumes the remaining DOF of that base (rotation
  about / sliding along the Z axis) and is satisfied numerically by adjusting
  the joint ``angle`` / ``offset`` parameters (see ``measure``/``targets``).

All lengths are in centimetres and all angles in radians (Fusion internal units).
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import vec

# --- Mate types (names follow the SolidWorks Mate PropertyManager) ----------

COINCIDENT = 'coincident'
PARALLEL = 'parallel'
PERPENDICULAR = 'perpendicular'
CONCENTRIC = 'concentric'
LOCK = 'lock'
DISTANCE = 'distance'
ANGLE = 'angle'

MATE_TYPES = [COINCIDENT, PARALLEL, PERPENDICULAR, CONCENTRIC, LOCK, DISTANCE, ANGLE]

MATE_LABELS = {
    COINCIDENT: 'Coincident (Trùng)',
    PARALLEL: 'Parallel (Song song)',
    PERPENDICULAR: 'Perpendicular (Vuông góc)',
    CONCENTRIC: 'Concentric (Đồng tâm)',
    LOCK: 'Lock (Khóa)',
    DISTANCE: 'Distance (Khoảng cách)',
    ANGLE: 'Angle (Góc)',
}

# --- Alignment -------------------------------------------------------------

ALIGN_AUTO = 'auto'
ALIGNED = 'aligned'
ANTI_ALIGNED = 'anti'

ALIGN_LABELS = {
    ALIGN_AUTO: 'Tự động',
    ALIGNED: 'Aligned (Cùng chiều)',
    ANTI_ALIGNED: 'Anti-Aligned (Ngược chiều)',
}

# --- Geometric feature kinds (what the user picked) ------------------------

PLANE = 'plane'      # planar face
AXIS = 'axis'        # cylinder / cone face, linear edge, sketch line
CIRCLE = 'circle'    # circular edge / arc / sketch circle (center + normal)
POINT = 'point'      # vertex, sketch point, construction point
SPHERE = 'sphere'    # spherical face (center)
FRAME = 'frame'      # Fusion joint origin (full coordinate system)

KIND_LABELS = {
    PLANE: 'mặt phẳng',
    AXIS: 'trục/mặt trụ',
    CIRCLE: 'cạnh tròn',
    POINT: 'điểm',
    SPHERE: 'mặt cầu',
    FRAME: 'joint origin',
}

# --- Constraint kinds (normalised meaning of one mate) ---------------------

C_PLANE = 'PLANE'      # two planes coincident / at distance
C_AXIS = 'AXIS'        # two axes collinear
C_CIRCLE = 'CIRCLE'    # collinear axes + coincident circle planes (peg-in-hole)
C_POINT = 'POINT'      # two points coincident
C_ORIENT = 'ORIENT'    # orientation only (parallel / perpendicular / angle)
C_FRAME = 'FRAME'      # two joint origins coincident
C_LOCK = 'LOCK'        # freeze current relative position

# --- Fusion joint motions --------------------------------------------------

M_RIGID = 'rigid'
M_REVOLUTE = 'revolute'
M_SLIDER = 'slider'
M_CYLINDRICAL = 'cylindrical'
M_PLANAR = 'planar'
M_BALL = 'ball'
M_AS_BUILT = 'as_built_rigid'

MOTION_LABELS = {
    M_RIGID: 'Rigid (0 bậc tự do)',
    M_REVOLUTE: 'Revolute (1 bậc tự do: xoay)',
    M_SLIDER: 'Slider (1 bậc tự do: trượt)',
    M_CYLINDRICAL: 'Cylindrical (2 bậc tự do: xoay + trượt)',
    M_PLANAR: 'Planar (3 bậc tự do: trượt trong mặt phẳng + xoay)',
    M_BALL: 'Ball (3 bậc tự do: xoay quanh điểm)',
    M_AS_BUILT: 'As-built Rigid (khóa tại vị trí hiện tại)',
}

# DOF that remain free around the base axis.
ROT = 'rot'
SLIDE = 'slide'

# Solve parameters / measurements.
P_OFFSET = 'offset'
P_ANGLE = 'angle'
MEAS_SLIDE = 'slide'
MEAS_ROT_DIR = 'rot_dir'
MEAS_ROT_AXIS = 'rot_axis'

LENGTH_TOL = 1e-4   # cm (1 micron)
ANGLE_TOL = 1e-5    # rad


class MateError(Exception):
    """A mate (or mate stack) that cannot be turned into a Fusion joint."""


@dataclass
class Feature:
    """World-space description of a selected entity."""
    kind: str
    origin: Tuple[float, float, float]
    direction: Optional[Tuple[float, float, float]] = None
    radius: float = 0.0
    is_line: bool = False   # axis that comes from a straight edge/sketch line


@dataclass
class MateOptions:
    mate_type: str
    alignment: str = ALIGN_AUTO
    distance: float = 0.0        # cm, for DISTANCE
    angle: float = 0.0           # rad, for ANGLE
    flip_dimension: bool = False
    lock_rotation: bool = False  # for CONCENTRIC

    def to_dict(self):
        return {
            'type': self.mate_type, 'align': self.alignment,
            'dist': self.distance, 'ang': self.angle,
            'flip': self.flip_dimension, 'lockrot': self.lock_rotation,
        }

    @staticmethod
    def from_dict(d):
        return MateOptions(d['type'], d.get('align', ALIGN_AUTO), d.get('dist', 0.0),
                           d.get('ang', 0.0), d.get('flip', False), d.get('lockrot', False))


@dataclass
class Constraint:
    kind: str
    options: MateOptions
    f1: Feature
    f2: Feature


@dataclass
class SolveStep:
    param: str          # P_OFFSET or P_ANGLE
    index: int          # constraint index in the stack
    measure: str        # MEAS_*


@dataclass
class Plan:
    motion: str
    base_index: int
    steps: List[SolveStep] = field(default_factory=list)
    checks: List[int] = field(default_factory=list)   # constraints to verify (slide) after solving
    free: Tuple[str, ...] = ()

    def describe(self):
        return MOTION_LABELS.get(self.motion, self.motion)


# ---------------------------------------------------------------------------
# Mate type <-> geometry
# ---------------------------------------------------------------------------

_PLANE_LIKE = (PLANE, CIRCLE)
_AXIS_LIKE = (AXIS, CIRCLE)
_POINT_LIKE = (POINT, SPHERE)
_DIRECTED = (PLANE, AXIS, CIRCLE)


def constraint_kind(mate_type, k1, k2):
    """Normalised constraint kind for a mate between two feature kinds.

    Raises MateError when the combination has no Fusion joint equivalent.
    """
    pair = (k1, k2)
    if mate_type == LOCK:
        return C_LOCK
    if mate_type == COINCIDENT:
        if k1 == CIRCLE and k2 == CIRCLE:
            return C_CIRCLE
        if k1 in _PLANE_LIKE and k2 in _PLANE_LIKE:
            return C_PLANE
        if k1 in _AXIS_LIKE and k2 in _AXIS_LIKE:
            return C_AXIS
        if k1 in _POINT_LIKE and k2 in _POINT_LIKE:
            return C_POINT
        if k1 == FRAME and k2 == FRAME:
            return C_FRAME
    elif mate_type == CONCENTRIC:
        if k1 in _AXIS_LIKE and k2 in _AXIS_LIKE:
            return C_AXIS
        if k1 in _POINT_LIKE and k2 in _POINT_LIKE and SPHERE in pair:
            return C_POINT
    elif mate_type == DISTANCE:
        if k1 == CIRCLE and k2 == CIRCLE:
            return C_CIRCLE
        if k1 in _PLANE_LIKE and k2 in _PLANE_LIKE:
            return C_PLANE
    elif mate_type in (PARALLEL, PERPENDICULAR, ANGLE):
        if k1 in _DIRECTED and k2 in _DIRECTED:
            return C_ORIENT
    raise MateError('Mate {} không áp dụng được cho {} + {}.'.format(
        MATE_LABELS.get(mate_type, mate_type), KIND_LABELS.get(k1, k1), KIND_LABELS.get(k2, k2)))


def allowed_mates(k1, k2):
    result = []
    for t in MATE_TYPES:
        try:
            constraint_kind(t, k1, k2)
            result.append(t)
        except MateError:
            pass
    return result


def suggest_mate(k1, k2):
    """Default mate for a selection, like SolidWorks' mate pop-up toolbar."""
    pair = {k1, k2}
    if pair <= {AXIS, CIRCLE} and AXIS in pair:
        return CONCENTRIC
    if k1 == SPHERE or k2 == SPHERE:
        return CONCENTRIC
    if k1 in _DIRECTED and k2 in _DIRECTED and not (set(_PLANE_LIKE) >= pair):
        return PARALLEL
    allowed = allowed_mates(k1, k2)
    if COINCIDENT in allowed:
        return COINCIDENT
    return allowed[0] if allowed else LOCK


def default_anti_aligned(kind):
    """SolidWorks default: face-to-face mates are anti-aligned."""
    return kind in (C_PLANE, C_CIRCLE)


def resolve_alignment(options, kind, f1, f2):
    """Return True for anti-aligned, False for aligned.

    ALIGN_AUTO picks the SolidWorks default for planes/circles and the
    alignment closest to the current position for axes / orientation mates.
    """
    if options.alignment == ALIGNED:
        return False
    if options.alignment == ANTI_ALIGNED:
        return True
    if default_anti_aligned(kind):
        return True
    if f1.direction is not None and f2.direction is not None:
        return vec.dot(f1.direction, f2.direction) < 0.0
    return False


def make_constraint(options, f1, f2):
    kind = constraint_kind(options.mate_type, f1.kind, f2.kind)
    if kind == C_ORIENT and options.mate_type == ANGLE and options.angle < 0:
        raise MateError('Góc phải là số dương.')
    if options.mate_type == DISTANCE and options.distance < 0:
        raise MateError('Khoảng cách phải là số dương.')
    return Constraint(kind, options, f1, f2)


# ---------------------------------------------------------------------------
# Planner: mate stack -> one Fusion joint
# ---------------------------------------------------------------------------

_BASE_PRIORITY = [C_CIRCLE, C_AXIS, C_PLANE, C_POINT, C_FRAME]


def _relation(d, axis):
    if vec.is_parallel(d, axis):
        return 'parallel'
    if vec.is_perpendicular(d, axis):
        return 'perpendicular'
    return 'oblique'


def _same_relation(c, base, fn):
    r1 = fn(c.f1, base.f1)
    r2 = fn(c.f2, base.f2)
    if r1 != r2:
        raise MateError('Hình học hai chi tiết không tương thích với mate trước đó '
                        '({} vs {}).'.format(r1, r2))
    return r1


def _coaxial(f, base_f):
    return vec.distance_point_to_line(f.origin, base_f.origin, base_f.direction) < LENGTH_TOL


def make_plan(constraints):
    """Turn a list of Constraint (same component pair) into a joint Plan."""
    if not constraints:
        raise MateError('Chưa có mate nào.')

    kinds = [c.kind for c in constraints]
    if C_LOCK in kinds:
        if len(constraints) > 1:
            raise MateError('Cặp chi tiết đã bị Lock. Hãy xóa mate Lock trước.')
        return Plan(M_AS_BUILT, 0)

    base_index = None
    for k in _BASE_PRIORITY:
        if k in kinds:
            base_index = kinds.index(k)
            break
    if base_index is None:
        raise MateError('Mate Parallel/Perpendicular/Angle không tự tạo được joint trong Fusion; '
                        'hãy thêm trước một mate Concentric hoặc Coincident trên cạnh tròn.')

    base = constraints[base_index]
    others = [i for i in range(len(constraints)) if i != base_index]

    if base.kind in (C_PLANE, C_POINT, C_FRAME):
        if others:
            raise MateError('Fusion joint không biểu diễn được tổ hợp mate này với mate gốc {}. '
                            'Chỉ hỗ trợ ghép thêm mate khi mate gốc là Concentric/cạnh tròn. '
                            'Gợi ý: dùng Concentric, hoặc Lock.'.format(base.kind))
        if base.kind == C_PLANE:
            return Plan(M_PLANAR, base_index, [SolveStep(P_OFFSET, base_index, MEAS_SLIDE)],
                        free=('tx', 'ty', ROT))
        if base.kind == C_POINT:
            return Plan(M_BALL, base_index, free=('rx', 'ry', 'rz'))
        return Plan(M_RIGID, base_index)

    # Axis based joints.
    free = {ROT, SLIDE}
    steps = []
    checks = []
    if base.kind == C_CIRCLE:
        free.discard(SLIDE)
        steps.append(SolveStep(P_OFFSET, base_index, MEAS_SLIDE))
    elif base.options.lock_rotation:
        free.discard(ROT)

    def consume(dof, step):
        if dof not in free:
            raise MateError('Thừa ràng buộc (over-defined): bậc tự do "{}" đã bị khóa bởi mate trước.'.format(
                'xoay' if dof == ROT else 'trượt'))
        free.discard(dof)
        steps.append(step)

    for i in others:
        c = constraints[i]
        if c.kind == C_PLANE:
            rel = _same_relation(c, base, lambda f, b: _relation(f.direction, b.direction))
            if rel == 'parallel':
                consume(SLIDE, SolveStep(P_OFFSET, i, MEAS_SLIDE))
            elif rel == 'perpendicular':
                consume(ROT, SolveStep(P_ANGLE, i, MEAS_ROT_DIR))
                checks.append(i)
            else:
                raise MateError('Mặt phẳng xiên so với trục: không hỗ trợ.')
        elif c.kind == C_ORIENT:
            rel = _same_relation(c, base, lambda f, b: _relation(f.direction, b.direction))
            if rel != 'perpendicular':
                raise MateError('Mate định hướng chỉ dùng được với hướng vuông góc với trục xoay '
                                '(nếu song song với trục thì mate bị thừa).')
            consume(ROT, SolveStep(P_ANGLE, i, MEAS_ROT_DIR))
        elif c.kind in (C_AXIS, C_CIRCLE):
            rel = _same_relation(c, base, lambda f, b: _relation(f.direction, b.direction))
            if rel != 'parallel':
                raise MateError('Trục thứ hai phải song song với trục của mate gốc.')
            co = _same_relation(c, base, _coaxial)
            if c.kind == C_AXIS:
                if co:
                    raise MateError('Thừa ràng buộc: hai trục này đã đồng tâm sẵn.')
                consume(ROT, SolveStep(P_ANGLE, i, MEAS_ROT_AXIS))
            else:
                if not co:
                    consume(ROT, SolveStep(P_ANGLE, i, MEAS_ROT_AXIS))
                consume(SLIDE, SolveStep(P_OFFSET, i, MEAS_SLIDE))
        else:
            raise MateError('Không ghép được mate {} với mate gốc dạng trục.'.format(c.kind))

    if free == {ROT, SLIDE}:
        motion = M_CYLINDRICAL
    elif free == {ROT}:
        motion = M_REVOLUTE
    elif free == {SLIDE}:
        motion = M_SLIDER
    else:
        motion = M_RIGID

    # Rotation does not change axial distances, so solve angles first.
    steps.sort(key=lambda s: 0 if s.param == P_ANGLE else 1)
    return Plan(motion, base_index, steps, checks, tuple(sorted(free)))


# ---------------------------------------------------------------------------
# Measurements and targets (used to drive joint offset / angle)
# ---------------------------------------------------------------------------

def measure(kind, f1, f2, b1, b2):
    """Current value of a measurement.

    f1/f2: features of the constraint being satisfied, b1/b2: base features.
    """
    if kind == MEAS_SLIDE:
        return vec.dot(vec.sub(f2.origin, f1.origin), vec.unit(f1.direction))
    a = vec.unit(b1.direction)
    if kind == MEAS_ROT_DIR:
        return vec.signed_angle(vec.perp(f1.direction, a), vec.perp(f2.direction, a), a)
    if kind == MEAS_ROT_AXIS:
        v1 = vec.perp(vec.sub(f1.origin, b1.origin), a)
        v2 = vec.perp(vec.sub(f2.origin, b2.origin), a)
        return vec.signed_angle(v1, v2, a)
    raise ValueError(kind)


def is_periodic(kind):
    return kind in (MEAS_ROT_DIR, MEAS_ROT_AXIS)


def _pick(candidates, current, flip, periodic):
    def dist(t):
        return abs(vec.wrap_angle(current - t)) if periodic else abs(current - t)
    ordered = sorted(candidates, key=dist)
    if flip and len(ordered) > 1:
        return ordered[1]
    return ordered[0]


def target(kind, constraint, anti_aligned, current):
    """Target value for a measurement, choosing the solution nearest to ``current``
    (or the other one when the user asked to flip the dimension)."""
    opts = constraint.options
    if kind == MEAS_SLIDE:
        d = opts.distance if opts.mate_type == DISTANCE else 0.0
        cands = [d, -d] if d > LENGTH_TOL else [0.0]
        return _pick(cands, current, opts.flip_dimension, False)
    if kind == MEAS_ROT_DIR:
        if opts.mate_type == PERPENDICULAR:
            alpha, offset = math.pi / 2.0, 0.0
        else:
            alpha = opts.angle if opts.mate_type == ANGLE else 0.0
            offset = math.pi if anti_aligned else 0.0
        cands = {round(vec.wrap_angle(offset + s * alpha), 12) for s in (1.0, -1.0)}
        return _pick(sorted(cands), current, opts.flip_dimension, True)
    if kind == MEAS_ROT_AXIS:
        return 0.0
    raise ValueError(kind)


def residual(kind, value, goal):
    if is_periodic(kind):
        return vec.wrap_angle(value - goal)
    return value - goal


def tolerance(kind):
    return ANGLE_TOL if is_periodic(kind) else LENGTH_TOL


def summarize(constraints):
    names = []
    for c in constraints:
        n = MATE_LABELS.get(c.options.mate_type, c.options.mate_type).split(' ')[0]
        if c.kind == C_CIRCLE and c.options.mate_type == COINCIDENT:
            n = 'Concentric+Coincident'
        names.append(n)
    return ' + '.join(names)
