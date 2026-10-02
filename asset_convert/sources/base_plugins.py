r"""Which plugins does an export tree build on?

An imported mod ships only what it changes; everything else -- textures its
meshes reference, and the ARMO/CLOT records that say which meshes are worn --
lives in the base game's export. A tree that cannot name its base is blind to
both, and the two blindnesses look identical from the outside: a shape simply
gets the conservative default.

Two carriers, because a mod declares its base in two different ways:

  * a PLUGIN mod names its masters in the export's `_HEADER.txt`, the same
    line `convert_speedtrees` reads to find a master's `.spt` files;
  * an ASSET-ONLY mod has no plugin and therefore no header, so the base is
    recorded at import time -- `--import-mod ... --base Nehrim.esm`, or
    implicitly by seeding the base into an ordered merge.
"""
import os

from core.plugin_masters import masters_from_export_header

FILE_NAME = '.base_plugins'


def names_for(own_dir):
    """Base plugin names for the export tree at `own_dir`, nearest first."""
    own_dir = str(own_dir)
    names = list(dict.fromkeys(masters_from_export_header(own_dir)))
    recorded = os.path.join(own_dir, '_source', FILE_NAME)
    if os.path.isfile(recorded):
        with open(recorded, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                n = line.strip()
                if n and n not in names:
                    names.append(n)
    return names


def export_dirs(own_dir):
    """Sibling export trees for the bases of `own_dir`, that exist.

    Resolved through `record_dir`: an imported mod's plugins share ONE folder
    named for the MOD, so joining the master's own name onto the export root
    misses it and the base is silently lost (`Tamriel_Data.esm` lives in
    `Tamriel Data (HD)`).

    `output_layout` is imported here, not at module scope: it reaches back into
    this package for `source_registry`, so a top-level import is a cycle.
    """
    from output_layout import record_dir
    own_dir = os.path.abspath(str(own_dir))
    export_root = os.path.dirname(own_dir)
    out = []
    for n in names_for(own_dir):
        p = str(record_dir(export_root, n))
        if os.path.isdir(p) and p not in out:
            out.append(p)
    return out


def subdirs(own_dir, sub):
    """`export_dirs` narrowed to an existing subfolder (e.g. 'textures')."""
    out = []
    for d in export_dirs(own_dir):
        p = os.path.join(d, sub)
        if os.path.isdir(p):
            out.append(p)
    return tuple(out)
