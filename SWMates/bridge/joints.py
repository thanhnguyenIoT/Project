"""Build Fusion joints from a stack of SolidWorks-style mates."""

from dataclasses import dataclass, field
from typing import List

import adsk.core
import adsk.fusion

from ..core import mates as m
from ..core import vec
from . import features, storage

MAX_ITERATIONS = 8


@dataclass
class Analysis:
    records: list
    old_joint: object
    resolved: list          # [(ent1, occ1, ent2, occ2)]
    constraints: list
    plan: m.Plan


@dataclass
class MateResult:
    joint: object
    plan: m.Plan
    summary: str
    warnings: List[str] = field(default_factory=list)


def _resolve_records(design, records):
    resolved = []
    for rec in records:
        e1, o1 = storage.resolve(design, rec['e1'])
        e2, o2 = storage.resolve(design, rec['e2'])
        resolved.append((e1, o1, e2, o2))
    return resolved


def _constraints(records, resolved):
    out = []
    for rec, (e1, _, e2, _) in zip(records, resolved):
        opts = m.MateOptions.from_dict(rec['opts'])
        out.append(m.make_constraint(opts, features.classify(e1), features.classify(e2)))
    return out


def _check_pair(ent1, ent2):
    occ1 = features.occurrence_of(ent1)
    occ2 = features.occurrence_of(ent2)
    if occ1 is None or occ2 is None:
        raise m.MateError('Hai đối tượng phải nằm trong component (không chọn body ở root).')
    if storage.occurrence_path(occ1) == storage.occurrence_path(occ2):
        raise m.MateError('Hai đối tượng phải thuộc hai component khác nhau.')
    return occ1, occ2


def analyze(design, ent1, ent2, options):
    """Plan the joint for a new mate (including existing mates of the same pair)
    without modifying the design."""
    occ1, occ2 = _check_pair(ent1, ent2)
    f1, f2 = features.classify(ent1), features.classify(ent2)
    new_c = m.make_constraint(options, f1, f2)
    anti = m.resolve_alignment(options, new_c.kind, f1, f2)
    rec = storage.make_record(options, anti, ent1, occ1, ent2, occ2)

    records, old_joint = [], None
    group = storage.find_group(design, storage.occurrence_path(occ1), storage.occurrence_path(occ2))
    if group is not None:
        old_joint, records, swapped = group
        if swapped:
            rec = storage.swap_record(rec)
    records = [rec] if new_c.kind == m.C_LOCK else list(records) + [rec]
    return analyze_records(design, records, old_joint)


def analyze_records(design, records, old_joint=None):
    resolved = _resolve_records(design, records)
    constraints = _constraints(records, resolved)
    plan = m.make_plan(constraints)
    return Analysis(records, old_joint, resolved, constraints, plan)


# ---------------------------------------------------------------------------


def _set_motion(inp, motion, axis_entity):
    D = adsk.fusion.JointDirections
    custom = axis_entity is not None
    if motion == m.M_RIGID:
        inp.setAsRigidJointMotion()
    elif motion == m.M_REVOLUTE:
        if custom:
            inp.setAsRevoluteJointMotion(D.CustomJointDirection, axis_entity)
        else:
            inp.setAsRevoluteJointMotion(D.ZAxisJointDirection)
    elif motion == m.M_SLIDER:
        if custom:
            inp.setAsSliderJointMotion(D.CustomJointDirection, axis_entity)
        else:
            inp.setAsSliderJointMotion(D.ZAxisJointDirection)
    elif motion == m.M_CYLINDRICAL:
        if custom:
            inp.setAsCylindricalJointMotion(D.CustomJointDirection, axis_entity)
        else:
            inp.setAsCylindricalJointMotion(D.ZAxisJointDirection)
    elif motion == m.M_PLANAR:
        inp.setAsPlanarJointMotion(D.ZAxisJointDirection)
    elif motion == m.M_BALL:
        inp.setAsBallJointMotion(D.ZAxisJointDirection, D.XAxisJointDirection)
    else:
        raise ValueError(motion)


def _check_health(joint):
    if joint is None:
        raise m.MateError('Fusion không tạo được joint.')
    if joint.healthState == adsk.fusion.FeatureHealthStates.ErrorFeatureHealthState:
        msg = joint.errorOrWarningMessage
        joint.deleteMe()
        raise m.MateError('Fusion báo lỗi joint: {}'.format(msg))


def _create_joint(root, analysis, flipped):
    plan = analysis.plan
    e1, _, e2, _ = analysis.resolved[plan.base_index]
    base = analysis.constraints[plan.base_index]
    inp = root.joints.createInput(features.joint_geometry(e1), features.joint_geometry(e2))
    inp.isFlipped = flipped
    axis_entity = e1 if base.f1.is_line else None
    _set_motion(inp, plan.motion, axis_entity)
    joint = root.joints.add(inp)
    _check_health(joint)
    return joint


def _create_as_built(root, analysis):
    _, o1, _, o2 = analysis.resolved[0]
    inp = root.asBuiltJoints.createInput(o1, o2, None)
    inp.setAsRigidJointMotion()
    joint = root.asBuiltJoints.add(inp)
    if joint is None:
        raise m.MateError('Fusion không tạo được as-built joint.')
    return joint


class _Measurer:
    def __init__(self, analysis):
        self.analysis = analysis

    def features(self, index):
        e1, _, e2, _ = self.analysis.resolved[index]
        return features.classify(e1), features.classify(e2)

    def value(self, step):
        f1, f2 = self.features(step.index)
        b1, b2 = self.features(self.analysis.plan.base_index)
        return m.measure(step.measure, f1, f2, b1, b2)


def _solve_step(joint, step, analysis, measurer):
    """Drive joint.offset / joint.angle with a secant iteration until the
    measurement reaches its target. Returns True on success."""
    param = joint.offset if step.param == m.P_OFFSET else joint.angle
    periodic = step.param == m.P_ANGLE
    constraint = analysis.constraints[step.index]
    anti = analysis.records[step.index]['anti']

    v0 = measurer.value(step)
    goal = m.target(step.measure, constraint, anti, v0)
    tol = m.tolerance(step.measure)

    p0 = param.value
    r0 = m.residual(step.measure, v0, goal)
    if abs(r0) <= tol:
        return True
    p1 = p0 - r0    # first guess: slope +1
    for _ in range(MAX_ITERATIONS):
        if periodic:
            p1 = vec.wrap_angle(p1)
        param.value = p1
        r1 = m.residual(step.measure, measurer.value(step), goal)
        if abs(r1) <= tol:
            return True
        dp = vec.wrap_angle(p1 - p0) if periodic else p1 - p0
        dr = vec.wrap_angle(r1 - r0) if periodic else r1 - r0
        if abs(dp) < 1e-12 or abs(dr) < 1e-6 * abs(dp):
            return False   # this parameter does not move the geometry
        p0, r0 = p1, r1
        p1 = p1 - r1 * dp / dr
    return False


def _alignment_ok(analysis, measurer):
    base = analysis.constraints[analysis.plan.base_index]
    if base.kind not in (m.C_PLANE, m.C_AXIS, m.C_CIRCLE):
        return True
    f1, f2 = measurer.features(analysis.plan.base_index)
    is_anti = vec.dot(f1.direction, f2.direction) < 0.0
    return is_anti == analysis.records[analysis.plan.base_index]['anti']


def _name_joint(joint, summary, analysis):
    _, o1, _, o2 = analysis.resolved[0]
    try:
        joint.name = 'SW {} ({} / {})'.format(summary, o1.name, o2.name)
    except RuntimeError:
        pass   # name clash: keep Fusion's default name


def build(design, analysis):
    """Create the joint described by ``analysis`` (replacing the old one)."""
    root = design.rootComponent
    if analysis.old_joint is not None and analysis.old_joint.isValid:
        analysis.old_joint.deleteMe()

    summary = m.summarize(analysis.constraints)
    warnings = []

    if analysis.plan.motion == m.M_AS_BUILT:
        joint = _create_as_built(root, analysis)
    else:
        measurer = _Measurer(analysis)
        joint = _create_joint(root, analysis, flipped=False)
        if not _alignment_ok(analysis, measurer):
            joint.deleteMe()
            joint = _create_joint(root, analysis, flipped=True)
            if not _alignment_ok(analysis, measurer):
                warnings.append('Không đạt được hướng Aligned/Anti-Aligned mong muốn.')

        for step in analysis.plan.steps:
            if not _solve_step(joint, step, analysis, measurer):
                warnings.append('Không căn chỉnh chính xác được mate #{} ({}).'.format(
                    step.index + 1, m.MATE_LABELS[analysis.constraints[step.index].options.mate_type]))

        for index in analysis.plan.checks:
            check = m.SolveStep(m.P_OFFSET, index, m.MEAS_SLIDE)
            value = measurer.value(check)
            goal = m.target(m.MEAS_SLIDE, analysis.constraints[index], analysis.records[index]['anti'], value)
            if abs(value - goal) > 10 * m.LENGTH_TOL:
                warnings.append('Mate #{}: hai mặt phẳng song song nhưng lệch {:.4f} cm '
                                '(hình học không khớp).'.format(index + 1, value - goal))

    _name_joint(joint, summary, analysis)
    storage.write_records(joint, analysis.records)
    return MateResult(joint, analysis.plan, summary, warnings)


def apply_mate(design, ent1, ent2, options):
    return build(design, analyze(design, ent1, ent2, options))


def remove_mate(design, joint, records, index):
    """Delete one mate from a managed joint and rebuild the rest."""
    remaining = [r for i, r in enumerate(records) if i != index]
    if not remaining:
        joint.deleteMe()
        return None
    return build(design, analyze_records(design, remaining, joint))
