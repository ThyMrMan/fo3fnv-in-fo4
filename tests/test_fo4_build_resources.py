"""The build's one resource setting, its memory per stage, and its time estimate.

See: docs/fork/fo4_build_resources.md#profiles
"""

import json
import sys

import pytest

from core import build_resources as R
from core import process_memory
from fo4_import.pipeline import eta, eta_inputs, stage_timer
from tools.release import fit_build_eta, machine_benchmark

GB = R.GB
#: A 16-thread, 32 GB machine with 24 GB free and a 2 GB main process.
ROOMY = R.Machine(16, 32 * GB, 24 * GB, 2 * GB)


def test_each_profile_keeps_its_share_of_the_cores():
    """Full is every core but one, balanced three quarters, low half."""
    counts = {name: R.plan_workers(0, 100, ROOMY, name) for name in R.PROFILES}
    assert counts == {'full': 15, 'balanced': 12, 'low': 8}


def test_memory_and_jobs_bound_the_workers():
    """Fewer jobs, a profile's memory share, a job cap and an explicit count each bound the plan; at least one."""
    assert R.plan_workers(GB, 3, ROOMY, 'full') == 3
    assert R.plan_workers(GB, 100, R.Machine(16, 16 * GB, 12 * GB, 7 * GB), 'low') == 1
    assert R.plan_workers(GB, 100, R.Machine(16, 32 * GB, 24 * GB, 2 * GB, job_cap=6 * GB), 'full') == 4
    assert R.plan_workers(GB, 100, R.Machine(16, 32 * GB, 1 * GB, 2 * GB), 'full') == 1
    assert R.plan_workers(GB, 100, ROOMY, 'low', asked=11) == 11
    assert R.plan_workers(GB, 100, R.Machine(16), 'balanced') == 12


def test_the_profile_comes_from_the_environment(monkeypatch):
    """TESCONV_RESOURCES names it, any case; an unknown name falls back to the default."""
    monkeypatch.setenv(R.ENV_VAR, 'LOW')
    assert R.profile_name() == 'low'
    monkeypatch.setenv(R.ENV_VAR, 'turbo')
    assert R.profile_name() == R.DEFAULT


@pytest.mark.skipif(sys.platform != 'win32', reason='memory is read through kernel32')
def test_this_process_commit_is_read_and_no_job_lists_nothing(monkeypatch):
    """Own commit is read; with no job named, no other process is listed."""
    monkeypatch.delenv(process_memory.JOB_ENV_VAR, raising=False)
    assert process_memory.own_commit() > 1 << 20
    assert process_memory.job_commits() == []


def test_memory_readings_go_to_the_innermost_stage(monkeypatch):
    """A reading inside a nested stage is that stage's; report and records carry the peaks."""
    monkeypatch.setattr(stage_timer, '_spent', {})
    monkeypatch.setattr(stage_timer, '_peaks', {})

    @stage_timer.timed('test outer')
    def outer():
        """Read once here, then inside the inner stage."""
        stage_timer.note(3 * GB, [])
        stage_timer.charged('test inner', stage_timer.note, 5 * GB, [GB, 2 * GB])

    outer()
    rows = stage_timer.records()
    assert rows['test outer']['peak_main_gb'] == 3.0 and rows['test outer']['workers'] == 0
    assert rows['test inner'] == {'seconds': rows['test inner']['seconds'], 'peak_main_gb': 5.0,
                                  'peak_workers_gb': 3.0, 'largest_worker_gb': 2.0, 'workers': 2}
    assert stage_timer.report()[-1].endswith('peak 5.00 GB main, 3.00 GB in 2 workers')


LOG = """scripts converted in 5.0s
mesh cache: 500 meshes ready in 25.0s
3 of 10 scripts changed or use one whose declarations did
NPC_: 40
guns on FNV clips: 7
stage script conversion: 5.0s
stage people: 12.5s
stage item WEAP: 4.0s
stage own-rig animation data: 9.0s
stage total: 30.5s
built in 60.0s
"""


def test_a_build_log_gives_stage_times_counts_and_the_mesh_cache(tmp_path):
    """Stages, counts and the log-only facts are read; the mesh cache's time is its line less script conversion."""
    path = tmp_path / '00 Test.esm build.log'
    path.write_text(LOG, encoding='utf-8')
    stages, counts = eta_inputs.log_build(path)
    assert stages['mesh cache'] == 20.0 and counts['scripts changed'] == 3.0 and counts['NPC_'] == 40
    groups = eta_inputs.grouped(stages)
    assert groups == {'scripts': 5.0, 'people': 12.5, 'weapons': 4.0, 'animation': 9.0, 'mesh cache': 20.0}
    feats = eta_inputs.features(counts, True)
    assert feats['npcs'] == 40 and feats['compiles'] == 1.0 and feats['compile_size'] == 0.5


def test_a_finished_stamp_is_read_and_a_running_one_is_not(tmp_path):
    """record_build reads a finished stamp's stage seconds (not its memory-only rows) and counts."""
    stamp = tmp_path / 'Test.esm.build.json'
    body = {'status': 'finished', 'stages': {'people': {'seconds': 3.0}, 'outside stages': {'peak_main_gb': 1.0}},
            'counts': {'NPC_': 4}}
    stamp.write_text(json.dumps(body), encoding='utf-8')
    assert eta_inputs.record_build(stamp) == ({'people': 3.0}, {'NPC_': 4})
    stamp.write_text(json.dumps({**body, 'status': 'running'}), encoding='utf-8')
    assert eta_inputs.record_build(stamp) is None


def test_an_export_takes_the_typical_region_only_when_it_edits_cells():
    """A plugin with masters and cells gets the model's region added; one without cells only its own records."""
    model = {'ratios': {'npcs': 1.0, 'meshes': 1.0, 'packed': 2.0}, 'region': {'npcs': 100.0, 'meshes': 50.0}}
    alone = eta_inputs.export_features({'NPC_': 5.0, 'CREA': 1.0, 'meshes': 10.0}, True, model)
    region = eta_inputs.export_features({'NPC_': 5.0, 'CELL': 3.0, 'meshes': 10.0}, True, model)
    assert alone['npcs'] == 6.0 and region['npcs'] == 105.0 and region['packed'] == 120.0
    assert region['faces_cold'] == region['npcs']


MODEL = {'groups': {'people': {'npcs': 1.0, 'faces_cold': 2.0}, 'archives': {'packed': 1.0}},
         'cold_ratios': {}, 'main_gb': 2.0,
         'reference': {'logical_cores': 16, 'memory': {'total_gb': 32.0}, 'single': {'python_units_s': 30.0},
                       'disk': {'write_mb_s': 100.0}, 'workers': {'units_per_second': {'1': 30.0, '15': 240.0}}}}


def test_cold_costs_more_than_cached_and_a_slower_machine_scales_each_kind():
    """Cold adds the face fits; half the single-core speed doubles the main process's part, half the disk speed
    doubles the archive, and the pool's part follows the throughput of the workers the profile allows."""
    feats = {'npcs': 10.0, 'packed': 5.0}
    assert eta.predict(MODEL, feats, False) == {'people': 10.0, 'archives': 5.0}
    assert eta.predict(MODEL, feats, True) == {'people': 30.0, 'archives': 5.0}
    slow = {'logical_cores': 4, 'memory': {'total_gb': 32.0}, 'single': {'python_units_s': 15.0},
            'disk': {'write_mb_s': 50.0}, 'workers': {'units_per_second': {'1': 15.0, '3': 30.0}}}
    assert eta.predict(MODEL, feats, True, slow, 'full') == {'people': 20.0 + 20.0 * 240.0 / 30.0, 'archives': 10.0}


def test_throughput_is_read_off_the_measured_worker_counts():
    """Straight lines between measured counts, flat past the largest."""
    bench = {'workers': {'units_per_second': {'1': 10.0, '5': 50.0, '9': 60.0}}}
    assert [eta.throughput(bench, n) for n in (1, 3, 7, 20)] == [10.0, 30.0, 55.0, 60.0]


def test_live_prints_the_time_left_scaled_by_the_pace_of_the_finished_groups(monkeypatch):
    """The finished group ran twice its plan, so the rest is planned at twice too."""
    lines = []
    live = eta.Live({'people': 100.0, 'weapons': 100.0}, lines.append)
    monkeypatch.setattr(eta, 'LIVE_SECONDS', 0)
    live('people', 200.0)
    live('item WEAP', 50.0)
    assert live.left() == 150.0
    assert lines[-1].startswith('estimate: about 2 min left')


def test_the_fit_recovers_known_coefficients():
    """NNLS on builds made from known per-feature costs gives them back."""
    data = [{'features': {'one': 1.0, 'npcs': n}, 'groups': {'people': 5.0 + 0.5 * n}} for n in (10, 100, 1000)]
    found = fit_build_eta.fit_group('people', data)
    assert found['one'] == pytest.approx(5.0) and found['npcs'] == pytest.approx(0.5)


def test_the_shipped_model_estimates_every_group_from_an_export_shaped_input():
    """The model file in the repo loads and gives a positive cached and a larger cold time."""
    model = eta.load()
    own = {'NPC_': 2000.0, 'WEAP': 200.0, 'STAT': 5000.0, 'CELL': 30000.0, 'INFO': 30000.0, 'meshes': 8000.0}
    feats = eta_inputs.export_features(own, False, model)
    cached, cold = (sum(eta.predict(model, feats, c).values()) for c in (False, True))
    assert 0 < cached < cold


def test_the_benchmark_disk_and_units_run(tmp_path, monkeypatch):
    """A Python unit gives a number; the disk test reports its three speeds on small sizes."""
    monkeypatch.setattr(machine_benchmark, 'BIG_BYTES', 32 << 20)
    monkeypatch.setattr(machine_benchmark, 'SMALL_FILES', 20)
    assert machine_benchmark.python_unit() > 0
    found = machine_benchmark.disk(tmp_path)
    assert found['write_mb_s'] > 0 and found['read_mb_s'] > 0 and found['small_files_s'] > 0
