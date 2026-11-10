"""FNV `SwapTexture` targets as FO4 material swaps, for the cell spike.

The converter turns `SwapTexture <ref> "<node>" "<texture>"` into
`ref.ApplyMaterialSwap(TES4Swap_<node>_<texture name>)` (F4SE). This finds
every SwapTexture in the game's scripts and line results, and makes each
property's MSWP on first use: the shape's converted material swapped for a
copy showing the new texture (statics.swap_material).

See: docs/fork/fo4_spikes.md#spike-2-vcg01
"""

import re
from pathlib import Path

from fo4_import.base.source_fault import without_fault
from fo4_import.spike import records as R
from fo4_import.spike.statics import swap_material
from fo4_import.pipeline.export_index import export_records
from script_convert.constants import fallout4_swap_property

#: `[<ref>.]SwapTexture <ref> "<node>" "<texture>"` in FO3/FNV script text.
SWAP = re.compile(r'(?i)\bswaptexture[ \t]+(\w+)[ \t]+"([^"]+)"[ \t]+"([^"]+)"')
#: Export files and record fields holding script text.
SCRIPT_SOURCES = {'SCPT': ('SCTX',), 'INFO': ('ResultScript', 'ResultScriptEnd'), 'QUST': ('ResultScript',)}
MATERIALS_PREFIX = 'materials\\'


class Swaps:
    """The game's SwapTexture targets by property; `swap` writes one property's MSWP."""

    def __init__(self, builder, export_dir: Path, models: dict):
        """Index the SwapTexture calls; `models` maps reference EditorIDs to FNV models."""
        self.builder, self.export_dir, self.models, self.made, self.targets = builder, export_dir, models, {}, {}
        self.pairs = {}
        texts = [text for sig, fields in SCRIPT_SOURCES.items() for rec in export_records(export_dir, sig)
                 for key, text in rec.items() if key.endswith(fields)]
        for ref, node, texture in (call for text in texts for call in SWAP.findall(text)):
            self.targets.setdefault(fallout4_swap_property(node, texture), (ref, node, texture))

    def swap(self, prop: str) -> int:
        """The MSWP for MatSwap property `prop` (made once); 0 when its target has no converted shape.

        It maps every material the shape can wear (its own and each other
        swap's on the same reference and node) to `prop`'s, whichever one
        is on it when the swap is applied.
        """
        if prop not in self.made:
            pair = self._pair(prop)
            self.made[prop] = fid = self.builder.new_id('MSWP ' + ' '.join(self.targets[prop])) if pair else 0
            if pair:
                ref, node = self.targets[prop][:2]
                worn = {pair[0]} | {self._pair(p)[1] for p, (r, n, _) in self.targets.items()
                                    if (r, n) == (ref, node) and self._pair(p)}
                pairs = [(w[len(MATERIALS_PREFIX):], pair[1][len(MATERIALS_PREFIX):]) for w in sorted(worn)]
                self.builder.writer.add_record('MSWP', R.pack_mswp(fid, f'FNV_{prop}', pairs))
            self.builder.counts['MSWP' if pair else f'swap without a converted shape: {prop}'] += 1
        return self.made[prop]

    def _pair(self, prop: str) -> 'tuple | None':
        """(shape's material, swap material) of `prop`, written once (statics.swap_material); None, as for no
        such shape, when its model has a source fault."""
        if prop not in self.pairs:
            ref, node, texture = self.targets.get(prop, ('', '', ''))
            model = self.models.get(ref.lower())
            self.pairs[prop] = without_fault(swap_material, self.export_dir, model, node, texture,
                                             self.builder.data_dir) if model else None
        return self.pairs[prop]
