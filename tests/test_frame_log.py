"""Tests for tools/validate/frame_log.py on a small fixture log in Afterburner's .hml layout."""
from tools.validate import frame_log as FL

HEADER = [
    '00, 11-10-2026 22:59:18, Hardware monitoring log v1.6 ',
    '01, 11-10-2026 22:59:18, AMD Radeon(TM) Graphics,NVIDIA GeForce RTX 5070 Ti',
    '02, 11-10-2026 22:59:18, GPU1 usage          ,GPU2 usage          ,GPU2 memory usage   ,Framerate           ,'
    'Frametime           ,Framerate 1% Low    ',
    '03, 11-10-2026 22:59:18, 0                   ,%                   ,0.000               ,100.000             ,10',
]


def _row(clock: str, gpu: float, rate, frame_ms) -> str:
    """One `80` data row at `clock`; None logs as N/A."""
    cells = [0.0, gpu, 4000.0, rate, frame_ms, None]
    text = ','.join('N/A' if v is None else f'{v:.3f}' for v in cells)
    return f'80, 11-10-2026 {clock}, {text}'


def _log() -> list:
    """Two routes in one session (a 30 s pause between), then a second session; idle rows before each."""
    rows = HEADER + [_row('23:00:00', 1, None, None)]
    rows += [_row(f'23:01:{s:02d}', 25, 118.0, 8.5) for s in range(10)]
    rows += [_row('23:01:10', 30, 20.0, 370.0)]
    rows += [_row(f'23:02:{s:02d}', 60, 90.0, 11.1) for s in range(20)]
    rows += HEADER + [_row(f'23:10:{s:02d}', 70, 60.0, 16.7) for s in range(5)]
    return rows


def test_split_by_pause_and_session():
    """A long pause or a new session starts a segment; idle rows drop."""
    segments = FL.split(FL.read_hml(_log()), gap=10, names=['Freeside', 'Strip'])
    assert [(s.name, len(s.samples)) for s in segments] == [('Freeside', 11), ('Strip', 20), ('run 3', 5)]


def test_summary_numbers():
    """Average, 1% low, share at the cap, median frame time, busiest GPU and spikes of one segment."""
    first = FL.split(FL.read_hml(_log()), gap=10, names=[])[0]
    row = FL.summary(first, cap=118, spike_ms=100)
    assert round(row['avg'], 2) == round((118 * 10 + 20) / 11, 2)
    assert row['low'] == 20.0
    assert round(row['at_cap'], 3) == round(10 / 11, 3)
    assert row['median_ms'] == 8.5
    assert row['gpu'] == ('GPU2 usage', 25.0)
    assert row['spikes'] == [('23:01:10', 370.0)]


def test_windows_and_cap():
    """Named time windows replace the split; the cap defaults to the most common frame rate."""
    samples = FL.read_hml(_log())
    (strip,) = FL.windows(samples, ['Strip=23:02:00-23:02:59'])
    assert len(strip.samples) == 20
    assert FL.cap_of(FL.drawing(samples)) == 90


def test_one_percent_low_nearest_rank():
    """Under 100 polls the 1% low is the minimum; at 200 it is the second slowest."""
    assert FL.one_percent_low([5, 1, 9]) == 1
    assert FL.one_percent_low(list(range(200, 0, -1))) == 2


def test_main_prints_table(tmp_path, capsys):
    """The command line reads a file and prints one row per segment."""
    log = tmp_path / 'run.hml'
    log.write_text('\n'.join(_log()), encoding='utf-8')
    assert FL.main([str(log), '--names', 'Freeside', 'Strip', 'Novac']) == 0
    out = capsys.readouterr().out
    assert 'Novac' in out and 'Freeside: 23:01:10 370 ms' in out
