"""FalloutHelpers.esl's race ability gates: FNV creatures on Fallout 4's races drop FO4-only race behaviour.

A converted creature is a copy of an FO4 creature on its race, so it runs
that race's ability. Some abilities do what FNV's creature never did: the
protectron, Mister Handy and sentry bot scripts (RobotSelfDestructScript)
self-destruct a robot left without an attack and set it on fire, the
deathclaw's (deathclawRaceScript) roar places a fear explosion, the
behemoth's slams place damaging explosions and the mirelurk king blurs
itself. Each such ability is overridden here: its scripted effects run only
without the converted-creature keyword (a condition put first, so it ANDs with
the effect's own). A robot ability also gains F3NV_RobotFrenzy,
on with the keyword, since the vanilla script is also what frenzies a robot
with a crippled combat inhibitor, which FNV robots do. Vanilla creatures
carry no such keyword.

See: docs/fork/fo4_creature_audit.md#race-abilities
"""

import struct

from fo4_import.base.vmad import object_scripts, read_entry
from fo4_import.base.writer import pack_fo4_record
from fo4_import.spike.records import pack_ctda, pack_kywd
from script_convert.constants import FALLOUT4_HELPER_CREATURE_KEYWORD, FALLOUT4_HELPER_ROBOT_FRENZY
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_string_subrecord, pack_subrecord

#: Fallout4.esm race abilities with FO4-only behaviour -> whether FNV's robot frenzy replaces it.
GATED_ABILITIES = {'AbRaceProtectron': True, 'AbRaceMrHandy': True, 'AbRaceSentryBot': True,
                   'AbRaceDeathclaw': False, 'AbRaceBehemoth': False, 'AbMirelurkKingCloakSpell': False}
TEMPLATE_EFFECT = 'abSentryBotRaceEffect'
KEYWORD_EDID, FRENZY_EDID, SCRIPT = 'F3NV_FalloutCreature', 'F3NV_RobotFrenzyEffect', 'F3NV_RobotFrenzy'
#: F3NV_RobotFrenzy property -> the template effect's RobotSelfDestructScript property it takes the form of.
FRENZY_PROPS = {'BrainCondition': 'BrainCondition', 'FrenzyShader': 'PRobotFrenzyFXS',
                'FrenzyLight': 'PFrenzyFXSLightVE'}
#: Condition function HasKeyword; record flag Compressed, cleared on a copied record (its body is written raw).
HAS_KEYWORD, COMPRESSED = 560, 0x40000
#: A VMAD's header before its first script entry (version, object format, script count).
VMAD_HEADER = 6


def race_records(fo4: bytes, own_id) -> list:
    """[(signature, record)]: the keyword, the frenzy effect and the overridden race abilities, `own_id` giving a
    helper object id's FormID."""
    keyword, frenzy = own_id(FALLOUT4_HELPER_CREATURE_KEYWORD), own_id(FALLOUT4_HELPER_ROBOT_FRENZY)
    found, scripted = {}, set()
    for rec, _ in walk(fo4, b'SPEL', b'MGEF'):
        subs = dict(subrecords(rec.body))
        if rec.sig == b'MGEF' and b'VMAD' in subs:
            scripted.add(rec.form_id)
        edid = subs.get(b'EDID', b'').rstrip(b'\0').decode('cp1252')
        if edid in GATED_ABILITIES or edid == TEMPLATE_EFFECT:
            found[edid] = rec
    out = [('KYWD', pack_kywd(keyword, KEYWORD_EDID, 0)), ('MGEF', frenzy_effect(found[TEMPLATE_EFFECT], frenzy))]
    return out + [('SPEL', gated_ability(found[edid], scripted, keyword, frenzy if robot else 0))
                  for edid, robot in GATED_ABILITIES.items()]


def frenzy_effect(template, fid: int) -> bytes:
    """MGEF `fid`: script effect `template` (a robot race effect) running F3NV_RobotFrenzy, with no conditions."""
    _, objects, _ = read_entry(dict(subrecords(template.body))[b'VMAD'], VMAD_HEADER)[0]
    vmad = object_scripts([(SCRIPT, {prop: objects[theirs] for prop, theirs in FRENZY_PROPS.items()}, {})])
    subs = b''
    for tag, data in subrecords(template.body):
        if tag == b'EDID':
            subs += pack_string_subrecord('EDID', FRENZY_EDID)
        elif tag == b'VMAD':
            subs += pack_subrecord('VMAD', vmad)
        elif tag != b'CTDA':
            subs += pack_subrecord(tag.decode(), data)
    return pack_fo4_record('MGEF', fid, template.flags & ~COMPRESSED, subs)


def gated_ability(ability, scripted: set, keyword: int, frenzy: int) -> bytes:
    """Race ability `ability` with its scripted effects (MGEFs in `scripted`) off for `keyword`'s actors, its other
    effects (Mister Handy's water walking) as they were, and `frenzy` (0: none) added, on for them."""
    groups, head = [], b''
    for tag, data in subrecords(ability.body):
        if tag == b'EFID':
            groups.append([struct.unpack('<I', data)[0], pack_subrecord('EFID', data), b''])
        elif groups:
            groups[-1][1 if tag == b'EFIT' else 2] += pack_subrecord(tag.decode(), data)
        else:
            head += pack_subrecord(tag.decode(), data)
    subs, effect = head, None
    for fid, item, conditions in groups:
        gated = fid in scripted
        effect = item[item.index(b'EFIT'):] if gated else effect
        subs += item + (pack_ctda(0, 0.0, HAS_KEYWORD, keyword) if gated else b'') + conditions
    if frenzy:
        subs += pack_subrecord('EFID', struct.pack('<I', frenzy)) + effect + pack_ctda(0, 1.0, HAS_KEYWORD, keyword)
    return pack_fo4_record('SPEL', ability.form_id, ability.flags & ~COMPRESSED, subs)
