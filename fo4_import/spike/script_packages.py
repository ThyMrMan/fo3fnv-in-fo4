"""FO3/FNV script packages (AddScriptPackage) on Fallout 4: a quest whose collection aliases run them.

FO4's Papyrus has no AddScriptPackage; its own way to give an actor a
package from script is an alias whose package list holds it, which runs
ahead of the actor's own. The build writes one start-game quest,
FNV_TES4ScriptPackages: a collection alias per package any converted script
names, alias i running Packages[i] of its F3NV_ScriptPackages script.
Converted AddScriptPackage puts the actor in that package's alias (out of
any other, as FNV keeps one script package per actor); RemoveScriptPackage
takes it out. Converted scripts reach the quest through their
TES4ScriptPackages property. After those aliases, one alias per held actor
(held_actors) keeps it at its placed spot until a script package of its own
runs.

See: docs/fork/fo4_pipeline.md#script-packages
"""

from fo4_import.base.vmad import quest_fragments
from fo4_import.pipeline.export_index import export_records
from fo4_import.spike import records as R
from tes5_import.packages.aliases import build_script_assigned_packages

#: The quest's EditorID (its FormID is hashed from it), script and the property converted scripts name it by.
EDID, SCRIPT, PROPERTY = 'FNV_TES4ScriptPackages', 'F3NV_ScriptPackages', 'TES4ScriptPackages'
SITE = 'FNV script packages'
#: Fallout4.esm's DefaultStayAtEditorLocation: Travel near the editor location, radius 0, no conditions.
STAY_AT_EDITOR = 0x003641
#: FNV PKDT type Dialogue, and PLDT type near editor location (its wait spot is where the actor is placed).
DIALOGUE, NEAR_EDITOR = '15', '3'
#: Records whose scripts may call AddScriptPackage, and those naming its packages and actors.
SCRIPTED, NAMED = ('SCPT', 'INFO', 'QUST', 'NPC_', 'CREA'), ('PACK', 'ACHR', 'ACRE', 'REFR', 'NPC_', 'CREA')


def quest_id(builder) -> int:
    """The script-package quest FormID (scripts are filled with it early)."""
    return builder.writer.derive_formid(SITE, EDID)


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
    """Write the script-package quest for the packages scripts named (Packages.scripted_made) and the held actors
    (held_actors); how many packages."""
    made = builder.packages.scripted_made()
    packages, held = [fid for _, fid in made], held_actors(builder)
    vmad = quest_fragments('', [], scripts=[(SCRIPT, {}, {'Packages': ('objects', packages),
                                                           'Holds': ('int', len(held))})])
    aliases = [(i, f'Package{i}', None, (fid,)) for i, fid in enumerate(packages)]
    aliases += [(len(packages) + i, f'Hold{i}', ref, (STAY_AT_EDITOR,)) for i, ref in enumerate(held)]
    builder.writer.add_record('QUST', R.pack_fnv_quest(quest_id(builder), EDID, '', 0, vmad, [], [], aliases, True))
    builder.scripts.used.append(SCRIPT)
    builder.counts['actors held at their placed spot'] = len(held)
    return len(packages)
