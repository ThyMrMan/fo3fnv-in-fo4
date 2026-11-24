"""Estimated build time, cold and cached, per stage group: a linear model of the build's features (eta_inputs),
fitted on recorded builds of the reference machine (tools/release/fit_build_eta.py writes DATA), scaled to another
machine by its benchmark (tools/release/machine_benchmark.py) and the resource profile's worker count. During a
build, Live prints how much is left, correcting the plan by how the groups went so far and the running stage by
its own progress (stage_timer.counted). Always an estimate.

    py -3.14 -m fo4_import.pipeline.eta <export folder or <plugin>.build.json>... [--resources low]
        [--benchmark machine_benchmark.json]

See: docs/fork/fo4_build_resources.md#eta
"""

import argparse
import dataclasses
import json
import threading
import time
from pathlib import Path

from core import build_resources
from fo4_import.pipeline import eta_inputs, stage_timer
from fo4_import.pipeline.code_tag import ROOT
from asset_convert import paths as data_paths

DATA = ROOT / 'fo4_import' / 'data' / 'build_eta.json'
#: Where machine_benchmark.py writes by default and the build looks for this machine's benchmark.
BENCHMARK = data_paths.OUTPUT / 'machine_benchmark.json'
#: How each feature's work scales to another machine (the rest is the main process: one core's speed).
KIND = {'faces_cold': 'pool', 'guns_cold': 'pool', 'meshes_cold': 'pool', 'scripts_changed': 'pool',
        'voices_cold': 'pool', 'packed': 'disk'}
#: Seconds between Live's checks (each a progress line for the app's window).
LIVE_SECONDS = 10
NOTE = 'an estimate, from earlier builds; this run may differ'
#: Live writes the time left again once the expected finish moves this many seconds and this share of the time left.
MOVED_SECONDS, MOVED_SHARE = 120.0, 0.15
#: The bounds of a build's pace against its plan, and the planned seconds before a pace counts.
PACE, PACE_PLANNED = (0.5, 3.0), 60.0
#: The share of a stage's counted loop done before its rate counts.
TRUSTED_SHARE = 0.05
#: Environment variable the app sets so a build prints a PROGRESS line each check, for its window only.
PROGRESS_ENV = 'F3NV_PROGRESS_LINES'
PROGRESS = 'progress: '


def load(path: Path = DATA) -> dict:
    """The fitted model."""
    return json.loads(path.read_text(encoding='utf-8'))


def benchmark_path() -> Path:
    """This machine's benchmark file, in the work folder's output."""
    return data_paths.data_root() / 'output' / BENCHMARK.name


def benchmark(path: 'Path | None' = None) -> 'dict | None':
    """A machine_benchmark.py result (default: benchmark_path()), or None when there is none."""
    try:
        return json.loads(Path(path or benchmark_path()).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def throughput(bench: dict, workers: int) -> float:
    """Python work units a second `workers` processes run together on the benchmarked machine, read off its
    measured counts (straight lines between them, flat past the largest)."""
    table = sorted((int(n), rate) for n, rate in bench['workers']['units_per_second'].items())
    below = [(n, rate) for n, rate in table if n <= workers] or table[:1]
    above = [(n, rate) for n, rate in table if n > workers]
    (n0, r0), (n1, r1) = below[-1], (above[0] if above else below[-1])
    return r0 if n1 == n0 else r0 + (r1 - r0) * (workers - n0) / (n1 - n0)


def pool_size(bench: dict, profile: str, main_gb: float) -> int:
    """Workers of 1 GB a pool starts on the benchmarked machine under `profile`, the main process at `main_gb`."""
    total = int(bench['memory']['total_gb'] * build_resources.GB)
    main = int(main_gb * build_resources.GB)
    box = build_resources.Machine(bench['logical_cores'], total, max(0, total - main), main)
    return build_resources.plan_workers(build_resources.GB, 1 << 16, box, profile)


def speeds(bench: dict, profile: str, main_gb: float) -> dict:
    """{kind: speed} of a machine: one core, its pool under `profile`, disk."""
    return {'serial': bench['single']['python_units_s'], 'disk': bench['disk']['write_mb_s'],
            'pool': throughput(bench, pool_size(bench, profile, main_gb))}


def scales(model: dict, bench: 'dict | None', profile: str) -> dict:
    """{kind: time on the benchmarked machine over time on the reference machine} (1 without a benchmark)."""
    if bench is None:
        return {'serial': 1.0, 'disk': 1.0, 'pool': 1.0}
    ref, here = (speeds(b, p, model['main_gb']) for b, p in ((model['reference'], 'full'), (bench, profile)))
    return {kind: ref[kind] / here[kind] for kind in ref}


def with_caches(feats: dict, cold: 'bool | None', model: dict) -> dict:
    """`feats` for a cold build (each cold feature its warm bound times the model's ratio), a cached one (no cold
    work, a script compile still run), or as they are (None)."""
    out = dict(feats)
    if cold is None:
        return out
    for name, warm in eta_inputs.COLD.items():
        out[name] = max(out.get(name, 0.0), out.get(warm, 0.0) * model['cold_ratios'].get(name, 1.0)) if cold else 0.0
    out['compiles'] = 1.0
    return eta_inputs.sized(out)


def predict(model: dict, feats: dict, cold: 'bool | None', bench: 'dict | None' = None, profile: str = 'full') -> dict:
    """{group: seconds} for `feats` made `cold` (with_caches), on `bench`."""
    return grouped_seconds(model['groups'], with_caches(feats, cold, model), scales(model, bench, profile))


def grouped_seconds(groups: dict, feats: dict, scale: dict) -> dict:
    """{group: seconds} of coefficients `groups` on `feats`, scaled by KIND."""
    return {group: sum(coef * feats.get(name, 0.0) * scale[KIND.get(name, 'serial')] for name, coef in coefs.items())
            for group, coefs in groups.items()}


def target_features(target: Path, model: dict) -> 'tuple | None':
    """(features, from a finished build) of `target`: a `.build.json` stamp's counts, else an export folder's;
    None when it is neither."""
    if target.suffix == '.json':
        found = eta_inputs.record_build(target)
        return (eta_inputs.features(found[1], found[1].get(eta_inputs.MASTERS_COUNT, 1)), True) if found else None
    if not target.is_dir():
        return None
    own = eta_inputs.export_counts(target, model['per_record'])
    return eta_inputs.export_features(own, eta_inputs.has_masters(target), model), False


def planned(stamp: Path, profile: str = 'full') -> 'dict | None':
    """{group: seconds} a rebuild of the plugin whose finished `.build.json` is `stamp` should take on this machine
    (its counts, as cached as they were); None without a finished build."""
    model = load()
    found = target_features(Path(stamp), model)
    return predict(model, found[0], None, benchmark(), profile) if found else None


def overran(plan: dict, stages: dict, top: int = 2) -> list:
    """The stages (of {stage: seconds}) of the `top` groups that ran furthest past their `plan` ({group: seconds}),
    each group's slowest stage: what to profile next (F3NV_PROFILE_STAGES)."""
    spent = eta_inputs.grouped(stages)
    over = sorted(spent, key=lambda g: plan.get(g, 0.0) - spent[g])[:top]
    return [max((s for s in stages if eta_inputs.group_of(s) == g), key=stages.get) for g in over
            if spent[g] > plan.get(g, 0.0)]


def minutes(seconds: float) -> str:
    """'N min', at least 1."""
    return f'{max(1, round(seconds / 60))} min'


def summary(model: dict, feats: dict, bench: 'dict | None', profile: str) -> str:
    """'about <cached> cached, <cold> cold' for a build with `feats`."""
    cached, cold = (sum(predict(model, feats, c, bench, profile).values()) for c in (False, True))
    return f'about {minutes(cached)} cached, {minutes(cold)} cold'


def pace(spent: float, planned: float) -> float:
    """`spent` over `planned` seconds within PACE; 1 below PACE_PLANNED planned."""
    return min(PACE[1], max(PACE[0], spent / planned)) if planned > PACE_PLANNED else 1.0


def step_left(progress, now: float) -> 'float | None':
    """Seconds left of a Progress at its rate; None under TRUSTED_SHARE done."""
    if progress is None or progress.done < max(1.0, progress.total * TRUSTED_SHARE):
        return None
    return (now - progress.began) * (progress.total - progress.done) / progress.done


def blended(plan_left: float, step: 'float | None', share: float) -> float:
    """Plan's time left moved toward `step` by `share`, never under `step`."""
    if step is None:
        return max(0.0, plan_left)
    return max(step, (1.0 - share) * max(0.0, plan_left) + share * step)


@dataclasses.dataclass
class Left:
    """Seconds left of the build and of the running stage's group (`step`), and that stage's name and Progress."""
    build: float
    step: float = 0.0
    stage: 'str | None' = None
    progress: 'stage_timer.Progress | None' = None

    def text(self) -> str:
        """'<Stage>: <done> of <total> <unit>, about N min left in this step, about M min overall'."""
        overall = f'about {minutes(self.build)} overall'
        if self.stage is None:
            return overall
        head = self.stage[:1].upper() + self.stage[1:]
        if self.progress is None:
            return f'{head}, {overall}'
        p = self.progress
        return f'{head}: {p.done:,} of {p.total:,} {p.unit}, about {minutes(self.step)} left in this step, {overall}'


class Live:
    """A stage_timer listener checking, every LIVE_SECONDS, the time left of a planned build ({group: seconds}):
    every group's plan scaled by the pace so far (the running group's time counted as it runs), the running group's
    left from its stage's progress as that grows (blended). It writes an 'estimate:' line when the expected finish
    moves (MOVED_SECONDS, MOVED_SHARE), and with `window` a PROGRESS line each check.
    See: docs/fork/fo4_build_resources.md#live-progress
    """

    def __init__(self, plan: dict, out=print, window: bool = False):
        """Track `plan`, printing with `out` (PROGRESS lines too when `window`)."""
        self.plan, self.out, self.window, self.spent = plan, out, window, {}
        self.started = self.event = time.time()
        self.finish = None

    def left(self, now: 'float | None' = None) -> Left:
        """The time left at `now` (default: now)."""
        now = time.time() if now is None else now
        stage, progress = stage_timer.running() or (None, None)
        group, spent = (eta_inputs.group_of(stage) if stage else None), dict(self.spent)
        if group is not None:
            spent[group] = spent.get(group, 0.0) + now - self.event
        done = [g for g in spent if g != group]
        first = pace(sum(spent[g] for g in done), sum(self.plan.get(g, 0.0) for g in done))
        share = progress.done / progress.total if progress else 0.0
        step = 0.0 if group is None else blended(self.plan.get(group, 0.0) * first - spent[group],
                                                 step_left(progress, now), share)
        overall = pace(sum(spent.values()) + step, sum(self.plan.get(g, 0.0) for g in [*done, group] if g))
        rest = sum(max(0.0, seconds * overall - spent.get(g, 0.0)) for g, seconds in self.plan.items() if g != group)
        return Left(rest + step, step, stage, progress)

    def __call__(self, stage: str, seconds: float) -> None:
        """Count `seconds` of `stage`."""
        group = eta_inputs.group_of(stage)
        self.spent[group] = self.spent.get(group, 0.0) + seconds
        self.event = time.time()

    def tick(self, now: 'float | None' = None) -> None:
        """Print a PROGRESS line (with `window`), and the time left when the expected finish moved."""
        now = time.time() if now is None else now
        left = self.left(now)
        if self.window:
            self.out(PROGRESS + left.text())
        if self.finish is None or abs(now + left.build - self.finish) >= max(MOVED_SECONDS, MOVED_SHARE * left.build):
            self.finish = now + left.build
            self.out(f'estimate: about {minutes(left.build)} left, {minutes(now - self.started)} so far ({NOTE})')

    def start(self) -> 'Live':
        """Tick every LIVE_SECONDS on a daemon thread for the life of the process; this listener."""
        def loop():
            """Tick forever."""
            while True:
                time.sleep(LIVE_SECONDS)
                self.tick()
        threading.Thread(target=loop, name='estimate', daemon=True).start()
        return self


def main() -> None:
    """The command line (the module notes): each target's estimate, then the total."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('targets', nargs='+', type=Path, help='Export folders, or finished builds\' .build.json stamps')
    ap.add_argument('--resources', choices=sorted(build_resources.PROFILES), default=build_resources.profile_name())
    ap.add_argument('--benchmark', type=Path, default=BENCHMARK, help='This machine\'s machine_benchmark.py result')
    args = ap.parse_args()
    model, bench = load(), benchmark(args.benchmark)
    print(f'machine: {"benchmarked" if bench else "not benchmarked, the reference machine assumed"}; '
          f'resources: {args.resources}')
    totals = {False: 0.0, True: 0.0}
    for target in args.targets:
        found = target_features(target, model)
        if found is None:
            print(f'{target}: neither an export folder nor a finished build record')
            continue
        for cold in totals:
            totals[cold] += sum(predict(model, found[0], cold, bench, args.resources).values())
        source = 'its last build' if found[1] else 'its export'
        print(f'{target.name}: {summary(model, found[0], bench, args.resources)} (from {source})')
    print(f'total: about {minutes(totals[False])} cached, {minutes(totals[True])} cold ({NOTE})')


if __name__ == '__main__':
    main()
