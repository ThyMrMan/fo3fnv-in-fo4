"""List Fallout 4's own animation props: the clips that load each, its bone and its start events.

    py -3.14 -m tools.creature.vanilla_anim_props [--object SUBSTR] [--clips N] [--json OUT]

Feeds `fo4_import/data/anim_props.json`, which swaps an FNV prop mesh for a vanilla one.
See: docs/fork/fo4_idles.md#props
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from external.pynifly_hkx.anim_fo4 import fo4_animation_header
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.havok.anim_props import ANIMATIONS, DRAW, LOAD
from fo4_import.pipeline.export_index import export_records

FALLOUT4_EXPORT = 'references/Fallout4.esm'
#: The prop bones of FO4's human skeleton, as a prop mesh's Prn names them.
PRN_BONE = re.compile(rb'AnimObject(?:[LR][123]|[AB])(?![A-Za-z0-9])')
#: Events this close to the draw count as the prop's start events.
START_WINDOW = 0.1


def prop_bone(meshes, model):
    """The prop bone a vanilla prop mesh's Prn names, or '' when it has none."""
    try:
        found = PRN_BONE.search(meshes.read('meshes\\' + model))
    except KeyError:
        return ''
    return found.group().decode() if found else ''


def clip_props(raw):
    """{object: (draw time or None, events beside the draw)} for one clip's annotations."""
    head = fo4_animation_header(raw)
    notes = head.annotations if head else []
    props = {}
    for note in notes:
        if note.text.startswith(LOAD):
            props.setdefault(note.text[len(LOAD):], None)
    for obj in props:
        draw = next((n.time for n in notes if n.text == DRAW + obj), None)
        after = [n.text for n in notes if draw is not None and abs(n.time - draw) <= START_WINDOW
                 and not n.text.startswith(('AnimObj', 'SoundPlay.'))]
        props[obj] = (draw, after)
    return props


def scan(anims, match=''):
    """{object: [(clip, draw time, start events)]} over every clip naming a matching object."""
    found = defaultdict(list)
    for name in anims.names('meshes\\actors\\'):
        if not name.endswith('.hkx'):
            continue
        raw = anims.read(name)
        if LOAD.encode() not in raw:
            continue
        for obj, (draw, after) in clip_props(raw).items():
            if match.lower() in obj.lower():
                found[obj].append((name[len('meshes\\'):], draw, after))
    return found


def report(found, limit):
    """One entry per object: its model, prop bone, clip count, start events and the clips."""
    models = {r.get('EditorID', ''): r.get('MODL', '') for r in export_records(FALLOUT4_EXPORT, 'ANIO')}
    meshes = Archives(FALLOUT4_DIR / 'Data', 'Fallout4 - Meshes.ba2')
    rows = []
    for obj, clips in sorted(found.items()):
        starts = sorted({e for _, _, after in clips for e in after})
        clips.sort(key=lambda c: (c[1] is None, c[1] or 0.0, c[0]))
        rows.append({'object': obj, 'model': models.get(obj, ''), 'bone': prop_bone(meshes, models.get(obj, '')),
                     'clip_count': len(clips), 'start': starts,
                     'clips': [{'clip': c, 'draw': d} for c, d, _ in clips[:limit]]})
    return rows


def main(argv=None):
    """Scan the vanilla animations and print (or write) each prop object's entry."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--object', default='', help='only objects whose EditorID contains this')
    ap.add_argument('--clips', type=int, default=5, help='clips listed per object, earliest draw first')
    ap.add_argument('--json', type=Path, help='write the entries here instead of printing')
    args = ap.parse_args(argv)
    rows = report(scan(Archives(FALLOUT4_DIR / 'Data', ANIMATIONS), args.object), args.clips)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=1), encoding='utf-8')
        print(len(rows), 'objects ->', args.json)
        return
    for row in rows:
        print(f"{row['object']}  {row['model']}  bone={row['bone'] or '?'}  clips={row['clip_count']}"
              f"  start={','.join(row['start']) or '-'}")
        for clip in row['clips']:
            print(f"    draw={clip['draw']}  {clip['clip']}")


if __name__ == '__main__':
    main()
