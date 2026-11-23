"""This project's release identity (fo4_import.base.release): its own f3nv- tags, read from VERSION or git.

See: docs/fork/fo4_plan_release.md#release-identity
"""

import version
from fo4_import.base import release as R


def test_only_our_tags_have_a_key_and_a_describe_suffix_ranks_as_its_tag():
    """f3nv-0.12 follows f3nv-0.2; the Skyrim fork's tags have no key."""
    assert R.key('f3nv-0.2') == (0, 2) and R.key('f3nv-0.12-4-gabc1234') == (0, 12)
    assert R.key('f3nv-0.12') > R.key('f3nv-0.2')
    assert R.key('0.689') is None and R.key('$Format:%(describe:tags)$') is None and R.key(R.DEV) is None


def test_a_release_download_reads_version_and_a_checkout_asks_git(tmp_path, monkeypatch):
    """VERSION holding a tag wins; holding git's placeholder, the describe answer is used, else DEV."""
    monkeypatch.setattr(R, 'ROOT', tmp_path)
    monkeypatch.setattr(R, '_from_git', lambda: 'f3nv-0.1-3-gabc1234')
    (tmp_path / 'VERSION').write_text('f3nv-0.2\n', encoding='utf-8')
    R.current.cache_clear()
    assert R.current() == 'f3nv-0.2'
    (tmp_path / 'VERSION').write_text('$Format:%(describe:tags)$', encoding='utf-8')
    R.current.cache_clear()
    assert R.current() == 'f3nv-0.1-3-gabc1234' and R.older('f3nv-0.0') and not R.older('f3nv-0.1')
    monkeypatch.setattr(R, '_from_git', lambda: '')
    R.current.cache_clear()
    assert R.current() == R.DEV and not R.older('f3nv-0.1')
    R.current.cache_clear()


def test_the_inherited_version_reads_our_release_too(tmp_path, monkeypatch):
    """version.current_version (run logs, step stamps) gives a release download's f3nv tag, not 0.0-dev."""
    monkeypatch.setattr(R, 'ROOT', tmp_path)
    monkeypatch.setattr(version, 'VERSION_FILE', tmp_path / 'VERSION')
    monkeypatch.setattr(version, '_git_version', lambda: None)
    monkeypatch.setattr(version, '_CURRENT', [None])
    (tmp_path / 'VERSION').write_text('f3nv-0.3\n', encoding='utf-8')
    assert version.current_version() == 'f3nv-0.3'
