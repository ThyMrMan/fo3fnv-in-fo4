"""FNV guns on FNV's own meshes over a Fallout 4 gun's parts, for the cell spike.

A FO4 gun is a dummy receiver mesh plus object mods (OMOD) the record's
default object template combination attaches: receiver, grip, barrel,
magazine, sights, muzzle. A converted FNV gun is built on the FO4 gun
spike.gun_choice picks (held and fired alike, laid out nearest), keeping
that combination, with the receiver and grip it chose, as copies. The
receiver's copy shows the FNV gun built on that receiver's skeleton
(nif.gun) and moves the aiming camera by how much higher FNV's eye point
(##SightingNode) sits above the trigger than the template's sights (its
P-Scope point plus the top of the sights part there); the other parts with a model keep
their stats and drop the model, as FNV's mesh has those parts; parts
without a model stay vanilla's. The record's other combinations go.
Vanilla's mods are untouched. A copy's FormID is hashed from the FNV gun
and the attach point (no combination holds two parts with a model at one),
so another vanilla part chosen there keeps it. Choosing reads the FNV
mesh's conversion only; its mesh, materials and textures are written for a
gun built on it (templates).

When the FO4 gun's graph takes FNV's own clips (havok.gun_clips: a
table entry naming the gun, a keyword-only subgraph entry, FNV clips for
the class), the mesh keeps FNV's placement in the hand instead of the
trigger match, the camera lift puts FNV's eye point on the camera, and the
record trades the template's Anims keyword for its own (anim_keywords),
which an additive race maps to the clips (write_subgraphs).

See: docs/fork/fo4_spikes.md#spike-4-guns
See: docs/fork/fo4_spikes.md#spike-4-gun-clips
"""

import struct
from dataclasses import replace

import numpy as np

from asset_convert.havok.gun_vocabulary_falloutnv import FNV_BACKPACK
from fo4_import.base.ba2 import Archives
from fo4_import.base.install import FALLOUT4_DIR
from fo4_import.base.writer import pack_fo4_record
from fo4_import.havok.gun_clips import GunClips
from fo4_import.nif import file as nif_file
from fo4_import.nif import gun
from fo4_import.pipeline.elric_cache import write_new
from fo4_import.pipeline.mesh_cache import cached_convert
from fo4_import.spike.gun_choice import (FNV_SCOPE_VIEW, INCLUDE_SIZE, OBTS_DEFAULT, PROPERTY_SIZE, Choice, GunChoices,
                                         includes, includes_at, properties, traded, weapon_model)
from fo4_import.spike.records import pack_kywd
from fo4_import.spike.statics import write_assets
from tes5_import.base.tes5_reader import first_sub, subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: The built gun's file beside the plain conversion, which FNV's statics and misc items may share.
GUN_SUFFIX = '_gun.nif'
#: derive_formid site of a copied mod (key: the FNV gun's FormID and its attach point's EditorID, one part each).
SITE = 'FNV OMOD'
#: The loose mod item, dropped from a copied mod (with its model data, and a non-receiver's model).
LOOSE = b'LNAM'
LOCALIZED = (b'FULL', b'DESC')
#: The receiver copy's added property: float, ADD, ZoomDataCameraOffsetZ (xEdit's wbWeaponPropertyEnum 72).
CAMERA_Z = struct.Struct('<B3xB3xH2xfIf')
FLOAT, ADD, PROP_CAMERA_Z = 1, 2, 72
#: OMOD property OverrideProjectile (xEdit's wbWeaponPropertyEnum 80); a property's kind is at 8.
PROP_OVERRIDE_PROJECTILE = 80
#: derive_formid sites of a gun's own Anims keyword (key: its FNV FormID) and of the one additive subgraph race.
KEYWORD_SITE, RACE_SITE = 'FNV gun anims KYWD', 'FNV gun anims RACE'
RACE_EDID = 'FNV_HumanRaceSubGraphDataAdditive'
#: ZOOM GNAM: its camera offset's z (after FOV mult, overlay, imagespace modifier, x, y).
ZOOM_CAMERA_Z = 20


class Guns:
    """FO4 object template subrecords that put FNV guns on their own meshes, each part copy written once."""

    def __init__(self, builder, strings: dict):
        """Index Fallout4.esm's mods and guns; `strings` resolves their localized names."""
        self.builder, self.strings, self.archives, self.receivers = builder, strings, None, {}
        self.mods = {rec.form_id: list(subrecords(rec.body)) for rec, _ in walk(builder.fo4, b'OMOD')}
        self.choices = GunChoices(builder.fo4, self.mods, builder.keywords, self._receiver_layout)
        self.edids = {dict(subs).get(b'EDID', b'').rstrip(b'\0').decode('cp1252'): fid for fid, subs in self.mods.items()}
        self.clips, self.converted, self.bodies = None, {}, {}

    def _read(self, model: str) -> bytes:
        """A vanilla mesh from the game's archives."""
        if self.archives is None:
            self.archives = Archives(FALLOUT4_DIR / 'Data')
        return self.archives.read('meshes\\' + model.lower())

    def _receiver_layout(self, model: str) -> dict:
        """A vanilla receiver mesh's layout (nif.gun.receiver_layout), read once."""
        if model not in self.receivers:
            self.receivers[model] = gun.receiver_layout(self._read(model))
        return self.receivers[model]

    def choose(self, rec: dict, only: 'str | None' = None, mods: tuple = ()) -> 'tuple | None':
        """(the FO4 gun to build FNV gun `rec` on (FO4 EditorID `only` when given, with the table's `mods` in
        its default combination: modded), its record subrecords, the FNV mesh's model, path, converted NIF (not
        written) and layout); None when no FO4 gun matches."""
        model = rec['Model.MODL']
        fnv_path = self.builder.export_dir / 'meshes' / model.replace('\\', '/').lower()
        static = nif_file.write(cached_convert(fnv_path, self.builder.export_dir, None, False).nif)
        if int(rec.get('DNAM.Flags1', 0)) & FNV_BACKPACK:
            static = gun.without(static, gun.BACKPACK)
        nodes = gun.fnv_nodes(fnv_path)
        layout = gun.fnv_layout(static, nodes)
        choice = self.choices.choose(rec, layout, only)
        if choice is None:
            return None
        subs = self.choices.weapons[choice.weapon][1]
        choice = self._modded_choice(choice, subs, mods) if mods else choice
        if int(rec.get('DNAM.Flags1', 0)) & FNV_SCOPE_VIEW == FNV_SCOPE_VIEW:
            choice = replace(choice, includes=self.choices.scoped(subs, choice.includes,
                                                                    float(rec.get('DNAM.SightFOV', 0.0))))
        body = weapon_model(subs)
        if choice.receiver is not None and body and gun.draws(self._read(body)):
            choice = replace(choice, receiver=None, model=body, layout=self._receiver_layout(body))
        return choice, subs, (model, fnv_path, static, nodes, layout)

    def templates(self, fnv: int, rec: dict, choice: Choice, template: list, fnv_mesh: tuple, own: bool) -> list:
        """The object template subrecords for FNV gun `rec` (FormID `fnv`) on `choice`, `template` its record's
        subrecords, `fnv_mesh` choose()'s converted mesh, whose assets are written now, as only this uses them;
        `own`: the copies drop their OverrideProjectile (the gun flies its own)."""
        name, obts = _default(template)
        model, fnv_path, static, nodes, layout = fnv_mesh
        path, _ = write_assets(self.builder.export_dir, model, self.builder.data_dir, animated=False)
        out_path = path[:-len('.nif')] + GUN_SUFFIX
        receiver = self._read(choice.model)
        matrix = gun.placement(static, nodes, receiver)
        made = gun.gun(static, nodes, receiver, matrix)
        clips = self._clips(fnv, rec, (template, choice.includes), fnv_path, receiver, (made, matrix))
        write_new(self.builder.data_dir / 'Meshes' / out_path, made)
        if choice.receiver is None:
            self.bodies[fnv] = out_path
        out, start = bytearray(obts), includes_at(obts)
        lift = self._lift(layout, choice) if clips is None else self._clip_lift(clips.lift, template)
        for i, fid in enumerate(choice.includes):
            made = self._part(fnv, rec, fid, out_path if fid == choice.receiver else None, lift, own)
            struct.pack_into('<I', out, start + INCLUDE_SIZE * i, made)
        return self._block(name, bytes(out))

    def gun_clips(self) -> GunClips:
        """The clip converter, made on first use."""
        if self.clips is None:
            self.clips = GunClips(self.builder.fo4, self.builder.export_dir / 'meshes', self.builder.data_dir)
        return self.clips

    def _clips(self, fnv: int, rec: dict, template: tuple, fnv_path, receiver: bytes, mesh: tuple):
        """FNV gun `rec`'s clips (`mesh`: its FO4 mesh and placement, on `receiver`) written
        on `template`'s graph (its subrecords and default combination) and its own Anims keyword records
        (gun_clips), or None when they do not convert."""
        subs, combo = template
        own = lambda old: self.builder.writer.derive_formid(KEYWORD_SITE, f'{fnv:08X} {old:08X}')
        keywords = self.choices.clip_keywords(subs, combo)
        made = self.gun_clips().convert(rec, keywords, own, fnv_path,
                                  gun.receiver_bones(receiver), mesh[1], (gun.pieces(mesh[0]), gun.pieces(receiver)))
        if made is None:
            return None
        olds = {r.form_id: r for r, _ in walk(self.builder.fo4, b'KYWD') if r.form_id in made.replaces}
        for old, keyword in made.replaces.items():
            name = first_sub(olds[old].body, b'EDID').rstrip(b'\0').decode('cp1252')
            self.builder.writer.add_record('KYWD', pack_kywd(keyword, f'FNV_{name}_{rec["EditorID"]}', struct.unpack(
                '<I', first_sub(olds[old].body, b'TNAM'))[0]))
        self.builder.counts['guns on FNV clips'] += 1
        self.converted[fnv] = made
        return made

    def _clip_lift(self, eye: 'float | None', template: list) -> float:
        """The camera lift putting FNV's eye point (`eye`, its height over the camera in the sighted clip) on the
        camera, less what the template's zoom data already moves it; 0 without one."""
        if eye is None:
            return 0.0
        zoom = dict(template).get(b'WZMD')
        gnam = next((first_sub(r.body, b'GNAM') for r, _ in walk(self.builder.fo4, b'ZOOM')
                     if zoom and r.form_id == struct.unpack('<I', zoom)[0]), None)
        return eye - (struct.unpack_from('<f', gnam, ZOOM_CAMERA_Z)[0] if gnam else 0.0)

    def body(self, fnv: int) -> dict:
        """MODL and MOD4 as gun `fnv`'s mesh when it is its FO4 gun's body, else {}."""
        path = (self.bodies[fnv] + '\0').encode() if fnv in self.bodies else None
        return {b'MODL': path, b'MOD4': path} if path else {}

    def anim_keywords(self, fnv: int, template: list) -> dict:
        """{b'KWDA': `template`'s keywords with each Anims keyword its clips replace traded for FNV gun `fnv`'s own}
        when its clips converted, else {}."""
        made = self.converted.get(fnv)
        if made is None:
            return {}
        kwda = dict(template)[b'KWDA']
        ids = [made.replaces.get(k, k) for k in struct.unpack(f'<{len(kwda) // 4}I', kwda)]
        return {b'KWDA': struct.pack(f'<{len(ids)}I', *ids)}

    def write_subgraphs(self) -> None:
        """The additive race mapping every converted gun's keyword to its clips (none when no gun converted)."""
        subs = self.clips.race(RACE_EDID) if self.clips else None
        if subs:
            fid = self.builder.writer.derive_formid(RACE_SITE, RACE_EDID)
            self.builder.writer.add_record('RACE', pack_fo4_record('RACE', fid, 0, b''.join(
                pack_subrecord(s.decode(), b) for s, b in subs)))

    def own_projectile(self, fnv: int, rec: dict, block: list) -> list:
        """Object template `block` of FNV gun `rec` with each vanilla part setting OverrideProjectile a copy without it,
        so the gun's FNAM override flies.
        See: docs/fork/fo4_pipeline.md#nv-ammo
        """
        out = []
        for sig, body in block:
            if sig == b'OBTS':
                obts, start = bytearray(body), includes_at(body)
                for i, fid in enumerate(includes(body)):
                    if fid in self.mods and overrides_projectile(dict(self.mods[fid]).get(b'DATA', bytes(8))):
                        subs = [(s, b if s in (b'MODL', b'MODT') else self._part_sub(s, b, rec, None, 0.0, True))
                                for s, b in self.mods[fid] if s != LOOSE]
                        struct.pack_into('<I', obts, start + INCLUDE_SIZE * i, self._add_copy(fnv, fid, subs))
                body = bytes(obts)
            out.append((sig, body))
        return out

    def modded(self, template: list, mods: tuple) -> list:
        """`template`'s default combination's parts with `mods` (OMOD EditorIDs) in place of those at their
        attach points."""
        combo = includes(_default(template)[1])
        for mod in mods:
            if mod not in self.edids:
                raise ValueError(f'no object mod {mod} in Fallout4.esm')
            new = self.edids[mod]
            combo = [new if self.choices.attach(f) == self.choices.attach(new) else f for f in combo]
        return combo

    def _modded_choice(self, choice: Choice, template: list, mods: tuple) -> Choice:
        """`choice` with the table's `mods` in its parts, a swapped receiver's model and layout taken."""
        combo = tuple(self.modded(template, mods))
        if choice.receiver is None or choice.receiver in combo:
            return replace(choice, includes=combo)
        point = self.choices.attach(choice.receiver)
        receiver = next(f for f in combo if self.choices.attach(f) == point)
        model = self.choices.model(receiver)
        return replace(choice, includes=combo, receiver=receiver, model=model, layout=self._receiver_layout(model))

    def with_mods(self, template: list, mods: tuple) -> list:
        """`template`'s object template: its default combination, `mods` in."""
        return self.combination(template, self.modded(template, mods))

    def combination(self, template: list, parts: list) -> list:
        """The object template subrecords of `template`'s default combination with its parts set to `parts`."""
        name, obts = _default(template)
        out, start = bytearray(obts), includes_at(obts)
        for i, fid in enumerate(parts):
            struct.pack_into('<I', out, start + INCLUDE_SIZE * i, fid)
        return self._block(name, bytes(out))

    def default_only(self, template: list) -> 'list | None':
        """`template`'s object template cut to its default combination; None for a record without one.
        See: docs/fork/fo4_spikes.md#spike-4-equipment
        """
        if not any(sig == b'OBTS' for sig, _ in template):
            return None
        return self._block(*_default(template))

    def _block(self, name: bytes, obts: bytes) -> list:
        """An object template of one combination: its name (a string ID resolved) and OBTS."""
        name = self.strings.get(struct.unpack('<I', name)[0], b'') + b'\0' if len(name) == 4 else name
        return [(b'OBTE', struct.pack('<I', 1)), (b'OBTF', b''), (b'FULL', name), (b'OBTS', obts), (b'STOP', b'')]

    def _lift(self, ours: dict, choice: Choice) -> float:
        """How much higher FNV's eye point sits above its trigger than the template's sights; 0 without both."""
        theirs, scope = choice.layout, self.choices.scope(choice.includes)
        if ours['sight'] is None or theirs['scope'] is None or theirs['trigger'] is None:
            return 0.0
        sight = float(theirs['scope'][2]) + (gun.mesh_top(self._read(self.choices.model(scope))) if scope else 0.0)
        trigger_ours = ours['trigger'][2] if ours['trigger'] is not None else 0.0
        return float(ours['sight'][2] - trigger_ours) - (sight - float(theirs['trigger'][2]))

    def _part_sub(self, sig: bytes, body: bytes, rec: dict, path: 'str | None', lift: float, own: bool) -> bytes:
        """A copied mod's subrecord: EditorID with FNV's gun, model `path`, strings as text; DATA loses its
        OverrideProjectile when `own`, and the receiver's (when `path`) gains the camera lift."""
        if sig == b'EDID':
            return b'FNV_' + body.rstrip(b'\0') + f'_{rec["EditorID"]}\0'.encode()
        if sig == b'MODL':
            return (path + '\0').encode()
        if sig in LOCALIZED and len(body) == 4:
            return self.strings.get(struct.unpack('<I', body)[0], b'') + b'\0'
        body = without_override(body) if sig == b'DATA' and own else body
        if sig == b'DATA' and path:
            data = bytearray(body)
            struct.pack_into('<I', data, 4, struct.unpack_from('<I', data, 4)[0] + 1)
            return bytes(data) + CAMERA_Z.pack(FLOAT, ADD, PROP_CAMERA_Z, float(np.float32(lift)), 0, 0.0)
        return body

    def _part(self, fnv: int, rec: dict, fid: int, path: 'str | None', lift: float, own: bool) -> int:
        """The mod the converted gun includes for vanilla mod `fid`: a copy (the receiver's, `path` given,
        showing it), another with a model losing it, one adding an Anims keyword the gun's clips replace taking
        the gun's own (gun_choice.traded)), or `fid` itself for any other mod without a model."""
        made = self.converted.get(fnv)
        trades = made.replaces if made else {}
        if not self.choices.model(fid) and not self.choices.keywords([], (fid,)) & set(trades):
            return fid
        out = [(sig, self._part_sub(sig, body, rec, path, lift, own)) for sig, body in self.mods.get(fid, [])
               if sig not in (LOOSE, b'MODT') and (sig != b'MODL' or path)]
        return self._add_copy(fnv, fid, [(sig, traded(body, trades) if sig == b'DATA' else body) for sig, body in out])

    def _add_copy(self, fnv: int, fid: int, out: list) -> int:
        """Write `out` as FNV gun `fnv`'s copy of vanilla mod `fid` (one per attach point); its FormID."""
        point = self.choices.names[self.choices.attach(fid)]
        copy = self.builder.writer.derive_formid(SITE, f'{fnv:08X} {point}')
        self.builder.writer.add_record('OMOD', pack_fo4_record('OMOD', copy, 0, b''.join(
            pack_subrecord(s.decode(), b) for s, b in out)))
        self.builder.counts['OMOD'] += 1
        return copy


def _default(template: list) -> tuple:
    """(the default combination's FULL, its OBTS) of a record's object template."""
    name = b''
    for sig, body in template:
        if sig == b'FULL':
            name = body
        elif sig == b'OBTS' and body[OBTS_DEFAULT]:
            return name, body
    raise ValueError('no default object template combination')


def overrides_projectile(data: bytes) -> bool:
    """Whether an OMOD DATA sets OverrideProjectile."""
    return any(prop == PROP_OVERRIDE_PROJECTILE for _, _, prop, _ in properties(data))


def without_override(data: bytes) -> bytes:
    """An OMOD DATA without its OverrideProjectile properties (they end it)."""
    count = struct.unpack_from('<I', data, 4)[0]
    start = len(data) - PROPERTY_SIZE * count
    kept = [data[start + PROPERTY_SIZE * i:start + PROPERTY_SIZE * (i + 1)] for i in range(count)
            if struct.unpack_from('<H', data, start + PROPERTY_SIZE * i + 8)[0] != PROP_OVERRIDE_PROJECTILE]
    head = bytearray(data[:start])
    struct.pack_into('<I', head, 4, len(kept))
    return bytes(head) + b''.join(kept)
