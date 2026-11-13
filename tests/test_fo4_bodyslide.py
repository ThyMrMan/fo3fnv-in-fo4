"""BodySlide files and Outfit Studio's Conform (fo4_import.nif.bodyslide), on synthetic data."""

import xml.etree.ElementTree as ET

import numpy as np

from fo4_import.nif import bodyslide


def test_osd_round_trip():
    """write_osd then read_osd gives back every name, index and move (float32)."""
    diffs = {'OutfitF_0Butt': (np.array([0, 7, 65535]), np.array([[1.0, -2.0, 0.5], [0, 0, 0.25], [3, 3, 3]])),
             'Empty': (np.zeros(0, int), np.zeros((0, 3)))}
    data = bodyslide.write_osd(diffs)
    assert data[:4] == bodyslide.OSD_MAGIC and len(data) == 12 + (1 + 13 + 2 + 3 * 14) + (1 + 5 + 2)
    back = bodyslide.read_osd(data)
    assert list(back) == list(diffs)
    for name, (index, moves) in diffs.items():
        assert back[name][0].tolist() == index.tolist()
        assert np.allclose(back[name][1], moves)


def test_conform_follows_nearest_moved_vertex():
    """A slider moving one reference vertex moves an outfit vertex on it by the same, a far one not at all."""
    ref = np.array([[0.0, 0, 0], [50, 0, 0], [0, 50, 0]])
    diff = (np.array([0]), np.array([[0.0, 0, 2.0]]))
    index, moves = bodyslide.conform(ref, diff, np.array([[0.0, 0, 0], [0, 49, 0], [200, 0, 0]]))
    assert index.tolist() == [0]
    assert np.allclose(moves, [[0, 0, 2.0]])


def test_conform_mixes_by_inverse_distance():
    """Between two moved reference vertices, a point's move is their inverse-distance mix."""
    ref = np.array([[0.0, 0, 0], [4, 0, 0]])
    diff = (np.array([0, 1]), np.array([[0.0, 0, 1.0], [0, 0, 3.0]]))
    index, moves = bodyslide.conform(ref, diff, np.array([[1.0, 0, 0]]))
    assert index.tolist() == [0]
    assert np.allclose(moves, [[0, 0, (1 / 1 * 1 + 1 / 3 * 3) / (1 / 1 + 1 / 3)]])


def test_project_names_data_per_shape():
    """A project holds one <Data> per shape a slider moves, pointing into the outfit's .osd."""
    ref = bodyslide.Reference(np.array([[0.0, 0, 0]]), [({'name': 'Butt', 'invert': 'false', 'default': '0'},
                                                         (np.array([0]), np.array([[1.0, 0, 0]])))])
    outfit = {'Top:0': np.array([[0.0, 0, 1]]), 'Far': np.array([[90.0, 0, 0]])}
    root, osd = bodyslide.project('F3NV - top', outfit, ref, ('F3NV', 'top.nif', 'Meshes\\fnv', 'top_female'))
    data = root.findall('Slider/Data')
    assert [(d.get('name'), d.get('target'), d.text) for d in data] == [('Top_0Butt', 'Top:0', 'top.osd\\Top_0Butt')]
    assert list(bodyslide.read_osd(osd)) == ['Top_0Butt']
    text = bodyslide.slider_sets([root])
    assert ET.fromstring(text).find('SliderSet/OutputFile').text == 'top_female'
