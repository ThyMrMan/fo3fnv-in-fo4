"""Pre-Elric Havok input: the bhk blocks collision.py writes, which FO4 cannot load until our physics writer
(nif/hknp_write.py, through pipeline/elric_cache.py) puts FO4 physics in their place; finding and removing them.

See: docs/fork/fo4_hknp_writer.md#seam
"""

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import BLOCKS, NONE
from fo4_import.nif.file import NifFile

#: Keys of parsed blocks (nif.blocks) holding a block reference or a list of them.
REF_KEYS = frozenset({'shader', 'alpha_property', 'skin', 'texture_set', 'controller', 'collision', 'children',
                      'extra', 'target'})
#: Block types whose every reference is under REF_KEYS (nif.blocks' static set): all a block after the Havok may be.
RENUMBERED = frozenset(BLOCKS)


def _havok(kind: str) -> bool:
    """Whether block type `kind` is pre-Elric Havok input."""
    return kind.startswith('bhk') or kind == 'NiTriStripsData'


def has_havok(data: bytes) -> bool:
    """Whether NIF bytes `data` hold pre-Elric Havok blocks (read from the header)."""
    return any(_havok(kind) for kind, _ in nif_file.read_header(data)[1])


def havok_start(nif: NifFile) -> 'int | None':
    """The index of the first pre-Elric Havok block, or None."""
    return next((i for i, (kind, _) in enumerate(nif.blocks) if _havok(kind)), None)


def without_havok(nif: NifFile) -> NifFile:
    """`nif` without its Havok blocks, no node naming a collision object; blocks added after the Havok input (a
    terminal's screen shader) are kept, references to them renumbered. ValueError for a block after the Havok
    that is not a parsed RENUMBERED one, whose references renumbering would miss."""
    start = havok_start(nif)
    if start is None:
        return nif
    kept = [i for i, (kind, _) in enumerate(nif.blocks) if i < start or not _havok(kind)]
    unsafe = [nif.blocks[i][0] for i in kept if i > start and not (nif.blocks[i][0] in RENUMBERED
                                                                    and isinstance(nif.blocks[i][1], dict))]
    if unsafe:
        raise ValueError(f'blocks after the Havok input that renumbering would mis-point: {unsafe}')
    moved = {old: new for new, old in enumerate(kept) if old >= start}
    nif.blocks = [nif.blocks[i] for i in kept]
    for _, block in nif.blocks:
        if isinstance(block, dict):
            _renumber(block, start, moved)
    return nif


def _renumber(block: dict, start: int, moved: dict) -> None:
    """Point `block`'s references at or past `start` through `moved` (NONE for a dropped block)."""
    def at(ref):
        """`ref` renumbered."""
        return ref if ref < start else moved.get(ref, NONE)
    for key in REF_KEYS & block.keys():
        block[key] = [at(r) for r in block[key]] if isinstance(block[key], list) else at(block[key])
