"""An own-rig creature's records, copied from its template race's: RACE on the creature's project and one root
subgraph entry, BPTD on its bones, the skin ARMO/ARMA on its body, a MOVT linked to the graph's iState_<project>, and
an IDLE per actor action the graph answers.

See: docs/fork/fo4_own_rig.md#modules
"""

import functools
import operator
import struct
from dataclasses import replace

from fo4_import.base.install import source_walk
from fo4_import.base.writer import pack_fo4_record
from fo4_import.rig.behavior import fire_start
from fo4_import.rig.table import weapon_node
from fo4_import.spike.creature_attacks import ATKD, POWER, weights
from fo4_import.spike.records import pack_ctda
from fo4_import.spike.void_actors import copy_record, with_race_flags
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

SITE = 'FNV RIG'
#: The vanilla graphs whose IDLEs lend their DATA, first wins: the cat's, eyebot's, turrets' (fire single, auto).
IDLE_GRAPHS = ('catrootbehavior.hkx', 'eyebotrootbehavior.hkx', 'turretsharedbehavior.hkx')
#: The actions a ranged rig adds (FO4 fires a creature's gun, automatic or not, from these, not attack data).
RANGED_ACTIONS = ('ActionFireSingle', 'ActionFireAuto')
#: Condition function GetActionDataByte: the firing gun's equip slot, which the robots' fire IDLEs branch on.
GET_ACTION_DATA_BYTE = 747
#: FO4 actor-type keywords per FNV creature type (type_tests.CREATURE_TYPES order), as vanilla's races group them.
ACTOR_TYPES = (('ActorTypeAnimal', 'ActorTypeCreature'), ('ActorTypeAnimal', 'ActorTypeCreature'),
               ('ActorTypeBug', 'ActorTypeCreature'), ('ActorTypeCreature',), ('ActorTypeSuperMutant',),
               ('ActorTypeCreature', 'ActorTypeFeralGhoul'), ('ActorTypeRobot',), ('ActorTypeCreature',))
#: RACE DATA flag Allow PC Dialogue, set on a rig race when FNV lets one of its creatures talk (ACBS bit 21).
ALLOW_PC_DIALOGUE = 0x200000
#: RACE VNAM equip type Gun: a ranged rig's race may equip its guns (the bubble turret's flags are the mole rat's + it).
EQUIP_GUN = 0x200
#: Actor action -> the root graph event its IDLE sends (an action without one is unsupported, so nothing happens).
ACTIONS = {'ActionMoveStart': 'moveStart', 'ActionMoveStop': 'moveStop', 'ActionTurnLeft': 'turnLeft',
           'ActionTurnRight': 'turnRight', 'ActionTurnStop': 'turnStop', 'ActionDraw': 'weapEquip',
           'ActionForceEquip': 'weapEquip', 'ActionSheath': 'weapUnequip', 'ActionDeath': 'Ragdoll',
           'ActionDeathWait': 'DeathAnimation', 'ActionRagdollInstant': 'Ragdoll', 'ActionKnockDown': 'Ragdoll',
           'ActionGetUp': 'GetUpBegin', 'ActionTalking': 'dyn_talkGeneric', 'ActionInitializeGraphToBaseState': 'g_InitializeGraph',
           'ActionInstantInitializeGraphToBaseState': 'g_InitializeGraphInstant'}
#: Attack aim: the angle the attack strikes within (all of an own-rig creature's attacks).
STRIKE_ANGLE = 35.0
#: Body part data flags kept: hit reactions only (no severing, exploding or cripple geometry).
PART_FLAGS_KEPT = 0x06
BPND_FLAGS = 64
#: The engine's forward sprint factor when it upgrades an old 17-float SPED (Fallout4.exe 0x24D1A00).
SPRINT = 1.75
#: A template race's subgraph entries or subgraph template race (SRAC), all replaced by the rig's one entry.
SUBGRAPH_TAGS = (b'SGNM', b'SAPT', b'SRAF', b'STKD', b'SADD', b'SRAC')
#: Template race fields left out: its equip slot nodes (race() names its guns'), its movement type (the rig's MOVT).
DROPPED_TAGS = (b'ZNAM', b'WKMV')
#: Template keyword prefixes the rig's race leaves out: actor types (keywords()) and the template's anim set.
TEMPLATE_KEYWORDS = ('ActorType', 'Anims')
ATTACK_TAGS = (b'ATKD', b'ATKE', b'ATKT', b'ATKW', b'ATKS')
#: BOD2's bit 0 biped slot; the slot a face screen takes (Eyes), so an equipped screen armor replaces the skin's.
FIRST_SLOT, SCREEN_SLOT = 30, 47


def text(d: bytes) -> str:
    return d.rstrip(b'\0').decode('cp1252', 'replace')


def zstr(sig: str, value: str) -> bytes:
    return pack_subrecord(sig, value.encode('cp1252') + b'\0')


def u32(sig: str, value: int) -> bytes:
    return pack_subrecord(sig, struct.pack('<I', value))


class Templates:
    """Fallout4.esm's records an own rig copies, by (signature, EditorID); its actions and their IDLEs' DATA."""

    def __init__(self, fo4: bytes):
        """Index `fo4` (Fallout4.esm's bytes) once."""
        self.by_edid, self.actions, self.idle_data, self.weapons = {}, {}, {}, {}
        rank = {}
        for rec, _ in walk(fo4, b'RACE', b'BPTD', b'ARMO', b'ARMA', b'MOVT', b'AACT', b'IDLE', b'WEAP', b'KYWD',
                            b'EQUP'):
            subs = list(subrecords(rec.body))
            found = dict(subs)
            edid = text(found.get(b'EDID', b''))
            self.by_edid[(rec.sig, edid)] = (rec, subs)
            if rec.sig == b'AACT':
                self.actions[edid] = rec.form_id
            elif rec.sig == b'WEAP':
                self.weapons[rec.form_id] = rec
            elif rec.sig == b'IDLE':
                self._idle(found, rank)

    def _idle(self, found: dict, rank: dict) -> None:
        """Keep IDLE `found`'s DATA for its action when its graph comes earlier in IDLE_GRAPHS than one kept."""
        graph = text(found.get(b'DNAM', b'')).lower()
        parent = struct.unpack('<I', found.get(b'ANAM', bytes(8))[:4])[0]
        at = next((i for i, g in enumerate(IDLE_GRAPHS) if graph.endswith(g)), len(IDLE_GRAPHS))
        if at < rank.get(parent, len(IDLE_GRAPHS)):
            rank[parent], self.idle_data[parent] = at, found.get(b'DATA', bytes(6))

    def get(self, sig: bytes, edid: str) -> tuple:
        return self.by_edid[(sig, edid)]


def attack_subs(rig, template: bytes, share: float) -> bytes:
    """ATKD/ATKE/ATKT for each attack: the template's normal ATKD, damage mult 1, aimed ahead, weighted so power
    attacks take `share` of the picks."""
    power_count = sum(1 for _, power, _ in rig.attacks.values() if power)
    normal_w, power_w = weights(len(rig.attacks) - power_count, power_count, share)
    out, base = b'', list(ATKD.unpack_from(template))
    for event, power, label in rig.attacks.values():
        v = list(base)
        v[0:6] = [1.0, power_w if power else normal_w, 0, POWER if power else 0, 0.0, STRIKE_ANGLE]
        out += pack_subrecord('ATKD', ATKD.pack(*v)) + zstr('ATKE', event) + zstr('ATKT', label)
    return out


def normal_attack(rig, t: Templates) -> bytes:
    """The template race's first normal ATKD, every own attack's shape."""
    _, subs = t.get(b'RACE', rig.template['race'])
    return next(d for tag, d in subs if tag == b'ATKD' and ATKD.unpack_from(d)[3] == 0)


def race(fid: int, rig, t: Templates, ids: dict, made: dict) -> bytes:
    """The template race as the creature's: its name, skin, skeleton, body parts and project, one subgraph entry
    (the root graph, all clips), its own attacks (power share made['share']), Allow PC Dialogue when
    made['talks'], its unarmed weapon ids['unarmed'] (unarmed()), the actor-type keywords of FNV creature type
    made['kind'] in place of the template's, and guns among its equip types when it has guns, in its equip slots
    (equip_slots; `rig` from with_slots).
    See: docs/fork/fo4_own_rig.md#ranged
    """
    rec, subs = t.get(b'RACE', rig.template['race'])
    template = normal_attack(rig, t)
    share, data = made['share'], dict(subs)[b'DATA']
    replaced = {b'EDID': zstr('EDID', f'{rig.project}Race'), b'FULL': zstr('FULL', ids['name']),
                b'DESC': zstr('DESC', ''), b'WNAM': u32('WNAM', ids['skin']), b'GNAM': u32('GNAM', ids['parts']),
                b'ANAM': zstr('ANAM', rig.path('CharacterAssets', 'skeleton.nif')),
                b'DATA': pack_subrecord('DATA', with_race_flags(data, ALLOW_PC_DIALOGUE if made['talks'] else 0))}
    replaced[b'UNWP'] = u32('UNWP', ids['unarmed'])
    replaced.update(keywords(dict(subs).get(b'KWDA', b''), t, made['kind']))
    if rig.guns:
        replaced[b'VNAM'] = u32('VNAM', struct.unpack('<I', dict(subs)[b'VNAM'])[0] | EQUIP_GUN)
    entry = (zstr('SGNM', rig.path('Behaviors', f'{rig.project}RootBehavior.hkx'))
             + zstr('SAPT', rig.path('Animations')) + u32('SRAF', 1))
    groups = {'attacks': attack_subs(rig, template, share), 'graph': entry, 'slots': equip_slots(rig, subs)}
    out, after_nam3, done = b'', False, set()
    for tag, data in subs:
        group = ('attacks' if tag in ATTACK_TAGS else 'graph' if tag in SUBGRAPH_TAGS
                 else 'slots' if tag == b'QNAM' else None)
        if tag in DROPPED_TAGS:
            continue
        if group:
            out += b'' if group in done else groups[group]
            done.add(group)
        elif tag == b'MODL' and after_nam3:
            out += zstr('MODL', rig.path(f'{rig.project}Project.hkx'))
        else:
            out += replaced.get(tag) or pack_subrecord(tag.decode(), data)
        after_nam3 = after_nam3 or tag == b'NAM3'
    return pack_fo4_record('RACE', fid, rec.flags, out)


def equip_slots(rig, subs: list) -> bytes:
    """QNAMs of `subs` then rig.slots, each gun's ZNAM naming its weapon_node."""
    fids = [struct.unpack('<I', d)[0] for tag, d in subs if tag == b'QNAM'] + list(rig.slots)
    return b''.join(u32('QNAM', f) + (zstr('ZNAM', weapon_node(i)) if i in rig.fire_nodes else b'')
                    for i, f in enumerate(fids))


def with_slots(rig, t: Templates):
    """`rig` with each gun's equip slot (an EQUP EditorID) as its index in its race's: the template race's slots,
    then the ones it lacks (`slots`, in the guns' order)."""
    _, subs = t.get(b'RACE', rig.template['race'])
    order = [struct.unpack('<I', d)[0] for tag, d in subs if tag == b'QNAM']
    named = [t.get(b'EQUP', name)[0].form_id for _, name, _, _ in rig.guns]
    added = list(dict.fromkeys(f for f in named if f not in order))
    index = {f: i for i, f in enumerate(order + added)}
    guns = tuple((role, index[f], bones, node) for (role, _, bones, node), f in zip(rig.guns, named))
    return replace(rig, guns=guns, slots=tuple(added))


def fnv_part_names(folder: str) -> dict:
    """{bone (lower case): part name} of FNV's body part data on skeleton folder `folder` (BPTN before its BPNN)."""
    out = {}
    for rec, _ in source_walk(b'BPTD'):
        subs = list(subrecords(rec.body))
        if text(dict(subs).get(b'MODL', b'')).lower().replace('/', '\\').rpartition('\\')[0] != folder.lower():
            continue
        name = ''
        for tag, data in subs:
            if tag == b'BPNN' and name:
                out.setdefault(text(data).lower(), name)
            name = text(data) if tag == b'BPTN' else '' if tag == b'BPNN' else name
    return out


def localized(data: bytes, strings: dict) -> str:
    """A Fallout4.esm string field's text: its string ID's in `strings`, else itself."""
    return strings.get(struct.unpack('<I', data)[0], b'').decode('cp1252', 'replace') if len(data) == 4 else text(data)


def part_name(bone: str, names: dict, parents: dict) -> 'str | None':
    """The name of the FNV part covering `bone`: the nearest of it and its ancestors (`parents`) that `names`
    (fnv_part_names) holds; None when none does."""
    while bone:
        if bone.lower() in names:
            return names[bone.lower()]
        bone = parents.get(bone)
    return None


def body_parts(fid: int, rig, t: Templates, made: dict) -> bytes:
    """The template's body part data on the creature's bones (`made`: write()'s parents and Fallout4.esm strings):
    each part named as FNV names the part covering its bone (part_name), else as the template names it; no limb
    models, hit reactions only.
    See: docs/fork/fo4_own_rig.md#body-parts
    """
    rec, subs = t.get(b'BPTD', rig.template['parts'])
    node = lambda d: rig.parts.get(text(d), rig.default_part) if text(d) else ''
    names, template = fnv_part_names(rig.folder), ''
    blank = {b'NAM1': zstr('NAM1', ''), b'NAM5': pack_subrecord('NAM5', b''), b'DNAM': zstr('DNAM', ''),
             b'EDID': zstr('EDID', f'{rig.project}BodyPartData'),
             b'MODL': zstr('MODL', rig.path('CharacterAssets', 'skeleton.nif'))}
    out = b''
    for tag, data in subs:
        if tag == b'BPTN':
            template = localized(data, made['strings'])
            continue
        shown = part_name(node(data), names, made['parents']) or template or node(data) if tag == b'BPNN' else ''
        out += _part_field(tag, data, node, shown) or blank.get(tag) or pack_subrecord(tag.decode(), data)
    return pack_fo4_record('BPTD', fid, rec.flags, out)


def _part_field(tag: bytes, data: bytes, node, shown: str) -> bytes:
    """A template part's field on the creature: its node (BPNN, after the part's name `shown`) and the node
    fields on its bones (`node`), its flags cut to hit reactions; b'' for any other field."""
    if tag == b'BPNN':
        return zstr('BPTN', shown) + zstr('BPNN', node(data))
    if tag in (b'BPNT', b'NAM4', b'ENAM', b'FNAM'):
        return zstr(tag.decode(), node(data))
    if tag != b'BPND':
        return b''
    nd = bytearray(data)
    nd[BPND_FLAGS] &= PART_FLAGS_KEPT
    return pack_subrecord('BPND', bytes(nd))


def body_path(rig, body: str) -> str:
    """The FO4 model path of body `body` (its file name) in the creature's folder."""
    return rig.path('CharacterAssets', body)


def skin(ids: tuple, race_fid: int, rig, t: Templates, body: str, footsteps: bool = True,
         screen: str = None) -> tuple:
    """(ARMO, [ARMA]): the template's skin and its addon on the creature's race and body `body` (a file name in its
    CharacterAssets), the addon's footstep set (SNDD) kept only with `footsteps`; with a `screen` (its face screen's
    file), a second addon showing it on SCREEN_SLOT. `ids` is (skin, addon[, screen addon]) FormIDs.

    See: docs/fork/fo4_own_rig.md#expressions
    """
    suffix = body.rsplit('.', 1)[0]
    addons = [addon(ids[1], race_fid, rig, t, (body_path(rig, body), f'{suffix}AA', None), footsteps)]
    if screen:
        addons.append(addon(ids[2], race_fid, rig, t, (body_path(rig, screen), f'{suffix}ScreenAA', SCREEN_SLOT)))
    return wearable(ids[0], race_fid, rig, t, f'Skin{suffix}', addons), [arma for _, arma in addons]


def addon(fid: int, race_fid: int, rig, t: Templates, shown: tuple, footsteps: bool = False) -> tuple:
    """((FormID, BOD2 slot mask), ARMA) of the template's addon on the race showing `shown`: (model path, EditorID,
    its one slot or None for the template's), its footstep set kept with `footsteps`."""
    model, edid, slot = shown
    arma_rec, arma_subs = t.get(b'ARMA', rig.template['addon'])
    mask = struct.unpack('<I', dict(arma_subs)[b'BOD2'][:4])[0] if slot is None else 1 << (slot - FIRST_SLOT)
    new = {b'EDID': zstr('EDID', edid), b'RNAM': u32('RNAM', race_fid), b'BOD2': u32('BOD2', mask),
           b'MOD2': zstr('MOD2', model), b'MOD3': zstr('MOD3', model)}
    arma = b''.join(new.get(tag) or pack_subrecord(tag.decode(), data) for tag, data in arma_subs
                    if tag not in (b'MO2T', b'MO3T') and (footsteps or tag != b'SNDD'))
    return (fid, mask), pack_fo4_record('ARMA', fid, arma_rec.flags, arma)


def wearable(fid: int, race_fid: int, rig, t: Templates, edid: str, addons: list) -> bytes:
    """The template's skin ARMO as `edid` on the race, listing `addons` (addon()'s) and covering their slots."""
    armo_rec, armo_subs = t.get(b'ARMO', rig.template['skin'])
    listed = b''.join(pack_subrecord('INDX', bytes(2)) + u32('MODL', f) for (f, _), _ in addons)
    new = {b'EDID': zstr('EDID', edid), b'RNAM': u32('RNAM', race_fid), b'MODL': listed,
           b'BOD2': u32('BOD2', functools.reduce(operator.or_, (m for (_, m), _ in addons)))}
    armo = b''.join(new.get(tag) or pack_subrecord(tag.decode(), data) for tag, data in armo_subs if tag != b'INDX')
    return pack_fo4_record('ARMO', fid, armo_rec.flags, armo)


def screen_armor(writer, rig, t: Templates, model: str, name: str) -> int:
    """Add the armor showing face screen file `model` (in the creature's CharacterAssets) on SCREEN_SLOT, as
    `FNV_SecuritronScreen_<name>`, on the rig's race; its FormID.

    See: docs/fork/fo4_own_rig.md#expressions
    """
    race_fid = writer.derive_formid(SITE, f'{rig.folder} race')
    fid, arma_fid = (writer.derive_formid(SITE, f'{rig.folder} screen {name} {k}') for k in ('armor', 'addon'))
    made = addon(arma_fid, race_fid, rig, t, (body_path(rig, model), f'FNV_SecuritronScreen_{name}AA', SCREEN_SLOT))
    writer.add_record('ARMA', made[1])
    writer.add_record('ARMO', wearable(fid, race_fid, rig, t, f'FNV_SecuritronScreen_{name}', [made]))
    return fid


def sped(old: list, walk: float, run: float) -> list:
    """The 28-float SPED of form version 104+: forward walk, run, sprint; rotations.
    See: docs/fork/fo4_spikes.md#own-rig-movement-type
    """
    rotation = old[8:14] if len(old) == 17 else old[16:28:2]
    return [0.0] * 8 + [0.0, walk, run, run * SPRINT] + [0.0] * 4 + [r for r in rotation for _ in range(2)]


def movement(fid: int, rig, t: Templates, walk_speed: float, run_speed: float) -> bytes:
    """The template movement type linked to the graph's iState_<project>, forward at the clips' root speeds."""
    rec, subs = t.get(b'MOVT', rig.template['movement'])
    out = b''
    for tag, data in subs:
        if tag == b'SPED':
            old = list(struct.unpack(f'<{len(data) // 4}f', data))
            out += pack_subrecord('SPED', struct.pack('<28f', *sped(old, walk_speed, run_speed)))
        else:
            new = {b'EDID': zstr('EDID', f'{rig.project}_Default_MT'), b'MNAM': zstr('MNAM', rig.project)}
            out += new.get(tag) or pack_subrecord(tag.decode(), data)
    return pack_fo4_record('MOVT', fid, rec.flags, out)


def idle(fid: int, rig, t: Templates, action: str, event: str, under: tuple = (), slot: int = -1) -> bytes:
    """An IDLE of `action` sending `event` (none when '') to the root graph: directly under the action with
    previous 0, as every vanilla one there has (the CK calls anything else an invalid prev idle), else `under`
    (parent IDLE, previous sibling) on GetActionDataByte == `slot`."""
    parent = t.actions[action]
    name = f'{rig.project}_{action[len("Action"):]}{slot if under else ""}'
    subs = (zstr('EDID', name) + (pack_ctda(0, float(slot), GET_ACTION_DATA_BYTE) if under else b'')
            + zstr('DNAM', rig.path('Behaviors', f'{rig.project}RootBehavior.hkx'))
            + (zstr('ENAM', event) if event else b'')
            + pack_subrecord('ANAM', struct.pack('<II', *(under or (parent, 0))))
            + pack_subrecord('DATA', t.idle_data.get(parent, bytes(6))))
    return pack_fo4_record('IDLE', fid, 0, subs)


def fire_idles(writer, rig, t: Templates) -> None:
    """Per fire action, as the robots': a root IDLE under it and one child per gun, sending fire_start(slot) on
    GetActionDataByte == slot.
    See: docs/fork/fo4_own_rig.md#ranged
    """
    for action in RANGED_ACTIONS:
        root = writer.derive_formid(SITE, f'{rig.folder} IDLE {action}')
        writer.add_record('IDLE', idle(root, rig, t, action, ''))
        previous = 0
        for _, slot, _, _ in rig.guns:
            fid = writer.derive_formid(SITE, f'{rig.folder} IDLE {action} {slot}')
            writer.add_record('IDLE', idle(fid, rig, t, action, fire_start(slot), (root, previous), slot))
            previous = fid


def keywords(kwda: bytes, t: Templates, kind: int) -> dict:
    """{KSIZ, KWDA} of template keywords `kwda` less its TEMPLATE_KEYWORDS ones, plus ACTOR_TYPES[`kind`]."""
    actor_types = {rec.form_id for (sig, edid), (rec, _) in t.by_edid.items()
                   if sig == b'KYWD' and edid.startswith(TEMPLATE_KEYWORDS)}
    kept = [k for k in struct.unpack(f'<{len(kwda) // 4}I', kwda) if k not in actor_types]
    ids = kept + [t.get(b'KYWD', name)[0].form_id for name in ACTOR_TYPES[kind]]
    return {b'KSIZ': u32('KSIZ', len(ids)), b'KWDA': pack_subrecord('KWDA', struct.pack(f'<{len(ids)}I', *ids))}


def unarmed(fid: int, rig, t: Templates) -> bytes:
    """The template race's unarmed weapon as the rig's own (its equip slot fits the race's), hitting with the
    impact set of Fallout4.esm weapon template 'unarmed' when the entry names one."""
    race_subs = dict(t.get(b'RACE', rig.template['race'])[1])
    weapon = t.weapons[struct.unpack('<I', race_subs[b'UNWP'])[0]]
    impact = {b'INAM': dict(t.get(b'WEAP', rig.template['unarmed'])[1])[b'INAM']} if 'unarmed' in rig.template else {}
    return copy_record(weapon, fid, f'{rig.project}Unarmed', impact)


def write_skin(writer, rig, t: Templates, race_fid: int, body: str, footsteps: bool, screen: str = None) -> int:
    """Add the skin and addons showing body `body` (a CharacterAssets file name) and its face `screen` on the
    race, with the template's footstep set when `footsteps`; the skin's FormID."""
    ids = tuple(writer.derive_formid(SITE, f'{rig.folder} {body.lower()} {k}')
                for k in ('skin', 'addon') + (('screen',) if screen else ()))
    armo, armas = skin(ids, race_fid, rig, t, body, footsteps, screen)
    for arma in armas:
        writer.add_record('ARMA', arma)
    writer.add_record('ARMO', armo)
    return ids[0]


def write(writer, rig, t: Templates, made: dict) -> int:
    """Add the creature's race, body parts, default skin (its first body), movement type and IDLEs to `writer`;
    the race's FormID. `made` holds name, body, speeds ((walk, run) root speed), share (of power attacks),
    footsteps (whether the skin keeps the template's footstep set), screen (its face screen's file or None), talks
    and kind (race()), parents (bones'), strings (Fallout4.esm's)."""
    ids = {k: writer.derive_formid(SITE, f'{rig.folder} {k}') for k in ('race', 'parts', 'movement', 'unarmed')}
    writer.add_record('WEAP', unarmed(ids['unarmed'], rig, t))
    ids['name'] = made['name']
    ids['skin'] = write_skin(writer, rig, t, ids['race'], made['body'], made['footsteps'], made.get('screen'))
    writer.add_record('MOVT', movement(ids['movement'], rig, t, *made['speeds']))
    writer.add_record('BPTD', body_parts(ids['parts'], rig, t, made))
    writer.add_record('RACE', race(ids['race'], rig, t, ids, made))
    for action, event in ACTIONS.items():
        writer.add_record('IDLE', idle(writer.derive_formid(SITE, f'{rig.folder} IDLE {action}'), rig, t, action,
                                       event))
    if rig.guns:
        fire_idles(writer, rig, t)
    return ids['race']
