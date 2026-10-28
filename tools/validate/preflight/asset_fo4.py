"""Red error markers and purple surfaces found before play on a Fallout 4 build.

Every model a player can meet (asset_load.model_users: placed, carried, worn,
rolled) must exist, and so must every material (BGSM, BGEM) and texture it
names, and every texture its materials name. Files resolve as the game finds
them: loose before archived, the plugin's mod folder first, then the mod
folders holding its masters, then Fallout 4's Data.

See: docs/fork/fo4_preflight.md#assets
"""

import re
from collections import defaultdict
from pathlib import Path

from fo4_import.app.files import Files
from fo4_import.nif import bgem, bgsm
from tools.validate.preflight.asset_load import model_users, norm, textures_in, users_detail
from tools.validate.preflight.findings import Finding

#: A material path inside NIF bytes.
_MATERIAL = re.compile(rb'[A-Za-z0-9_\\/ .\'&()-]{3,200}\.bg[se]m', re.I)

#: Users listed per material or texture finding.
_SHOWN = 3


def data_dirs(plugin: Path, masters: tuple, game_data: Path) -> list:
    """The plugin's folder, sibling mods holding its masters, then the game's Data."""
    folder = Path(plugin).parent
    siblings = sorted(d for d in folder.parent.iterdir() if d.is_dir() and d != folder)
    return [folder, *(d for d in siblings if any((d / m).is_file() for m in masters)), Path(game_data)]


def material_textures(path: str, data: bytes):
    """The texture paths a BGSM or BGEM names, or None when it cannot be read."""
    reader = bgem.read if path.endswith('.bgem') else bgsm.read
    try:
        return [t for t in reader(data)['textures'].values() if t]
    except (ValueError, IndexError, KeyError, UnicodeDecodeError):
        return None


def _named_by(kind: str, names: set) -> tuple:
    """Detail lines naming the first files that use a material or texture."""
    return tuple(f'named by {kind} {n}' for n in sorted(names)[:_SHOWN])


def mesh_findings(game: str, users: dict, files: Files, source_dir: Path) -> tuple:
    """(findings for missing meshes, {material: meshes}, {texture: meshes}) over every used model."""
    out, materials, textures = [], defaultdict(set), defaultdict(set)
    for path in sorted(users):
        data = files.read(path)
        if data is None:
            where = 'the source game has it' if (Path(source_dir) / path).is_file() else 'nor does the source game'
            out.append(Finding('assets', f'assets|{game}|missing|{path}', 'error',
                               f'{path} is not in the build, its masters or Fallout 4 ({where}): a red error marker',
                               users_detail(users[path])))
            continue
        for match in _MATERIAL.findall(data):
            materials[norm(match.decode('latin-1'), 'materials')].add(path)
        for tex in textures_in(data):
            textures[tex].add(path)
    return out, materials, textures


def material_findings(game: str, materials: dict, textures: dict, files: Files) -> list:
    """Findings for missing or unreadable materials; adds each material's textures to `textures`."""
    out = []
    for path, meshes in sorted(materials.items()):
        data = files.read(path)
        named = material_textures(path, data) if data is not None else None
        if data is None or named is None:
            why = 'is not in the build, its masters or Fallout 4' if data is None else 'cannot be read'
            out.append(Finding('assets', f'assets|{game}|material|{path}', 'error',
                               f'{path} {why}: its meshes render without it', _named_by('mesh', meshes)))
            continue
        for tex in named:
            textures[norm(tex, 'textures')].add(path)
    return out


def audit(game: str, index, plugin: Path, game_data: Path, source_dir: Path) -> list:
    """The asset findings for one Fallout 4 build."""
    files = Files(data_dirs(plugin, index.masters, game_data))
    out, materials, textures = mesh_findings(game, model_users(index), files, source_dir)
    out += material_findings(game, materials, textures, files)
    return out + [Finding('assets', f'assets|{game}|texture|{tex}', 'error',
                          f'{tex} is not in the build, its masters or Fallout 4: the surface shows purple',
                          _named_by('file', users))
                  for tex, users in sorted(textures.items()) if files.where(tex) is None]
