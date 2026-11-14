"""BodySlide's files and Outfit Studio's Conform, to give converted outfits a BodySlide body's sliders.

A body mod (CBBE) ships a slider set (`SliderSets\\*.osp`, XML) naming its base NIF and, per slider, the
vertex moves in a shape data file (`ShapeData\\<folder>\\*.osd`, binary). An outfit project is the same three
files for the outfit; BodySlide builds it by adding each slider's moves times its value. Conform carries the
body's moves onto the outfit, as Outfit Studio's does (Automorph::GenerateResultDiff, GPL-3.0, ported with
credit: github.com/ousnius/BodySlide-and-Outfit-Studio).

See: docs/fork/fo4_bodies_cbbe.md#outfit-studio
"""

import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from fo4_import.nif import file as nif_file
from fo4_import.nif.blocks import Reader, read_tri_shape

#: An .osd file's magic (the uint32 "OSD\0" as BodySlide writes it) and version.
OSD_MAGIC, OSD_VERSION = b'\x00DSO', 1
#: One .osd move: a vertex index and its move.
OSD_ROW = np.dtype([('i', '<u2'), ('d', '<3f4')])
#: Outfit Studio's Conform defaults (ConformOptions.h): reference vertices within this radius, the nearest this many.
PROXIMITY_RADIUS, MAX_RESULTS = 10.0, 10
#: The inverse-distance weight of a reference vertex at exactly the outfit vertex.
EXACT_WEIGHT = 1000.0
#: Shapes whose geometry BodySlide reads.
SHAPE_KINDS = ('BSTriShape', 'BSSubIndexTriShape')
XML_HEAD = b'<?xml version="1.0" encoding="UTF-8"?>\n'


@dataclass
class Reference:
    """A body's reference shape: its points, and per slider its attributes and moves (vertex indices, moves)."""
    points: np.ndarray
    sliders: list


def read_osd(data: bytes) -> dict:
    """{data name: (vertex indices, (n, 3) moves)} of an .osd file."""
    if data[:4] != OSD_MAGIC:
        raise ValueError('not an .osd file')
    count, pos, out = struct.unpack_from('<I', data, 8)[0], 12, {}
    for _ in range(count):
        n = data[pos]
        name = data[pos + 1:pos + 1 + n].decode('cp1252')
        size = struct.unpack_from('<H', data, pos + 1 + n)[0]
        pos += 3 + n
        rows = np.frombuffer(data, OSD_ROW, size, pos)
        out[name] = (rows['i'].astype(int), rows['d'].astype(float))
        pos += OSD_ROW.itemsize * size
    return out


def write_osd(diffs: dict) -> bytes:
    """An .osd file of {data name: (vertex indices, (n, 3) moves)}."""
    out = OSD_MAGIC + struct.pack('<II', OSD_VERSION, len(diffs))
    for name, (index, moves) in diffs.items():
        raw = name.encode('cp1252')
        rows = np.zeros(len(index), OSD_ROW)
        rows['i'], rows['d'] = index, moves
        out += bytes([len(raw)]) + raw + struct.pack('<H', len(index)) + rows.tobytes()
    return out


def conform(ref_points: np.ndarray, diff: tuple, points: np.ndarray) -> tuple:
    """(vertex indices, moves) of `points` for one reference slider `diff` (indices, moves): each point takes
    the inverse-distance mix of the moves of its MAX_RESULTS nearest reference vertices within PROXIMITY_RADIUS
    that have one, nothing when the nearest has none."""
    dist, near = cKDTree(ref_points).query(points, k=MAX_RESULTS, distance_upper_bound=PROXIMITY_RADIUS)
    moves, has = np.zeros((len(ref_points) + 1, 3)), np.zeros(len(ref_points) + 1, bool)
    moves[diff[0]], has[diff[0]] = diff[1], True
    weight = np.where(dist == 0, EXACT_WEIGHT, 1.0 / np.maximum(dist, 1e-30)) * has[near]
    total = weight.sum(1)
    mixed = (moves[near] * weight[:, :, None]).sum(1) / np.maximum(total, 1e-30)[:, None]
    kept = np.flatnonzero(has[near[:, 0]] & np.any(mixed != 0, axis=1))
    return kept, mixed[kept]


def shapes(data: bytes) -> dict:
    """{shape name: (n, 3) vertex positions} of a Fallout 4 NIF's geometry."""
    nif, out = nif_file.read(data), {}
    for kind, block in nif.blocks:
        if kind in SHAPE_KINDS:
            shape = read_tri_shape(Reader(block)) if isinstance(block, bytes) else block
            out[nif.strings[shape['name']]] = np.array([v['position'] for v in shape['vertices']], float)
    return out


def read_xml(path: Path) -> ET.Element:
    """An XML file's root (BodySlide's files may start with a byte-order mark)."""
    return ET.fromstring(path.read_bytes().removeprefix(b'\xef\xbb\xbf'))


def reference(tools_dir: Path, template: str) -> Reference:
    """The reference shape of BodySlide reference template `template` (RefTemplates\\*.xml) under BodySlide
    folder `tools_dir`, with its conformable sliders (no zap or UV sliders)."""
    found = next(t for f in sorted((tools_dir / 'RefTemplates').glob('*.xml')) for t in read_xml(f)
                 if t.text == template)
    sets = read_xml(tools_dir / found.get('sourcefile'))
    slider_set = next(s for s in sets if s.get('name') == found.get('set'))
    folder = tools_dir / 'ShapeData' / slider_set.findtext('DataFolder')
    target = next(s.get('target') for s in slider_set.iter('Shape') if s.text == found.get('shape'))
    points = shapes((folder / slider_set.findtext('SourceFile')).read_bytes())[found.get('shape')]
    osd, sliders = {}, []
    for slider in slider_set.iter('Slider'):
        data = next((d for d in slider.iter('Data') if d.get('target') == target), None)
        if data is None or slider.get('zap') == 'true' or slider.get('uv') == 'true':
            continue
        file, name = data.text.split('\\')
        osd.setdefault(file, read_osd((folder / file).read_bytes()))
        sliders.append((dict(slider.attrib), osd[file].get(name, (np.zeros(0, int), np.zeros((0, 3))))))
    return Reference(points, sliders)


def data_name(target: str, slider: str) -> str:
    """BodySlide's data name: 'OutfitF:0', 'Butt' -> 'OutfitF_0Butt'."""
    return re.sub(r'[: ]', '_', target) + slider


def project(name: str, outfit: dict, ref: Reference, paths: tuple) -> tuple:
    """(<SliderSet> element, .osd bytes) of outfit `name`: {shape: points} conformed to `ref`; `paths` are its
    (data folder, source NIF, game output folder, output file without .nif)."""
    folder, source, out_path, out_file = paths
    root = ET.Element('SliderSet', name=name)
    for tag, text in (('DataFolder', folder), ('SourceFile', source), ('OutputPath', out_path)):
        ET.SubElement(root, tag).text = text
    ET.SubElement(root, 'OutputFile', GenWeights='false').text = out_file
    for shape in outfit:
        ET.SubElement(root, 'Shape', target=shape).text = shape
    osd_name, diffs = Path(source).with_suffix('.osd').name, {}
    for attrib, diff in ref.sliders:
        slider = ET.SubElement(root, 'Slider', attrib)
        for shape, points in outfit.items():
            moved = conform(ref.points, diff, points)
            if len(moved[0]):
                key = data_name(shape, attrib['name'])
                diffs[key] = moved
                ET.SubElement(slider, 'Data', name=key, target=shape, local='true').text = f'{osd_name}\\{key}'
    return root, write_osd(diffs)


def _xml(root: ET.Element) -> bytes:
    """`root` as an indented UTF-8 XML file."""
    ET.indent(root, '    ')
    return XML_HEAD + ET.tostring(root, 'utf-8') + b'\n'


def slider_sets(sets: list) -> bytes:
    """An .osp file holding `sets` (<SliderSet> elements)."""
    root = ET.Element('SliderSetInfo', version='1')
    root.extend(sets)
    return _xml(root)


def slider_group(group: str, members: list) -> bytes:
    """A SliderGroups file putting slider sets `members` in group `group`."""
    root = ET.Element('SliderGroups')
    node = ET.SubElement(root, 'Group', name=group)
    for member in members:
        ET.SubElement(node, 'Member', name=member)
    return _xml(root)
