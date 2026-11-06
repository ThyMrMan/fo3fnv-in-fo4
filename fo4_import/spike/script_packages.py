"""FO3/FNV script packages (AddScriptPackage) on Fallout 4: a quest whose collection aliases run them.

FO4's Papyrus has no AddScriptPackage; its own way to give an actor a
package from script is an alias whose package list holds it, which runs
ahead of the actor's own. The build writes one start-game quest,
FNV_TES4ScriptPackages: a collection alias per package any converted script
names, alias i running Packages[i] of its F3NV_ScriptPackages script.
Converted AddScriptPackage puts the actor in that package's alias (out of
any other, as FNV keeps one script package per actor); RemoveScriptPackage
takes it out. A Dialogue package is done once its actor talks: the talk
opening (F3NV_Greeting) drops it (Talks), as FNV does; FO4's force greet
standing in for it never ends by itself. Converted scripts reach the quest through their
TES4ScriptPackages property. After those aliases, one alias per held actor
(held_actors) keeps it at its placed spot until a script package of its own
runs. A plugin whose master holds the quest writes its own (quest_id), whose
Hub is the master's: every plugin's quest registers with the hub at game
start, and Add, Remove and Talked look across them all, so a package from
any loaded plugin runs and an actor keeps one script package across them.

See: docs/fork/fo4_pipeline.md#script-packages
"""

from pathlib import Path

from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from tes5_import.packages.aliases import build_script_assigned_packages

#: The quest's EditorID (its FormID is hashed from it), script and the property converted scripts name it by.
EDID, SCRIPT, PROPERTY = 'FNV_TES4ScriptPackages', 'F3NV_ScriptPackages', 'TES4ScriptPackages'
#: derive_formid site, and the key of a plugin's own quest when its master holds EDID's.
SITE, PLUGIN_KEY = 'FNV script packages', 'plugin quest'
#: The keyword every package alias puts on its actors, so Remove skips the alias search for one in none (its key).
KEYWORD = 'F3NV_InScriptPackage'
#: Fallout4.esm's DefaultStayAtEditorLocation: Travel near the editor location, radius 0, no conditions.
STAY_AT_EDITOR = 0x003641
#: FNV PKDT type Dialogue, and PLDT type near editor location (its wait spot is where the actor is placed).
DIALOGUE, NEAR_EDITOR = '15', '3'
#: Records whose scripts may call AddScriptPackage, and those naming its packages and actors.
SCRIPTED, NAMED = ('SCPT', 'INFO', 'QUST', 'NPC_', 'CREA'), ('PACK', 'ACHR', 'ACRE', 'REFR', 'NPC_', 'CREA')


def hub_id(builder) -> int:
    """The game's script-package quest FormID (the hub): own or the master's."""
    return builder.writer.derive_formid(SITE, EDID)


def quest_id(builder) -> int:
    """The build's own script-package quest FormID: the hub, or a DLC's own."""
    hub = hub_id(builder)
    return hub if hub >> 24 == builder.writer.own_index else builder.writer.derive_formid(SITE, PLUGIN_KEY)


def held_actors(builder) -> list:
    """FO4 references, sorted, of the built actors a script gives (AddScriptPackage, comments skipped) an FNV
    Dialogue package waiting near their editor location: FNV has them stand there when the script runs. Those
    outside the build are counted.
    See: docs/fork/fo4_pipeline.md#greet-hold
    """
    by_type = {sig: export_records(builder.export_dir, sig) for sig in SCRIPTED}
    names = {int(r['FormID'], 16): r['EditorID'] for sig in NAMED for r in export_records(builder.export_dir, sig)
             if r.get('EditorID')}
    waits = {int(fid, 16) for fid, r in builder.packages.packs.items()
             if r.get('PKDT.Type') == DIALOGUE and r.get('PLDT.Type') == NEAR_EDITOR}
    actors = {a for p, refs in build_script_assigned_packages(by_type, names).items() if p in waits for a in refs}
    builder.counts['held actor outside the build'] += len(actors - builder.actor_refs.keys())
    return sorted({builder.actor_refs[a] for a in actors & builder.actor_refs.keys()})


def write_script_packages(builder) -> int:
    """Write the build's script-package quest (quest_id) for the packages scripts named (Packages.scripted_made),
    the FNV Dialogue ones among them (Talks), and the held actors (held_actors); a plugin's own one names the
    game's (Hub). How many packages."""
    made, quest, hub = builder.packages.scripted_made(), quest_id(builder), hub_id(builder)
    edid, links = (EDID, {}) if quest == hub else (f'{EDID}_{Path(builder.export_dir).stem}', {'Hub': hub})
    packages, held = [fid for _, fid in made], held_actors(builder)
    types = {r.get('EditorID'): r.get('PKDT.Type') for r in builder.packages.packs.values()}
    talks = [fid for name, fid in made if types.get(name) == DIALOGUE]
    own = KEYWORD if quest == hub else f'{KEYWORD}_{Path(builder.export_dir).stem}'
    keyword = builder.writer.derive_formid(SITE, own)
    builder.writer.add_record('KYWD', R.pack_kywd(keyword, own, 0))
    vmad = quest_fragments('', [], scripts=[(SCRIPT, {**links, 'InPackage': keyword},
                                             {'Packages': ('objects', packages), 'Talks': ('objects', talks),
                                              'Holds': ('int', len(held))})])
    aliases = [(i, f'Package{i}', None, (fid,), 0, 0, (keyword,)) for i, fid in enumerate(packages)]
    aliases += [(len(packages) + i, f'Hold{i}', ref, (STAY_AT_EDITOR,), 0, 0, (), True) for i, ref in enumerate(held)]
    builder.writer.add_record('QUST', R.pack_fnv_quest(quest, edid, '', 0, vmad, [], [], aliases, True))
    builder.scripts.used.append(SCRIPT)
    builder.counts['actors held at their placed spot'] = len(held)
    return len(packages)
