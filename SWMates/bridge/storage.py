"""Persist the SolidWorks-style mate stack of a joint in Fusion attributes.

Each managed joint (or as-built joint) carries one attribute whose value is a
JSON document with the list of mates between its two occurrences. Entities are
stored as (native entity token, occurrence full path) so they can be resolved
again later, e.g. when another mate is added to the same pair.
"""

import json

import adsk.core
import adsk.fusion

from ..core import mates as m

GROUP = 'SWMates'
NAME = 'stack'
VERSION = 1


def occurrence_path(occ):
    return occ.fullPathName


def entity_ref(entity, occ):
    native = getattr(entity, 'nativeObject', None)
    if native is None:
        native = entity
    return {'tok': native.entityToken, 'occ': occurrence_path(occ)}


def make_record(options, anti_aligned, ent1, occ1, ent2, occ2):
    return {
        'opts': options.to_dict(),
        'anti': bool(anti_aligned),
        'e1': entity_ref(ent1, occ1),
        'e2': entity_ref(ent2, occ2),
    }


def swap_record(rec):
    out = dict(rec)
    out['e1'], out['e2'] = rec['e2'], rec['e1']
    return out


def find_occurrence(design, path):
    for occ in design.rootComponent.allOccurrences:
        if occ.fullPathName == path:
            return occ
    return None


def resolve(design, ref):
    """Return (proxy entity, occurrence) for a stored reference."""
    occ = find_occurrence(design, ref['occ'])
    if occ is None:
        raise m.MateError('Không tìm thấy component "{}".'.format(ref['occ']))
    found = design.findEntityByToken(ref['tok'])
    if not found:
        raise m.MateError('Không tìm thấy hình học đã mate trên "{}" (có thể đã bị xóa).'.format(ref['occ']))
    native = found[0]
    if getattr(native, 'assemblyContext', None) is not None:
        native = native.nativeObject
    return native.createForAssemblyContext(occ), occ


def read_records(joint):
    attr = joint.attributes.itemByName(GROUP, NAME)
    if attr is None:
        return None
    try:
        data = json.loads(attr.value)
    except ValueError:
        return None
    return data.get('mates') or None


def write_records(joint, records):
    joint.attributes.add(GROUP, NAME, json.dumps({'version': VERSION, 'mates': records}))


def pair_of(records):
    first = records[0]
    return first['e1']['occ'], first['e2']['occ']


def managed_joints(design):
    """All joints created by this add-in: list of (joint, records)."""
    root = design.rootComponent
    result = []
    for coll in (root.allJoints, root.allAsBuiltJoints):
        for joint in coll:
            records = read_records(joint)
            if records:
                result.append((joint, records))
    return result


def find_group(design, path1, path2):
    """Existing managed joint between the two occurrences.

    Returns (joint, records, swapped) or None. ``swapped`` is True when the
    stored order is (path2, path1).
    """
    for joint, records in managed_joints(design):
        a, b = pair_of(records)
        if (a, b) == (path1, path2):
            return joint, records, False
        if (a, b) == (path2, path1):
            return joint, records, True
    return None
