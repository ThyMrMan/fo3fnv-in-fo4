"""The Classic Look plugin: FNV's flat lights and straight tone over a built plugin, as overrides only.

    py -3.14 -m fo4_import.classic_look --plugin <built FalloutNV.esm> [--data <its Data folder>] --out <folder>

Every Key light's shadow copy (spike.light_roles) is overridden with its
shadow flags cleared. Every FNV imagespace (TX00 under LUT_FOLDER) points
at a Classic LUT, the built LUT after FNV's straight curve (fnv_tone),
with exposure pinned where that curve keeps middle grey
(classic_exposure). Masters are the built plugin's masters then the
plugin, so its FormIDs carry unchanged; ticking it on or off needs no new
save.

See: docs/fork/fo4_look.md#route-lights
"""
import argparse
import struct
from pathlib import Path

import numpy as np

from fo4_import.base.install import masters_of
from fo4_import.base.writer import FO4PluginWriter, pack_fo4_record
from fo4_import.spike.imagespace import (CURVE_SAMPLES, DISPLAY_GAMMA, FO4_WHITE, LUT_FOLDER, apply_lut, base_hdr,
                                         fo4_display, identity, lut_dds, read_lut)
from tes5_import.base.tes5_reader import subrecords, walk
from tes5_import.base.writer import pack_subrecord

#: Where Classic LUTs go, under Textures.
CLASSIC_FOLDER = 'Effects\\LUTs\\FNVClassic'
#: FO4 LIGH DATA shadow flags (spot, hemisphere, omnidirectional) and their offset in DATA.
SHADOWS, FLAGS_AT = 0x400 | 0x800 | 0x1000, 12


def plugin_name(built: str) -> str:
    """The Classic plugin's file name for built plugin `built`."""
    return f'{Path(built).stem} - Classic Look.esl'


def fnv_tone(display: np.ndarray, tonemap_e: float, middle_grey: float) -> np.ndarray:
    """FO4 display colours re-toned with FNV's straight curve, anchored where FO4 shows `middle_grey`.

    See: docs/fork/fo4_look.md#night
    """
    scene = np.linspace(0.0, FO4_WHITE / 2, CURVE_SAMPLES)
    exposed = np.interp(display, fo4_display(scene, tonemap_e), scene)
    anchor = fo4_display(np.array(middle_grey), tonemap_e)
    return anchor * (exposed / middle_grey) ** (1 / DISPLAY_GAMMA)


def classic_exposure(tonemap_e: float, middle_grey: float) -> float:
    """The exposure at which FO4 under fnv_tone shows exposed colour c as c^(1/2.2).

    See: docs/fork/fo4_spikes.md#spike-2-imagespace
    """
    return middle_grey / float(fo4_display(np.array(middle_grey), tonemap_e)) ** DISPLAY_GAMMA


def classic_lut(modern: np.ndarray, hdr: tuple) -> np.ndarray:
    """Classic LUT colours of `modern` (read_lut) under `hdr` (base_hdr)."""
    return apply_lut(np.clip(fnv_tone(identity(), *hdr), 0.0, 1.0), modern)


def unshadowed(body: bytes) -> bytes:
    """LIGH `body`'s subrecords with its DATA shadow flags cleared."""
    subs = b''
    for tag, data in subrecords(body):
        if tag == b'DATA':
            flags = struct.unpack_from('<I', data, FLAGS_AT)[0] & ~SHADOWS
            data = data[:FLAGS_AT] + struct.pack('<I', flags) + data[FLAGS_AT + 4:]
        subs += pack_subrecord(tag.decode('latin1'), data)
    return subs


def classic_imgs(body: bytes, lut: str) -> bytes:
    """IMGS `body`'s subrecords with TX00 `lut` and auto exposure pinned at classic_exposure."""
    exposure, subs = classic_exposure(*base_hdr(body)), b''
    for tag, data in subrecords(body):
        if tag == b'HNAM':
            data = data[:16] + struct.pack('<2f', exposure, exposure) + data[24:]
        elif tag == b'TX00':
            data = lut.encode() + b'\0'
        subs += pack_subrecord(tag.decode('latin1'), data)
    return subs


def _imagespace(rec, data_dir: Path, out: Path) -> 'bytes | None':
    """The Classic override of built IMGS `rec`, its LUT written under `out`; None when it is not an FNV one."""
    tx00 = dict(subrecords(rec.body)).get(b'TX00', b'').rstrip(b'\0').decode('latin1')
    if not tx00.lower().startswith(LUT_FOLDER.lower() + '\\'):
        return None
    name = tx00.rpartition('\\')[2]
    modern = read_lut((data_dir / 'Textures' / tx00.replace('\\', '/')).read_bytes())
    target = out / 'Textures' / CLASSIC_FOLDER.replace('\\', '/') / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(lut_dds(classic_lut(modern, base_hdr(rec.body))))
    return classic_imgs(rec.body, f'{CLASSIC_FOLDER}\\{name}')


def build(plugin: Path, data_dir: Path, out: Path) -> dict:
    """Write the Classic plugin for built `plugin` (its LUTs under `data_dir`) into folder `out`; counts by type."""
    data = plugin.read_bytes()
    masters = [*masters_of(data), plugin.name]
    own, counts = len(masters) - 1, {'LIGH': 0, 'IMGS': 0}
    writer = FO4PluginWriter(masters=masters, is_esm=False, is_esl=True, description='F3NV Classic Look')
    for rec, _ in walk(data, b'LIGH', b'IMGS'):
        if rec.form_id >> 24 != own:
            continue
        sig = rec.sig.decode()
        if sig == 'LIGH':
            edid = dict(subrecords(rec.body)).get(b'EDID', b'').rstrip(b'\0')
            subs = unshadowed(rec.body) if edid.endswith(b'_Shadow') else None
        else:
            subs = _imagespace(rec, data_dir, out)
        if subs is not None:
            writer.add_record(sig, pack_fo4_record(sig, rec.form_id, rec.flags, subs))
            counts[sig] += 1
    out.mkdir(parents=True, exist_ok=True)
    writer.write(str(out / plugin_name(plugin.name)))
    return counts


def main() -> None:
    """Command line: build the Classic plugin."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--plugin', required=True, type=Path, help='the built plugin (FalloutNV.esm)')
    ap.add_argument('--data', type=Path, help="folder holding the built plugin's Textures (default: its folder)")
    ap.add_argument('--out', required=True, type=Path, help='folder to write the Classic plugin and its LUTs into')
    args = ap.parse_args()
    counts = build(args.plugin, args.data or args.plugin.parent, args.out)
    print(f'{args.out / plugin_name(args.plugin.name)}: {counts["LIGH"]} lights, {counts["IMGS"]} imagespaces')


if __name__ == '__main__':
    main()
