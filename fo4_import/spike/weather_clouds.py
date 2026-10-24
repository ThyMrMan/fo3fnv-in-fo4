"""FNV's weather clouds on a converted weather: FO4's cloud layers in FNV's cloud colours.

An FNV weather has four cloud layers (DNAM, CNAM, ANAM, BNAM: layers 0 to 3);
`sky\\alpha.dds` is an empty one. Its cloud colours (PNAM) are RGBA per layer
for FNV's six times of day (sunrise, day, sunset, night, high noon,
midnight). FNV's cloud textures do not fit FO4's sky dome (played
2026-10-23: hard seams), so the converted weather keeps the template's own
cloud layers and colours them as FNV's first drawn layer, over FO4's times
(FO4_TIMES). A weather FNV draws no clouds in (no drawn layer, or none whose
texture FNV has) gets every layer disabled (NAM1).

See: docs/fork/fo4_look.md#lighting
"""

import struct

#: FNV's cloud layer texture subrecords, layer 0 to 3, and the texture that draws nothing.
FNV_LAYERS, EMPTY = (b'DNAM', b'CNAM', b'ANAM', b'BNAM'), 'sky\\alpha.dds'
#: FNV's times of day in its cloud colours; FO4's cloud layers.
FNV_TIMES, FO4_LAYERS = 6, 32


def fnv_layers(source: dict) -> list:
    """[(FNV layer index, texture)] of FNV weather `source`'s ({tag: data}) cloud layers that draw something."""
    out = []
    for index, tag in enumerate(FNV_LAYERS):
        texture = source.get(tag, b'').rstrip(b'\0').decode('latin1')
        if texture and texture.lower() != EMPTY:
            out.append((index, texture))
    return out


def cloud_colours(source: dict, layer: int, times: tuple) -> bytes:
    """FO4's PNAM: FNV layer `layer`'s colours (FNV weather `source`) over FO4 `times`, for every FO4 layer."""
    colours = source.get(b'PNAM', b'')
    one = b''.join(colours[(layer * FNV_TIMES + t) * 4:(layer * FNV_TIMES + t) * 4 + 4] or bytes(4) for t in times)
    return one * FO4_LAYERS


def with_clouds(builder, template: list, source: dict, times: tuple) -> list:
    """Weather subrecords `template` [(tag, data)] with its clouds in FNV weather `source`'s colours, or all off
    when FNV draws none there (a layer whose texture FNV lacks draws nothing)."""
    drawn = [(i, t) for i, t in fnv_layers(source)
             if (builder.export_dir / ('textures/' + t.replace('\\', '/').lower())).exists()]
    builder.counts['weather without FNV clouds'] += not drawn
    fields = {b'PNAM': cloud_colours(source, drawn[0][0], times)} if drawn else \
        {b'NAM1': struct.pack('<I', 0xFFFFFFFF)}
    return [(tag, fields.get(tag, data)) for tag, data in template]
