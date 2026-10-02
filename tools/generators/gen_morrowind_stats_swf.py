"""
Author the Morrowind stats window and level-up dialog SWFs, and their layout header.

Two standalone movies, each a menu of its own, drawn exactly like the dialogue
window (`gen_morrowind_menu_swf.py`): Morrowind's art from the registered
install composed into one chrome bitmap, OpenMW's embedded face, and every
string a dynamic field the plugin writes. Rows are single-line fields the
plugin places, so a list's pitch is the layout's, not the font's.

- `morrowind_stats.swf`: `openmw_stats_window.layout`.
- `morrowind_levelup.swf`: `openmw_levelup_dialog.layout`, with every class
  image (`textures/levelup`) as a hidden sprite and the gold coins.

🛑 The art is NOT committed; like the dialogue menu this needs a Morrowind
install. The header IS committed, so the plugin builds without one.

See: docs/plans/character_sheet.md#m2-swf
"""

import argparse
import os
import struct

from asset_convert.ui.morrowind_menu_art import (ICONS, SCROLL_TRACK, SCROLL_W,
                                                 compose_box, compose_button,
                                                 compose_cap, compose_frame,
                                                 compose_head, compose_scrollbar,
                                                 compose_stat_bar,
                                                 compose_thumb, load)
from asset_convert.ui.swf import (Swf, Tag, define_bits_lossless2,
                                  define_shape3_bitmap_rects,
                                  define_shape3_solid_rects, define_sprite,
                                  pack_rect, place_object2)
from asset_convert.ui.ui_menus import premultiplied_argb
from tools.generators.gen_morrowind_menu_swf import (
    ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, BODY_HEIGHT_TWIPS, CAPTION_PAD,
    CHAR_MW_FONT, COLOR_BACKGROUND, FONT_COLORS, STAGE_H, STAGE_W, TAG_END,
    TAG_FILE_ATTRIBUTES, TAG_SET_BACKGROUND_COLOR, TAG_SHOW_FRAME, THUMB_H,
    THUMB_W, THUMB_X, TWIP, define_edit_text, embed_font, text_top)

#: Where the plugin's copy of both layouts is written.
HEADER_PATH = 'tes_runtime/morrowind/plugin/stats_layout.h'

#: The two movies, as the game loads them under Interface/.
STATS_MOVIE = 'morrowind_stats.swf'
LEVELUP_MOVIE = 'morrowind_levelup.swf'

#: `Morrowind.ini` `[FontColor]` color_health, color_magic, color_fatigue: the three bar tints.
BAR_COLORS = ((200, 60, 30), (53, 69, 159), (0, 150, 60))

#: MW_Window at `openmw_stats_window.layout`'s size, its caption strip, client origin and inner frame.
STATS_W = 500
STATS_H = 342
CAPTION = (4, 4, STATS_W - 8, 20)
CLIENT = (8, 28)
INNER_FRAME = (4, 24, STATS_W - 8, STATS_H - 28)

#: The layout's MW_Box panes in CLIENT space: dynamic stats, level box, attributes, skills.
DYNAMIC_BOX = (8, 8, 212, 62)
INFO_BOX = (8, 78, 212, 62)
ATTRIBUTE_BOX = (8, 148, 212, 152)
SKILL_BOX = (228, 8, 248, 292)

#: A dynamic stat row inside its box: 4 px in, 18 px apart; the label 70 wide, the bar from 74 to 204.
BOX_PAD = 4
ROW_H = 18
BAR_LABEL_W = 70
BAR_X = 74
BAR_W = 130

#: The level box's HBoxes sit at these offsets inside it.
INFO_ROWS = (4, 24, 42)

#: Attribute rows, each ROW_H tall.
ATTRIBUTE_ROWS = 8

#: Row fields kept for the skill list; the plugin places each, and a partly shown row is hidden.
SKILL_FIELDS = 16

#: Character ids for the stats movie: chrome, the caption cover, three bar covers, sprites, fields.
CHAR_STATS_BMP = 20
CHAR_COVER = 22
CHAR_BAR_COVER_FIRST = 30
CHAR_STATS_SPRITE_FIRST = 60
CHAR_STATS_FIELD_FIRST = 100

#: MW_Dialog's size: 10 px padding around a 420 px column, children 8 px apart.
DIALOG_W = 440
DIALOG_H = 496

#: The class image box and the image inside it, stretched from the texture's 256x128.
IMAGE_BOX = (24, 10, 391, 198)
IMAGE = (28, 14, 383, 190)

#: The level line, the level text, the coin row, the attribute grid and OK, in DIALOG space.
LEVEL_TEXT = (24, 216, 391, 24)
DESCRIPTION = (24, 248, 391, 90)
COIN_ROW = (0, 346, DIALOG_W, 16)
ASSIGN = (10, 370, 420, 84)
OK_BUTTON = (DIALOG_W - 10 - 64, 462, 64, 24)

#: LevelupDialog's grid: two columns at these x offsets, 20 px rows, the multiplier 20 px before the name.
COLUMNS = (32, 218)
GRID_ROW_H = 20
MULTIPLIER_W = 20
NAME_W = 120
VALUE_W = 40

#: Attributes per grid column: OpenMW's ceil(attributes / columns).
PER_COLUMN = (ATTRIBUTE_ROWS + len(COLUMNS) - 1) // len(COLUMNS)

#: The coin icon's size, the gap resetCoins leaves between coins, and how many there are.
COIN = 16
COIN_SPACING = 33
COINS = 3

#: MW_Button's caption inset, as the dialogue window's Goodbye.
BUTTON_INSET = (4, 3)

#: Every class image LevelupDialog::getLevelupClassImage can name.
CLASSES = ('acrobat', 'agent', 'archer', 'assassin', 'barbarian', 'bard',
           'battlemage', 'crusader', 'healer', 'knight', 'mage', 'monk',
           'nightblade', 'pilgrim', 'rogue', 'scout', 'sorcerer',
           'spellsword', 'thief', 'warrior', 'witchhunter')

#: The class texture's own pixel size, which the image rect stretches.
CLASS_PIXELS = (256, 128)

#: Character ids for the level-up movie: chrome, coins, class images (three each), then fields.
CHAR_DIALOG_BMP = 20
CHAR_COIN_FIRST = 30
CHAR_CLASS_FIRST = 60
CHAR_DIALOG_FIELD_FIRST = 200


# ---------------------------------------------------------------------------
# Shared pieces
# ---------------------------------------------------------------------------

def stats_origin() -> tuple:
    """The stats window's top-left on the stage: centered."""
    return ((STAGE_W - STATS_W) // 2, (STAGE_H - STATS_H) // 2)


def dialog_origin() -> tuple:
    """The level-up dialog's top-left on the stage: centered."""
    return ((STAGE_W - DIALOG_W) // 2, (STAGE_H - DIALOG_H) // 2)


def client(rect: tuple) -> tuple:
    """A CLIENT-space rect of the stats window moved into WINDOW space."""
    return (rect[0] + CLIENT[0], rect[1] + CLIENT[1], rect[2], rect[3])


def on_stage(rect: tuple, origin: tuple) -> tuple:
    """A window-space rect moved onto the stage."""
    return (rect[0] + origin[0], rect[1] + origin[1], rect[2], rect[3])


def line_in(box: tuple) -> tuple:
    """A field rect whose one line is vertically centered in `box`."""
    x, y, w, h = box
    return (x, text_top(y, h), w, h)


def field(char_id: int, rect: tuple, origin: tuple, color: str = 'normal',
          align: int = ALIGN_LEFT) -> Tag:
    """A dynamic field in the embedded face at a window-space rect."""
    return define_edit_text(char_id, *on_stage(rect, origin), '', '',
                            font_id=CHAR_MW_FONT, rgb=FONT_COLORS[color],
                            height=BODY_HEIGHT_TWIPS, align=align)


def sprite(char_id: int, image, name: str, rect: tuple, origin: tuple,
           pixels: tuple = None) -> list:
    """`image` in a one-frame SPRITE placed at a window-space rect.

    Returns `[bitmap, shape, sprite, (sprite_id, name, stage_xy)]`. With
    `pixels`, the bitmap's own size, the rect's size stretches it.
    """
    x, y, w, h = on_stage(rect, origin)
    iw, ih = image.size
    piece = (char_id, 0, 0, w, h, pixels) if pixels else (char_id, 0, 0, iw, ih)
    return [
        define_bits_lossless2(char_id, iw, ih, premultiplied_argb(image)),
        define_shape3_bitmap_rects(char_id + 1, [piece]),
        define_sprite(char_id + 2,
                      [place_object2(depth=1, character_id=char_id + 1)]),
        (char_id + 2, name, (x, y)),
    ]


def cover(char_id: int, name: str, rect: tuple, origin: tuple,
          depth: int) -> list:
    """A 1 px wide black sprite `rect[3]` tall at a window-space rect's
    top-left; the plugin sets its `_x` and `_width`."""
    x, y, _w, h = on_stage(rect, origin)
    return [
        define_shape3_solid_rects(char_id, [(0, 0, 1, h)], (0, 0, 0, 255)),
        define_sprite(char_id + 1, [place_object2(depth=1, character_id=char_id)]),
        place_object2(depth=depth, character_id=char_id + 1, name=name,
                      translate=(x, y)),
    ]


def chrome_tags(char_bmp: int, image, origin: tuple) -> list:
    """The composed chrome as one bitmap shape at depth 1."""
    w, h = image.size
    return [
        define_bits_lossless2(char_bmp, w, h, premultiplied_argb(image)),
        define_shape3_bitmap_rects(char_bmp + 1,
                                   [(char_bmp, origin[0], origin[1], w, h)]),
        place_object2(depth=1, character_id=char_bmp + 1, name='Window_mc'),
    ]


def place_all(parts: list, fields: list, depth: int) -> list:
    """Sprites, then fields, each at the next depth from `depth`."""
    tags = []
    for bitmap, shape, clip, (char_id, name, at) in parts:
        tags += [bitmap, shape, clip,
                 place_object2(depth=depth, character_id=char_id, name=name,
                               translate=at)]
        depth += 1
    for tag, name in fields:
        tags += [tag, place_object2(depth=depth,
                                    character_id=tag.character_id, name=name)]
        depth += 1
    return tags


def movie(tags: list) -> Swf:
    """A one-frame stage-sized movie of `tags`, with the embedded face."""
    head = [Tag(TAG_FILE_ATTRIBUTES, struct.pack('<I', 0)),
            Tag(TAG_SET_BACKGROUND_COLOR, bytes([0, 0, 0])), embed_font()]
    tail = [Tag(TAG_SHOW_FRAME, b''), Tag(TAG_END, b'')]
    return Swf(version=9,
               frame_size=pack_rect(0, STAGE_W * TWIP, 0, STAGE_H * TWIP),
               framerate=(24 << 8), framecount=1, tags=head + tags + tail)


# ---------------------------------------------------------------------------
# Stats window
# ---------------------------------------------------------------------------

def bar_rect(row: int) -> tuple:
    """Dynamic stat `row`'s bar, in WINDOW space."""
    x, y, _w, _h = client(DYNAMIC_BOX)
    return (x + BOX_PAD + BAR_X, y + BOX_PAD + row * ROW_H, BAR_W, ROW_H)


def bar_fill_rect(row: int) -> tuple:
    """The tinted part of a bar, inside its box border, in WINDOW space."""
    x, y, w, h = bar_rect(row)
    return (x + 2, y + 2, w - 4, h - 4)


def row_rect(box: tuple, offset: int) -> tuple:
    """A full-width row `offset` px down a CLIENT-space box, in WINDOW space."""
    x, y, w, _h = client(box)
    return (x + BOX_PAD, y + offset, w - 2 * BOX_PAD, ROW_H)


def skill_view() -> tuple:
    """The skill list's rows area, beside its scrollbar, in WINDOW space."""
    x, y, w, h = client(SKILL_BOX)
    return (x + BOX_PAD, y + BOX_PAD, w - 2 * BOX_PAD - SCROLL_W - 2,
            h - 2 * BOX_PAD)


def skill_scroll() -> tuple:
    """The skill list's scrollbar, at the box's inner right edge, in WINDOW space."""
    x, y, w, h = client(SKILL_BOX)
    return (x + w - BOX_PAD - SCROLL_W, y + BOX_PAD, SCROLL_W, h - 2 * BOX_PAD)


def compose_stats(export_root):
    """The stats window's chrome: frames, caption plate, four panes, three full bars."""
    panel = compose_frame(export_root, STATS_W, STATS_H, fill=COLOR_BACKGROUND)
    ix, iy, iw, ih = INNER_FRAME
    panel.alpha_composite(compose_frame(export_root, iw, ih), (ix, iy))
    cx, cy, cw, ch = CAPTION
    panel.alpha_composite(compose_head(export_root, cw, ch), (cx, cy))
    for box in (DYNAMIC_BOX, INFO_BOX, ATTRIBUTE_BOX, SKILL_BOX):
        bx, by, bw, bh = client(box)
        panel.alpha_composite(compose_box(export_root, bw, bh), (bx, by))
    for row, rgb in enumerate(BAR_COLORS):
        bx, by, bw, bh = bar_rect(row)
        panel.alpha_composite(compose_stat_bar(export_root, bw, bh, rgb),
                              (bx, by))
    return panel


def paired_rows(ids, rects: list, name: str) -> list:
    """A name field and a right-aligned value field per rect: `Name<i>`, `Value<i>`."""
    origin, out = stats_origin(), []
    for row, rect in enumerate(rects):
        out.append((field(next(ids), line_in(rect), origin), f'{name}Name{row}'))
        out.append((field(next(ids), line_in(rect), origin, 'header',
                          ALIGN_RIGHT), f'{name}Value{row}'))
    return out


def stats_fields() -> list:
    """Every stats-window field as `(tag, instance_name)`."""
    origin = stats_origin()
    ids = iter(range(CHAR_STATS_FIELD_FIRST, CHAR_STATS_FIELD_FIRST + 200))
    out = [(field(next(ids), line_in(CAPTION), origin, 'header', ALIGN_CENTER),
            'Title')]
    for row in range(len(BAR_COLORS)):
        x, y, _w, _h = row_rect(DYNAMIC_BOX, BOX_PAD + row * ROW_H)
        out.append((field(next(ids), line_in((x, y, BAR_LABEL_W, ROW_H)),
                          origin), f'BarLabel{row}'))
        out.append((field(next(ids), line_in(bar_rect(row)), origin,
                          align=ALIGN_CENTER), f'BarValue{row}'))
    out += paired_rows(ids, [row_rect(INFO_BOX, y) for y in INFO_ROWS], 'Info')
    out += paired_rows(ids, [row_rect(ATTRIBUTE_BOX, BOX_PAD + r * ROW_H)
                             for r in range(ATTRIBUTE_ROWS)], 'Attr')
    x, y, w, _h = skill_view()
    out += paired_rows(ids, [(x, y + r * ROW_H, w, ROW_H)
                             for r in range(SKILL_FIELDS)], 'Skill')
    return out


def stats_sprites(export_root) -> list:
    """The caption caps, the skill scrollbar and its thumb."""
    origin, bar = stats_origin(), skill_scroll()
    parts = [
        (compose_cap(export_root, 'right'), 'CapLeft', CAPTION),
        (compose_cap(export_root, 'left'), 'CapRight', CAPTION),
        (compose_scrollbar(export_root, bar[3]), 'SkillScroll', bar),
        (compose_thumb(export_root, THUMB_W, THUMB_H), 'SkillThumb',
         (bar[0] + THUMB_X, bar[1] + SCROLL_TRACK[0], THUMB_W, THUMB_H)),
    ]
    return [sprite(CHAR_STATS_SPRITE_FIRST + 3 * i, image, name, rect, origin)
            for i, (image, name, rect) in enumerate(parts)]


def stats_window(export_root) -> Swf:
    """The stats window movie.

    See: docs/plans/character_sheet.md#m2-swf
    """
    origin = stats_origin()
    tags = chrome_tags(CHAR_STATS_BMP, compose_stats(export_root), origin)
    tags += cover(CHAR_COVER, 'Cover', CAPTION, origin, 2)
    for row in range(len(BAR_COLORS)):
        tags += cover(CHAR_BAR_COVER_FIRST + 2 * row, f'BarCover{row}',
                      bar_fill_rect(row), origin, 3 + row)
    tags += place_all(stats_sprites(export_root), stats_fields(),
                      3 + len(BAR_COLORS))
    return movie(tags)


# ---------------------------------------------------------------------------
# Level-up dialog
# ---------------------------------------------------------------------------

def grid_row(attribute: int) -> tuple:
    """`(column_x, row_y)` of an attribute's grid row, in DIALOG space."""
    column, row = divmod(attribute, PER_COLUMN)
    return ASSIGN[0] + COLUMNS[column], ASSIGN[1] + row * GRID_ROW_H


def compose_dialog(export_root):
    """The level-up dialog's chrome: frame, the image box and the OK button."""
    panel = compose_frame(export_root, DIALOG_W, DIALOG_H, fill=COLOR_BACKGROUND)
    bx, by, bw, bh = IMAGE_BOX
    panel.alpha_composite(compose_box(export_root, bw, bh), (bx, by))
    ox, oy, ow, oh = OK_BUTTON
    panel.alpha_composite(compose_button(export_root, ow, oh), (ox, oy))
    return panel


def ok_caption_rect() -> tuple:
    """The OK caption box, in DIALOG space."""
    x, y, w, h = OK_BUTTON
    return line_in((x + BUTTON_INSET[0], y + BUTTON_INSET[1],
                    w - 2 * BUTTON_INSET[0], h - 2 * BUTTON_INSET[1]))


def grid_fields(ids) -> list:
    """Each attribute's multiplier, name and value fields, at its grid row."""
    origin, out = dialog_origin(), []
    for attribute in range(ATTRIBUTE_ROWS):
        x, y = grid_row(attribute)
        name_x = x + MULTIPLIER_W
        out += [(field(next(ids), line_in((x, y, MULTIPLIER_W, GRID_ROW_H)),
                       origin), f'Mult{attribute}'),
                (field(next(ids), line_in((name_x, y, NAME_W, GRID_ROW_H)),
                       origin), f'AttrName{attribute}'),
                (field(next(ids), line_in((name_x, y, VALUE_W, GRID_ROW_H)),
                       origin, 'header'), f'AttrValue{attribute}')]
    return out


def dialog_fields() -> list:
    """Every level-up field as `(tag, instance_name)`."""
    origin = dialog_origin()
    ids = iter(range(CHAR_DIALOG_FIELD_FIRST, CHAR_DIALOG_FIELD_FIRST + 100))
    out = [(field(next(ids), line_in(LEVEL_TEXT), origin, align=ALIGN_CENTER),
            'LevelText'),
           (field(next(ids), DESCRIPTION, origin), 'Description'),
           (field(next(ids), ok_caption_rect(), origin, align=ALIGN_CENTER),
            'OkCaption')]
    return out + grid_fields(ids)


def dialog_sprites(export_root) -> list:
    """The gold coins, then every class image, each a sprite of its own."""
    origin, coin = dialog_origin(), load(export_root, 'tx_goldicon', ICONS)
    out = [sprite(CHAR_COIN_FIRST + 3 * i, coin, f'Coin{i}',
                  (COIN_ROW[0], COIN_ROW[1], COIN, COIN), origin)
           for i in range(COINS)]
    for i, name in enumerate(CLASSES):
        image = load(export_root, 'levelup' + chr(92) + name)
        out.append(sprite(CHAR_CLASS_FIRST + 3 * i, image, f'Class_{name}',
                          IMAGE, origin, CLASS_PIXELS))
    return out


def levelup_dialog(export_root) -> Swf:
    """The level-up dialog movie.

    See: docs/plans/character_sheet.md#m2-swf
    """
    tags = chrome_tags(CHAR_DIALOG_BMP, compose_dialog(export_root),
                       dialog_origin())
    tags += place_all(dialog_sprites(export_root), dialog_fields(), 2)
    return movie(tags)


# ---------------------------------------------------------------------------
# The plugin's header and the CLI
# ---------------------------------------------------------------------------

def rect_lines(prefix: str, rect: tuple, origin: tuple) -> list:
    """Four `constexpr int` lines for one window-space rect, on the stage."""
    return [f'constexpr int k{prefix}{axis} = {value};'
            for axis, value in zip('XYWH', on_stage(rect, origin))]


def stats_lines() -> list:
    """The stats window's rects, row counts and pitch."""
    origin = stats_origin()
    lines = rect_lines('Caption', CAPTION, origin)
    for row in range(len(BAR_COLORS)):
        lines += rect_lines(f'BarFill{row}', bar_fill_rect(row), origin)
    lines += rect_lines('SkillView', skill_view(), origin)
    lines += rect_lines('SkillScroll', skill_scroll(), origin)
    return lines + [f'constexpr int kCaptionPad = {CAPTION_PAD};',
                    f'constexpr int kRowH = {ROW_H};',
                    f'constexpr int kBarRows = {len(BAR_COLORS)};',
                    f'constexpr int kInfoRows = {len(INFO_ROWS)};',
                    f'constexpr int kAttributeRows = {ATTRIBUTE_ROWS};',
                    f'constexpr int kSkillFields = {SKILL_FIELDS};']


def dialog_lines() -> list:
    """The level-up dialog's rects, grid and coin geometry, and class names."""
    origin = dialog_origin()
    x, y = grid_row(0)
    lines = rect_lines('Ok', OK_BUTTON, origin)
    lines += rect_lines('CoinRow', COIN_ROW, origin)
    lines += [f'constexpr int kGridX = {x + origin[0]};',
              f'constexpr int kGridY = {y + origin[1]};',
              f'constexpr int kGridColumnStep = {COLUMNS[1] - COLUMNS[0]};',
              f'constexpr int kGridRowH = {GRID_ROW_H};',
              f'constexpr int kGridPerColumn = {PER_COLUMN};',
              f'constexpr int kMultiplierW = {MULTIPLIER_W};',
              f'constexpr int kNameW = {NAME_W};',
              f'constexpr int kCoin = {COIN};',
              f'constexpr int kCoinSpacing = {COIN_SPACING};',
              f'constexpr int kCoins = {COINS};']
    names = ', '.join(f'"{name}"' for name in CLASSES)
    return lines + [f'constexpr const char* kClassImages[] = {{{names}}};',
                    f'constexpr int kClassImageCount = {len(CLASSES)};']


def layout_header() -> str:
    """The plugin's copy of both layouts, generated so nothing can disagree."""
    lines = ['// GENERATED by tools/generators/gen_morrowind_stats_swf.py.',
             '// Edit the generator, not this file.', '', '#pragma once', '',
             'namespace tesruntime::mw::stats_layout {', '']
    lines += stats_lines() + [''] + dialog_lines()
    lines += ['', '}  // namespace tesruntime::mw::stats_layout', '']
    return '\n'.join(lines)


def write_movies(export_root: str, out_dir: str, compress: bool = True) -> list:
    """Both movies into `out_dir`; returns the paths written."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, build in ((STATS_MOVIE, stats_window),
                        (LEVELUP_MOVIE, levelup_dialog)):
        path = os.path.join(out_dir, name)
        with open(path, 'wb') as fh:
            fh.write(build(export_root).serialize(compress=compress))
        written.append(path)
    return written


def write_previews(export_root: str, folder: str) -> None:
    """Both chromes as PNGs, to look at without the game."""
    os.makedirs(folder, exist_ok=True)
    compose_stats(export_root).convert('RGB').save(
        os.path.join(folder, 'stats.png'))
    compose_dialog(export_root).convert('RGB').save(
        os.path.join(folder, 'levelup.png'))


def main() -> None:
    """CLI: write both movies and the plugin's layout header."""
    ap = argparse.ArgumentParser(
        description='Author the Morrowind stats and level-up SWFs.')
    ap.add_argument('--out', default='tes_runtime/morrowind/interface')
    ap.add_argument('--header', default=HEADER_PATH)
    ap.add_argument('--export-root', default='export')
    ap.add_argument('--preview', help='also write both chromes as PNGs here')
    ap.add_argument('--uncompressed', action='store_true')
    args = ap.parse_args()
    for path in write_movies(args.export_root, args.out, not args.uncompressed):
        print(f'wrote {path} ({os.path.getsize(path)} bytes)')
    with open(args.header, 'w', encoding='ascii', newline='\n') as fh:
        fh.write(layout_header())
    print(f'layout -> {args.header}')
    if args.preview:
        write_previews(args.export_root, args.preview)


if __name__ == '__main__':
    main()
