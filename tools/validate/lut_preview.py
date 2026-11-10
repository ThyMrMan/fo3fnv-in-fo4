"""Preview FO4 colour LUTs on screenshots offline, and write the neutral LUTs that make such screenshots.

FO4 applies an imagespace's LUT last, to display colours, so a shot taken with identity LUTs is FO4's frame
before grading, and any LUT applied to it here shows exactly what the game would.

Usage: python -m tools.validate.lut_preview neutral <built Textures/Effects/LUTs/FNV> <out folder>
       python -m tools.validate.lut_preview apply SHOT.png LUT.dds OUT.png
`neutral` writes an identity LUT under each built LUT's name; install the out folder as a loose-file mod at
Textures/Effects/LUTs/FNV and take the shots.

See: docs/fork/fo4_look.md#route-tone
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from fo4_import.spike.imagespace import apply_lut, identity, lut_dds, read_lut


def neutral(built: Path, out: Path) -> int:
    """Write an identity LUT under each `.dds` name in `built` into `out`; the count."""
    out.mkdir(parents=True, exist_ok=True)
    names = sorted(p.name for p in built.glob('*.dds'))
    for name in names:
        (out / name).write_bytes(lut_dds(identity()))
    return len(names)


def main() -> None:
    """Command line: `neutral` or `apply`."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('neutral')
    make.add_argument('built', type=Path)
    make.add_argument('out', type=Path)
    use = sub.add_parser('apply')
    use.add_argument('shot')
    use.add_argument('lut', type=Path)
    use.add_argument('out')
    args = parser.parse_args()
    if args.command == 'neutral':
        print(f'{neutral(args.built, args.out)} identity LUTs written to {args.out}')
        return
    with Image.open(args.shot) as im:
        rgb = np.asarray(im.convert('RGB')) / 255.0
    graded = apply_lut(rgb, read_lut(args.lut.read_bytes()))
    Image.fromarray(np.round(graded * 255).astype(np.uint8)).save(args.out)
    print(f'{args.out}: {args.shot} through {args.lut.name}')


if __name__ == '__main__':
    main()
