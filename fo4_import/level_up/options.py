"""The level-up options as a Mod Configuration Menu page, one per game plugin: Data/MCM/Config/F3NV_<plugin>/.

MCM reads and writes the options straight into the character rules quest's script properties (PropertyValue
sources: F3NV_CharacterRules' rates, CRUI_LevelUp's cap and filter), kept by the save; our scripts call nothing of
MCM's, so without it every option stays the source game's value the build wrote. A hotkey opens the menu
(OpenLevelUp). The page is the templates in mcm/, their `$F3NV_MCM_` keys in our translation files.

See: docs/fork/fo4_level_up_plan.md#options
"""

import json
from pathlib import Path

#: The page's templates: {mod}, {title} and {form} are filled per plugin.
TEMPLATES = Path(__file__).resolve().parent / 'mcm'
#: The page's title per game plugin; another plugin is titled by its name.
TITLES = {'FalloutNV.esm': 'F3NV: Fallout New Vegas', 'Fallout3.esm': 'F3NV: Fallout 3'}


def mod_name(plugin: str) -> str:
    """The MCM mod name (its config folder) of game plugin `plugin`."""
    return f'F3NV_{Path(plugin).stem}'


def filled(template: str, plugin: str, quest: int) -> dict:
    """Template `template` (mcm/<name>.json) for `plugin`, whose rules quest is FormID `quest`."""
    values = {'{mod}': mod_name(plugin), '{title}': TITLES.get(plugin, f'F3NV: {Path(plugin).stem}'),
              '{form}': f'{plugin}|{quest & 0xFFFFFF:X}'}

    def fill(node):
        """`node` with every placeholder string replaced."""
        if isinstance(node, dict):
            return {key: fill(value) for key, value in node.items()}
        if isinstance(node, list):
            return [fill(value) for value in node]
        return values.get(node, node)
    return fill(json.loads((TEMPLATES / template).read_text(encoding='utf-8')))


def install(data_dir: Path, plugin: str, quest: int) -> int:
    """Write <data_dir>/MCM/Config/<mod_name>/ (config.json, keybinds.json) for `plugin`; how many files."""
    folder = Path(data_dir) / 'MCM' / 'Config' / mod_name(plugin)
    folder.mkdir(parents=True, exist_ok=True)
    templates = sorted(p.name for p in TEMPLATES.glob('*.json'))
    for name in templates:
        (folder / name).write_text(json.dumps(filled(name, plugin, quest), indent=2) + '\n', encoding='utf-8')
    return len(templates)
