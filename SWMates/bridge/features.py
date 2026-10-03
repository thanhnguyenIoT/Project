"""Convert selected Fusion entities into world-space ``Feature`` objects."""

import adsk.core
import adsk.fusion

from ..core import mates as m
from ..core import vec

# Selection filters accepted by the Mate command.
SELECTION_FILTERS = [
    'PlanarFaces', 'CylindricalFaces', 'ConicalFaces', 'SphericalFaces', 'ToroidalFaces',
    'LinearEdges', 'CircularEdges', 'Vertices',
    'SketchPoints', 'SketchCurves', 'ConstructionPoints', 'JointOrigins',
]


def _t(p):
    return (p.x, p.y, p.z)


def occurrence_of(entity):
    """Occurrence (assembly context) that owns the selected entity, or None."""
    occ = getattr(entity, 'assemblyContext', None)
    if occ is None and isinstance(entity, adsk.fusion.SketchEntity):
        occ = entity.parentSketch.assemblyContext
    return occ


def _face_normal(face):
    ok, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
    if not ok:
        raise m.MateError('Không lấy được pháp tuyến của mặt.')
    return vec.unit(_t(normal))


def _circle_direction(edge, normal):
    """Prefer the outward normal of an adjacent planar face, so that "anti-aligned"
    means "faces against each other" like in SolidWorks."""
    for face in edge.faces:
        geom = face.geometry
        if geom.surfaceType == adsk.core.SurfaceTypes.PlaneSurfaceType:
            n = _face_normal(face)
            if vec.is_parallel(n, normal):
                return n
    return normal


def _from_curve3d(curve, edge=None):
    t = curve.curveType
    if t == adsk.core.Curve3DTypes.Line3DCurveType:
        start, end = _t(curve.startPoint), _t(curve.endPoint)
        return m.Feature(m.AXIS, start, vec.unit(vec.sub(end, start)), is_line=True)
    if t in (adsk.core.Curve3DTypes.Circle3DCurveType, adsk.core.Curve3DTypes.Arc3DCurveType):
        normal = vec.unit(_t(curve.normal))
        if edge is not None:
            normal = _circle_direction(edge, normal)
        return m.Feature(m.CIRCLE, _t(curve.center), normal, curve.radius)
    raise m.MateError('Chỉ hỗ trợ cạnh thẳng hoặc cạnh tròn.')


def classify(entity):
    """Return a world-space Feature for a (proxy) entity selected in the assembly."""
    if isinstance(entity, adsk.fusion.BRepFace):
        geom = entity.geometry
        st = geom.surfaceType
        if st == adsk.core.SurfaceTypes.PlaneSurfaceType:
            return m.Feature(m.PLANE, _t(entity.pointOnFace), _face_normal(entity))
        if st in (adsk.core.SurfaceTypes.CylinderSurfaceType, adsk.core.SurfaceTypes.ConeSurfaceType):
            return m.Feature(m.AXIS, _t(geom.origin), vec.unit(_t(geom.axis)),
                             getattr(geom, 'radius', 0.0))
        if st == adsk.core.SurfaceTypes.SphereSurfaceType:
            return m.Feature(m.SPHERE, _t(geom.origin), None, geom.radius)
        if st == adsk.core.SurfaceTypes.TorusSurfaceType:
            return m.Feature(m.AXIS, _t(geom.origin), vec.unit(_t(geom.axis)))
        raise m.MateError('Loại mặt này không được hỗ trợ.')

    if isinstance(entity, adsk.fusion.BRepEdge):
        start = entity.startVertex
        end = entity.endVertex
        geom = entity.geometry
        if geom.curveType == adsk.core.Curve3DTypes.Line3DCurveType and start and end:
            p0, p1 = _t(start.geometry), _t(end.geometry)
            return m.Feature(m.AXIS, p0, vec.unit(vec.sub(p1, p0)), is_line=True)
        return _from_curve3d(geom, entity)

    if isinstance(entity, adsk.fusion.BRepVertex):
        return m.Feature(m.POINT, _t(entity.geometry))

    if isinstance(entity, adsk.fusion.ConstructionPoint):
        return m.Feature(m.POINT, _t(entity.geometry))

    if isinstance(entity, adsk.fusion.SketchPoint):
        return m.Feature(m.POINT, _t(entity.worldGeometry))

    if isinstance(entity, adsk.fusion.SketchCurve):
        return _from_curve3d(entity.worldGeometry)

    if isinstance(entity, adsk.fusion.JointOrigin):
        g = entity.geometry
        return m.Feature(m.FRAME, _t(g.origin), vec.unit(_t(g.thirdAxisVector)))

    raise m.MateError('Đối tượng "{}" không được hỗ trợ.'.format(entity.objectType))


def joint_geometry(entity):
    """JointGeometry (or JointOrigin) for an entity, mirroring the Joint command snaps."""
    JG = adsk.fusion.JointGeometry
    KP = adsk.fusion.JointKeyPointTypes
    if isinstance(entity, adsk.fusion.JointOrigin):
        return entity
    if isinstance(entity, adsk.fusion.BRepFace):
        st = entity.geometry.surfaceType
        if st == adsk.core.SurfaceTypes.PlaneSurfaceType:
            return JG.createByPlanarFace(entity, None, KP.CenterKeyPoint)
        if st in (adsk.core.SurfaceTypes.SphereSurfaceType, adsk.core.SurfaceTypes.TorusSurfaceType):
            return JG.createByNonPlanarFace(entity, KP.CenterKeyPoint)
        return JG.createByNonPlanarFace(entity, KP.MiddleKeyPoint)
    if isinstance(entity, (adsk.fusion.BRepEdge, adsk.fusion.SketchCurve)):
        geom = entity.geometry if isinstance(entity, adsk.fusion.BRepEdge) else entity.worldGeometry
        if geom.curveType == adsk.core.Curve3DTypes.Line3DCurveType:
            return JG.createByCurve(entity, KP.MiddleKeyPoint)
        return JG.createByCurve(entity, KP.CenterKeyPoint)
    if isinstance(entity, (adsk.fusion.BRepVertex, adsk.fusion.SketchPoint, adsk.fusion.ConstructionPoint)):
        return JG.createByPoint(entity)
    raise m.MateError('Không tạo được joint geometry cho "{}".'.format(entity.objectType))
