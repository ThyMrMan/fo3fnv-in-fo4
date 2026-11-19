"""Fallout 4 say bookkeeping: a converted block holds the says count for each ask's speaker (say_to_done.held_says)."""
from script_convert.say_to_done import held_says
from script_convert.target import FALLOUT4, TARGET_ENV


def test_each_ask_holds_for_its_own_speaker(monkeypatch):
    """HoldSays names the speaker of the SayWhenFree after it, a cast with commas inside included."""
    monkeypatch.setenv(TARGET_ENV, FALLOUT4)
    lines = ['Event OnTimer(Int aiTimerID)',
             '  TES4Polyfill.SayWhenFree(DocMitchellREF, VCG01Intro, Player)',
             '  If Busy',
             '    Return',
             '  EndIf',
             '  TES4Polyfill.SayWhenFree(Pick(a, b) as ObjectReference, Topic01, None)',
             'EndEvent']
    out = held_says(lines)
    assert out[1:4] == ['  Bool TES4_SaysHeld = False',
                        '  TES4_SaysHeld = TES4Polyfill.HoldSays(TES4_SaysHeld, DocMitchellREF)',
                        '  TES4Polyfill.SayWhenFree(DocMitchellREF, VCG01Intro, Player)']
    assert '    TES4Polyfill.ReleaseSays(TES4_SaysHeld)' in out
    assert '  TES4_SaysHeld = TES4Polyfill.HoldSays(TES4_SaysHeld, Pick(a, b) as ObjectReference)' in out
    assert out[-2:] == ['  TES4Polyfill.ReleaseSays(TES4_SaysHeld)', 'EndEvent']
