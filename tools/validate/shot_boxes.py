"""Measure fixed boxes of comparison screenshots: mean RGB, luminance, saturation and hue per box, each image
against the first.

Usage: python tools/validate/shot_boxes.py FNV.webp FO4.webp [--spot saloon] [--box NAME=x0,y0,x1,y1 ...]
       [--draw OUT.png]
Boxes are fractions of the image (0 to 1 from the top-left), so any resolution works; framing differs
between games, so check them with --draw.

See: docs/fork/fo4_plan_world_look.md#spots
"""
import argparse
import colorsys
import sys

import numpy as np
from PIL import Image, ImageDraw

#: Boxes per spot, fitted to the FNV reference shots in look_refs (`saloon_*_fnv.webp`).
SPOTS = {
    'saloon': {
        'sky': (0.30, 0.05, 0.50, 0.25),
        'horizon': (0.05, 0.52, 0.15, 0.60),
        'road': (0.26, 0.84, 0.38, 0.86),
        'wall': (0.915, 0.73, 0.94, 0.84),
        'window': (0.835, 0.75, 0.855, 0.82),
    },
}
#: Rec. 709 luma weights on the 8-bit display values.
LUMA = np.array([0.2126, 0.7152, 0.0722])


def parse_box(spec: str) -> tuple:
    """`NAME=x0,y0,x1,y1` as (name, (x0, y0, x1, y1))."""
    name, coords = spec.split('=', 1)
    box = tuple(float(v) for v in coords.split(','))
    if len(box) != 4 or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        raise ValueError(f'bad box {spec!r}: want x0<x1, y0<y1 within 0..1')
    return name, box


def pixels(image: np.ndarray, box: tuple) -> np.ndarray:
    """The RGB pixels of `image` (rows x columns x 3) inside fractional `box`, as N x 3."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = box
    return image[int(y0 * h):max(int(y1 * h), int(y0 * h) + 1),
                 int(x0 * w):max(int(x1 * w), int(x0 * w) + 1)].reshape(-1, 3)


def measure(image: np.ndarray, box: tuple) -> dict:
    """Mean RGB, luminance, and the mean's saturation and hue (degrees) in `box`."""
    rgb = pixels(image, box).astype(float).mean(0)
    hue, sat, _ = colorsys.rgb_to_hsv(*(rgb / 255))
    return {'rgb': rgb, 'lum': float(rgb @ LUMA), 'sat': sat, 'hue': hue * 360}


def load(path: str) -> np.ndarray:
    """An image file as an RGB array."""
    with Image.open(path) as im:
        return np.asarray(im.convert('RGB'))


def table(paths: list, boxes: dict) -> str:
    """One row per image and box; from the second image on, its luminance as a ratio of the first's."""
    first, out = {}, [f'{"image":<34}{"box":<10}{"R":>5}{"G":>5}{"B":>5}{"lum":>7}{"sat":>6}{"hue":>6}{"lum/1st":>9}']
    for path in paths:
        image = load(path)
        for name, box in boxes.items():
            m = measure(image, box)
            ratio = f'{m["lum"] / first[name]:.2f}' if name in first and first[name] else ''
            first.setdefault(name, m['lum'])
            r, g, b = m['rgb'].round().astype(int)
            out.append(f'{path[-33:]:<34}{name:<10}{r:>5}{g:>5}{b:>5}{m["lum"]:>7.1f}{m["sat"]:>6.2f}'
                       f'{m["hue"]:>6.0f}{ratio:>9}')
    return '\n'.join(out)


def draw(path: str, boxes: dict, out: str) -> None:
    """Save `path` with `boxes` outlined and labelled, to check their framing."""
    with Image.open(path) as im:
        im = im.convert('RGB')
    pen = ImageDraw.Draw(im)
    for name, (x0, y0, x1, y1) in boxes.items():
        rect = (x0 * im.width, y0 * im.height, x1 * im.width, y1 * im.height)
        pen.rectangle(rect, outline=(255, 0, 255), width=3)
        pen.text((rect[0] + 4, rect[1] + 4), name, fill=(255, 0, 255))
    im.save(out)


def main(argv=None) -> int:
    """Measure the boxes on every image and print the table."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('images', nargs='+', help='screenshots; the first is the reference (FNV)')
    ap.add_argument('--spot', choices=sorted(SPOTS), help='use that spot\'s boxes')
    ap.add_argument('--box', action='append', default=[], help='NAME=x0,y0,x1,y1, added to or replacing a spot box')
    ap.add_argument('--draw', help='save the first image with the boxes outlined to this file')
    args = ap.parse_args(argv)
    boxes = dict(SPOTS.get(args.spot, {}))
    boxes.update(parse_box(spec) for spec in args.box)
    if not boxes:
        ap.error('give --spot or at least one --box')
    if args.draw:
        draw(args.images[0], boxes, args.draw)
    print(table(args.images, boxes))
    return 0


if __name__ == '__main__':
    sys.exit(main())
