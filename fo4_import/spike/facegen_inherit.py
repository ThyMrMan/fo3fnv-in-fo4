"""Faces of the NPCs a plugin overrides. The faces stage patches sliders and skin tone (PATCHED) only into the
records of the plugin that adds an NPC, and FO4 draws an override with FaceGen under that plugin's folder name.
So every converted face (FMRI) a plugin overrides takes the adding plugin's patched values, matching the FaceGen
drawn, but one whose authored FNV face (face_fits.FIT_FIELDS, sex, head parts) differs from the adding plugin's
(changed): the stage gives it FaceGen of its own under that folder name in the mod, and its own values. An
override the FNV plugin does not hold was made by the converter from the master's record: the same face. FO4
FormIDs are hashed, so FNV records pair by EditorID.

See: docs/fork/fo4_facegen_plan.md#addon-faces
"""

import functools
from pathlib import Path

from fo4_import.base.ba2_pack import archived_names
from fo4_import.base.source import plugin_name, record_dir
from fo4_import.face import facegeom, own_facegen
from fo4_import.pipeline.export_index import master_names, own_records
from fo4_import.spike import facegen_skin
from fo4_import.spike.face_fits import FIT_FIELDS
from fo4_import.spike.fnv_npc import head_parts
from tes5_import.base.tes5_reader import masters, subrecords, walk

#: The NPC fields the faces stage patches: sliders (refine) and skin tone (skin).
PATCHED = (b'FMRS', b'MSDV', b'QNAM', b'TEND')
#: The FIT_FIELDS holding a FormID.
FORM_FIELDS = ('RNAM.Race', 'HNAM.Hair', 'ENAM.Eyes')


@functools.cache
def fnv_npcs(folder: str) -> dict:
    """{EditorID: record} of the NPC_ records export `folder`'s plugin holds."""
    return {r['EditorID']: r for r in own_records(folder, 'NPC_') if 'EditorID' in r}


def named(text: str, names: list) -> tuple:
    """Export FormID `text` as (plugin, local id); `names`: masters, plugin."""
    form_id = int(text, 16)
    return names[min(form_id >> 24, len(names) - 1)], form_id & 0xFFFFFF


def authored_face(folder: str, edid: str) -> 'tuple | None':
    """(FIT_FIELDS, FormIDs named; female; head parts) of NPC_ `edid` as export `folder`'s plugin holds it; None
    when it holds none."""
    npc = fnv_npcs(folder).get(edid)
    if npc is None:
        return None
    names = [n.lower() for n in (*master_names(folder), plugin_name(folder))]
    fields = tuple(named(npc[k], names) if k in FORM_FIELDS and npc.get(k) else npc.get(k, '') for k in FIT_FIELDS)
    parts = tuple(head_parts(Path(folder), int(npc['FormID'], 16)))
    return fields, int(npc.get('ACBS.Flags', '0')) & facegen_skin.FEMALE, parts


@functools.cache
def fo4_npcs(path: Path) -> dict:
    """{local id: [(tag, data)]} of the NPC_ records the FO4 plugin at `path` adds."""
    data = path.read_bytes()
    slot = len(masters(data))
    return {r.form_id & 0xFFFFFF: list(subrecords(r.body)) for r, _ in walk(data, b'NPC_') if r.form_id >> 24 == slot}


def same_face(export_dir: Path, owner: str, edid: str) -> bool:
    """Whether `export_dir`'s plugin keeps `owner`'s face of NPC `edid` (module doc)."""
    fnv = [n.lower() for n in master_names(export_dir)]
    theirs = authored_face(str(record_dir(export_dir, master_names(export_dir)[fnv.index(owner)])), edid)
    return theirs is not None and authored_face(str(export_dir), edid) in (None, theirs)


def fnv_edid(subs: list) -> str:
    """A converted NPC_'s FNV EditorID (EDID less FNV_PREFIX), else ''."""
    edid = facegeom.zstr(dict(subs).get(b'EDID', b'\0'))
    return edid[len(own_facegen.FNV_PREFIX):] if edid.startswith(own_facegen.FNV_PREFIX) else ''


def copy_edit(master: list, missed: list, form_id: int):
    """An edit writing `master`'s PATCHED subrecords over the record's, in order; `form_id` noted in `missed`
    instead when they don't pair by tag and size."""
    def edit(raw: bytearray, subs: list) -> None:
        """Copy the master's patched fields."""
        mine, theirs = [s for s in subs if s[0] in PATCHED], [s for s in master if s[0] in PATCHED]
        if [(t, size) for t, _, size in mine] != [(t, len(d)) for t, d in theirs]:
            missed.append(form_id)
            return
        for (_, at, size), (_, data) in zip(mine, theirs):
            raw[at:at + size] = data
    return edit


def overridden(data_dir: Path, plugin: str, export_dir: Path) -> list:
    """[(FormID, master's name, master's subrecords, FNV EditorID, changes the face)] of every converted face
    (FMRI) the plugin overrides of an FNV master's (module doc)."""
    data, dirs = (data_dir / plugin).read_bytes(), facegen_skin.profile_dirs(data_dir)[0]
    own, fnv, out = masters(data), {n.lower() for n in master_names(export_dir)}, []
    for rec, _ in walk(data, b'NPC_'):
        owner, subs = (own + [None])[min(rec.form_id >> 24, len(own))], list(subrecords(rec.body))
        master = fo4_npcs(own_facegen.find(dirs, owner)).get(rec.form_id & 0xFFFFFF) if owner in fnv else None
        if master is not None and b'FMRI' in dict(subs):
            edid = fnv_edid(subs)
            out.append((rec.form_id, owner, master, edid, not same_face(export_dir, owner, edid)))
    return out


def changed(data_dir: Path, plugin: str, export_dir: Path) -> dict:
    """{master's name: [local ids]} of the faces the plugin's overrides change (overridden)."""
    out = {}
    for form_id, owner, *_, changes in overridden(data_dir, plugin, export_dir):
        if changes:
            out.setdefault(owner, []).append(form_id & 0xFFFFFF)
    return out


def geom_path(owner: str, form_id: int) -> Path:
    """Where FaceGeom NIF of master `owner`'s NPC `form_id` lies under Data."""
    return own_facegen.GEOM_DIR / owner / f'{form_id & 0xFFFFFF:08X}.nif'


def inherit(data_dir: Path, plugin: str, export_dir: Path, packed: bool = False) -> list:
    """Give every converted face the plugin overrides its master's patched values (module doc), but a changed one
    with FaceGen of its own in the mod folder (loose, or with `packed` in its archives); report lines.
    See: docs/fork/fo4_facegen_plan.md#override-faces
    """
    names = archived_names(data_dir) if packed else set()
    edits, missed, lines, drawn = {}, [], [], 0
    for form_id, owner, master, edid, changes in overridden(data_dir, plugin, export_dir):
        path = geom_path(owner, form_id)
        if changes and ((data_dir / path).is_file() or path.as_posix().lower() in names):
            drawn += 1
            continue
        if changes:
            lines.append(f'{form_id:08X} {edid} changes its face from {owner}\'s, whose FaceGen it is drawn with')
        edits[form_id] = copy_edit(master, missed, form_id)
    facegen_skin.patch(data_dir / plugin, edits)
    lines += [f'{fid:08X} keeps its own face values: its fields do not pair with its master\'s' for fid in missed]
    return lines + [f'overridden faces given their master\'s values: {len(edits) - len(missed)} of {len(edits)}',
                    f'overridden faces drawn with FaceGen of their own: {drawn}']
