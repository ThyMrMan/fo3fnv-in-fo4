"""The Fallout 3 recorder's parts that need no game."""
import re

from tools.live import fo3_record as R

TIMELINE = '\n'.join([
    '0|start|runtime 01070030|fose 01030020',
    '10|fault|no eval for IsTalking',
    '500|cell|0001A2B3',
    '510|actor|00000014|00000007',
    '520|stage|CG00|00012345|0',
    '900|stage|CG00|00012345|5',
    '950|pos|00000014|1|2|3|90',
]) + '\n'


def test_follow_stops_at_the_until_line(tmp_path, capsys):
    """Following reads every whole line and stops once one matches `--until`."""
    out = tmp_path / 'f3_timeline.log'
    out.write_text(TIMELINE + '960|partial', encoding='utf-8')
    lines, matched = R.follow(out, 5, re.compile(r'\|stage\|CG00\|[^|]*\|5$'))
    assert matched and len(lines) == 7 and '960|partial' not in capsys.readouterr().out


def test_launcher_prefers_an_exe_that_loads_fose(tmp_path):
    """An exe naming fose_1_7.dll starts directly; a plain one goes through fose_loader."""
    exe = tmp_path / 'Fallout3.exe'
    exe.write_bytes(b'MZ...fose_1_7.dll\0...')
    assert R.launcher(tmp_path) == exe
    exe.write_bytes(b'MZ...xlive.dll\0...')
    assert R.launcher(tmp_path) == tmp_path / 'fose_loader.exe'


def test_summary_counts_kinds_and_lists_faults():
    """The summary counts each kind of line and repeats every fault."""
    text = R.summary(TIMELINE.splitlines())
    assert "'stage': 2" in text and "'fault': 1" in text
    assert '10|fault|no eval for IsTalking' in text
