"""FO3/FNV script packages (AddScriptPackage) on Fallout 4: a quest whose collection aliases run them.

FO4's Papyrus has no AddScriptPackage; its own way to give an actor a
package from script is an alias whose package list holds it, which runs
ahead of the actor's own. The build writes one start-game quest,
FNV_TES4ScriptPackages: a collection alias per package any converted script
names, alias i running Packages[i] of its F3NV_ScriptPackages script.
Converted AddScriptPackage puts the actor in that package's alias (out of
any other, as FNV keeps one script package per actor); RemoveScriptPackage
takes it out. Converted scripts reach the quest through their
TES4ScriptPackages property.

See: docs/fork/fo4_pipeline.md#script-packages
"""

from fo4_import.base.vmad import quest_fragments
from fo4_import.spike import records as R

#: The quest's EditorID (its FormID is hashed from it), script and the property converted scripts name it by.
EDID, SCRIPT, PROPERTY = 'FNV_TES4ScriptPackages', 'F3NV_ScriptPackages', 'TES4ScriptPackages'
SITE = 'FNV script packages'


def quest_id(builder) -> int:
    """The script-package quest FormID (scripts are filled with it early)."""
    return builder.writer.derive_formid(SITE, EDID)


def write_script_packages(builder) -> int:
    """Write the script-package quest for the packages scripts named (Packages.scripted_made); how many."""
    made = builder.packages.scripted_made()
    packages = [fid for _, fid in made]
    vmad = quest_fragments('', [], scripts=[(SCRIPT, {}, {'Packages': ('objects', packages)})])
    aliases = [(i, f'Package{i}', None, (fid,)) for i, fid in enumerate(packages)]
    builder.writer.add_record('QUST', R.pack_fnv_quest(quest_id(builder), EDID, '', 0, vmad, [], [], aliases, True))
    builder.scripts.used.append(SCRIPT)
    return len(packages)
