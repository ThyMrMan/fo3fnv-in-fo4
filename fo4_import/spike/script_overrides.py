"""A dependent plugin's changed scripts on the master records that attach them.

A source with masters may override a master's SCPT (YUP's VCG01RemoveDocCarebearModeTriggerSCRIPT) without the
records attaching it. Its conversion compiles under the master's name and wins in game, but the master plugin's
VMAD names the master version's properties. So every record of the built masters whose VMAD attaches such a
script, one the build does not hold, is written as an override: the master's record with that script's entry
rebuilt for the dependent's script. A property both versions declare keeps the master's value; one only the
dependent's declares is filled by the build (ObjectScripts.properties); one it no longer declares goes. A record
whose entry comes out the same, or whose script did not compile, is left alone.

See: docs/fork/fo4_plugin_layout.md#changed-scripts
"""

import struct
from pathlib import Path

from fo4_import.base.dangling_scripts import Unreadable, script_spans
from fo4_import.base.master_overrides import built_bytes
from fo4_import.base.vmad import Unsupported, read_entry
from fo4_import.base.writer import pack_fo4_record
from fo4_import.pipeline.export_index import own_records
from fo4_import.pipeline.master_plugin import layouts
from fo4_import.spike.script import declared_properties, prefix
from script_convert.constants import papyrus_script_name
from script_convert.pipeline import script_entry
from tes5_import.base.tes5_reader import FLAG_COMPRESSED, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: A record's header size.
REC_HDR = 24
#: Top-level types with a VMAD (data/fo4_subrecord_formids.json), not placed, dialogue, package or world records.
SCRIPTED = frozenset(sig for sig, subs in layouts('fo4').items() if b'VMAD' in subs) - {
    b'REFR', b'ACHR', b'PGRE', b'PHZD', b'PMIS', b'PARW', b'PBAR', b'PBEA', b'PCON', b'PFLA', b'INFO', b'PACK',
    b'SCEN', b'CELL', b'WRLD', b'NAVM', b'LAND', b'DIAL'}


def changed_scripts(builder, export_dir: Path, scripts_dir: Path) -> dict:
    """{lower-case name: name} of master SCPTs the plugin overrides."""
    names = (papyrus_script_name(rec.get('EditorID', ''), prefix()) for rec in own_records(export_dir, 'SCPT')
             if not builder.ids.is_own(int(rec['FormID'], 16)))
    return {name.lower(): name for name in names if (scripts_dir / f'{name}.psc').exists()}


def attachers(paths: list, masters: list, scripts: dict) -> dict:
    """{FormID: (signature, flags, body, script name)} of the records in built master plugins `paths` (the last
    holding each, in the numbering of `masters`) whose VMAD attaches one of `scripts` (lower-case names)."""
    out = {}
    for path in paths:
        for rec, _ in walk(built_bytes(path, masters), *SCRIPTED):
            vmad = dict(subrecords(rec.body)).get(b'VMAD')
            names = _spans(rec.sig, vmad) if vmad else []
            found = next((name for name, _, _ in names if name.lower() in scripts), None)
            if found:
                out[rec.form_id] = (rec.sig, rec.flags & ~FLAG_COMPRESSED, rec.body, found)
    return out


def _spans(sig: bytes, vmad: bytes) -> list:
    """script_spans, none for a VMAD the walker cannot follow."""
    try:
        return script_spans(sig, vmad)
    except (Unreadable, struct.error, IndexError, UnicodeDecodeError):
        return []


def master_source(builder, scripts_dir: Path, script: str) -> str:
    """`script`'s source in the last master folder holding it ('')."""
    folders = [scripts_dir.parent / Path(p).name for p in reversed(builder.built)]
    path = next((f / f'{script}.psc' for f in folders if (f / f'{script}.psc').exists()), None)
    return path.read_text(encoding='utf-8') if path else ''


def rebuilt_entry(builder, script: str, master: tuple, sources: tuple) -> 'bytes | None':
    """Script `script`'s entry for the dependent's source, from the master's entry `master` (read_entry's
    (name, objects, values)); `sources`: (dependent's, master's) .psc text. None when it would not change. Names
    match ignoring case, as Papyrus binds them."""
    _, objects, values = master
    declared, before = ({prop.lower(): prop for _, prop in declared_properties(text)} for text in sources)
    kept_objects = {p: f for p, f in objects.items() if p.lower() in declared}
    kept_values = {p: v for p, v in values.items() if p.lower() in declared}
    missing = {prop for low, prop in declared.items() if low not in before}
    filled = {p: f for p, f in builder.scripts.properties(script, missing).items() if f} if missing else {}
    if not filled and (kept_objects, kept_values) == (objects, values):
        return None
    return script_entry(master[0], {**kept_objects, **filled}, kept_values)


def plan(builder, export_dir: Path, scripts_dir) -> None:
    """In a dependent build, `builder.script_overrides`: {FormID: (signature, flags, master body, script, entry)}
    of the master records to override for the plugin's changed scripts, those scripts added to the compile.
    See: docs/fork/fo4_plugin_layout.md#changed-scripts
    """
    builder.script_overrides = {}
    scripts = changed_scripts(builder, export_dir, Path(scripts_dir)) if builder.built and scripts_dir else {}
    builder.counts['master scripts the plugin changes'] = len(scripts)
    found = attachers(builder.built, builder.writer.masters, scripts) if scripts else {}
    for fid, (sig, flags, body, name) in found.items():
        if fid in builder.held:
            continue
        vmad = dict(subrecords(body))[b'VMAD']
        start = next(at for script, at, _ in script_spans(sig, vmad) if script == name)
        try:
            master = read_entry(vmad, start)[0]
        except Unsupported:
            builder.counts[f'changed script left to the master (property not read) ({sig.decode()})'] += 1
            continue
        own = scripts[name.lower()]
        sources = ((Path(scripts_dir) / f'{own}.psc').read_text(encoding='utf-8'),
                   master_source(builder, Path(scripts_dir), own))
        entry = rebuilt_entry(builder, own, master, sources)
        builder.counts[f'master records attaching a changed script ({sig.decode()})'] += 1
        if entry is not None:
            builder.script_overrides[fid] = (sig, flags, body, name, entry)
            builder.scripts.used += [own] if own not in builder.scripts.used else []


def with_entry(sig: bytes, body: bytes, script: str, entry: bytes) -> 'bytes | None':
    """Record body `body` with script `script`'s VMAD entry replaced by `entry`; None when it attaches none."""
    subs = subrecords(body)
    for i, (tag, data) in enumerate(subs):
        if tag != b'VMAD':
            continue
        span = next(((at, end) for name, at, end in _spans(sig, data) if name.lower() == script.lower()), None)
        if span is None:
            return None
        subs[i] = (tag, data[:span[0]] + entry + data[span[1]:])
        return b''.join(pack_subrecord(t.decode('latin1'), d) for t, d in subs)
    return None


def compiled(builder, compiled_dir: Path) -> dict:
    """`builder.script_overrides` whose script compiled into `compiled_dir` (else the master's still runs)."""
    out = {}
    for fid, planned in getattr(builder, 'script_overrides', {}).items():
        if (compiled_dir / f'{planned[3]}.pex').exists():
            out[fid] = planned
        else:
            builder.counts[f'changed script left to the master (did not compile) ({planned[3]})'] += 1
    return out


def apply(builder, compiled_dir: Path) -> None:
    """Write `builder.script_overrides` whose script compiled into `compiled_dir`, once the build's own master
    records are judged (drop_unchanged): a record the build still writes gets the entry in place, else the
    master's record is written with it; counted."""
    todo = compiled(builder, compiled_dir)

    def patch(blob: bytes) -> bytes:
        """`blob` (a record, a quest's children group after it) with its planned entry, if any."""
        fid = struct.unpack_from('<I', blob, 12)[0]
        if fid not in todo or blob[:4] != todo[fid][0]:
            return blob
        sig, _, _, name, entry = todo.pop(fid)
        size, flags = struct.unpack_from('<II', blob, 4)
        body = with_entry(sig, blob[REC_HDR:REC_HDR + size], name, entry) if not flags & FLAG_COMPRESSED else None
        builder.counts['changed script entry set on a written master record' if body else
                       'changed script not set (written record attaches none)'] += 1
        return blob[:4] + struct.pack('<I', len(body)) + blob[8:REC_HDR] + body + blob[REC_HDR + size:] if body else blob
    for sig in {value[0] for value in todo.values()}:
        builder.writer.patch_records(sig.decode(), patch)
    for fid, (sig, flags, body, name, entry) in todo.items():
        builder.writer.add_record(sig.decode(), pack_fo4_record(sig.decode(), fid, flags,
                                                                with_entry(sig, body, name, entry)))
        builder.counts[f'master records overridden for a changed script ({sig.decode()})'] += 1
