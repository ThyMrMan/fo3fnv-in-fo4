"""Preview a Fallout 4 NIF in a window, or render it to a PNG with no window.

    py -3.14 -m fo4_import.app.preview meshes\\weapons\\10mmpistol\\10mmpistol.nif
    py -3.14 -m fo4_import.app.preview <mesh> --settings fo4_app.json --png out.png

The mesh is a file on disk or a path inside Data, looked up in --dirs, then the settings' mod sources, then
Fallout 4's Data folder (loose files before archives, ignoring case).

See: docs/fork/fo4_gui.md#preview
"""

import argparse
from pathlib import Path

from core.mod_sources import data_dirs
from fo4_import.app import settings
from fo4_import.app.files import Files
from fo4_import.app.preview.materials import Materials
from fo4_import.app.preview.render import render_image
from fo4_import.app.preview.viewer import open_model, show


def arguments() -> argparse.Namespace:
    """The command line (the module notes)."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('mesh', help='A NIF file, or a path inside Data (meshes\\...)')
    ap.add_argument('--dirs', nargs='*', default=(), type=Path, help='Data-like folders to look in first')
    ap.add_argument('--settings', type=Path, help="The app's settings file, for its mod sources and game folder")
    ap.add_argument('--png', type=Path, help='Render to this PNG instead of opening a window')
    ap.add_argument('--size', type=int, default=768, help='The PNG size in pixels')
    return ap.parse_args()


def search_dirs(args: argparse.Namespace) -> list:
    """Folders to look in, winning first: --dirs, mod sources, Fallout 4's Data."""
    chosen = settings.load(args.settings)
    game = settings.game_dir(chosen, 'fallout4')
    return [*args.dirs, *data_dirs(settings.mod_sources(chosen)), *([game / 'Data'] if game else [])]


def main() -> int:
    """Show or render the mesh; the exit code."""
    args = arguments()
    files = Files(search_dirs(args))
    parts, surfaces = open_model(args.mesh, files, Materials(files))
    print(f'{args.mesh}: {len(parts)} parts')
    if args.png:
        render_image(parts, surfaces, (args.size, args.size)).save(args.png)
        return 0
    return show(parts, surfaces, Path(args.mesh).name)


if __name__ == '__main__':
    raise SystemExit(main())
