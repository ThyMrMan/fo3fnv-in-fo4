"""FNV's and FO3's level-up art staged as our textures: each perk's and skill's Vault Boy image (the ICON of PERK
and AVIF records, SPECIAL included), for our own level-up menu to show with f4se.MountImage.

Each image is copied as it is, to its FNV path under our texture folder (statics.copy_texture), as the casino's
textures are; a DLC build stages only those its masters' builds did not. Nothing in the records points at them yet:
FO4's PERK has an unused ICON field and AVIF none, so the menu will find them by its own table.

See: docs/fork/swf_framework.md#level-up
"""

from pathlib import Path

from fo4_import.nif.convert_static import texture_source
from fo4_import.pipeline.export_index import export_file, export_records
from fo4_import.spike.statics import copy_texture

#: The record types whose ICON is level-up art.
SIGNATURES = ('PERK', 'AVIF')


def icons(export_dir: Path) -> list:
    """The distinct PERK and AVIF ICON images `export_dir` sees, as textures\\ paths."""
    return sorted({texture_source(rec['ICON']) for sig in SIGNATURES for rec in export_records(export_dir, sig)
                   if rec.get('ICON')})


def stage(builder, export_dir: Path, data_dir: Path) -> None:
    """Stage every level-up image the export has into `data_dir`; counted, with any the export lacks."""
    paths = icons(export_dir)
    found = [p for p in paths if export_file(export_dir, p.replace('\\', '/')).is_file()]
    builder.counts['level-up icons staged'] = sum(copy_texture(export_dir, data_dir, p) for p in found)
    builder.counts['level-up icon missing from the export'] = len(paths) - len(found)
