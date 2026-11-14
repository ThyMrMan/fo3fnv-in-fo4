"""Estimated build time, cold and cached, per stage group: a linear model of the build's features (eta_inputs),
fitted on recorded builds of the reference machine (tools/release/fit_build_eta.py writes DATA), scaled to another
machine by its benchmark (tools/release/machine_benchmark.py) and the resource profile's worker count. During a
build, Live prints how much is left, correcting the plan by how the finished groups went. Always an estimate.

    py -3.14 -m fo4_import.pipeline.eta <export folder or <plugin>.build.json>... [--resources low]
        [--benchmark machine_benchmark.json]

See: docs/fork/fo4_build_resources.md#eta
"""

import argparse
import json
import threading
import time
from pathlib import Path

from core import build_resources
from fo4_import.pipeline import eta_inputs
from fo4_import.pipeline.code_tag import ROOT

DATA = ROOT / 'fo4_import' / 'data' / 'build_eta.json'
#: Where machine_benchmark.py writes by default and the build looks for this machine's benchmark.
BENCHMARK = ROOT / 'output' / 'machine_benchmark.json'
#: How each feature's work scales to another machine (the rest is the main process: one core's speed).
KIND = {'faces_cold': 'pool', 'guns_cold': 'pool', 'meshes_cold': 'pool', 'scripts_changed': 'pool',
        'voices_cold': 'pool', 'packed': 'disk'}
#: Seconds between Live's lines.
LIVE_SECONDS = 30
NOTE = 'an estimate, from earlier builds; this run may differ'


def load(path: Path = DATA) -> dict:
    """The fitted model."""
    return json.loads(path.read_text(encoding='utf-8'))


def benchmark(path: Path = BENCHMARK) -> 'dict | None':
    """A machine_benchmark.py result, or None when there is none."""
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
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


class Live:
    """A stage_timer listener printing, every LIVE_SECONDS, the time left of a planned build ({group: seconds}): the
    plan of the groups not done, scaled by how the started ones went against theirs, less the running stage's time
    so far. start() also prints during a long stage."""

    def __init__(self, plan: dict, out=print):
        """Track `plan`, printing with `out`."""
        self.plan, self.out, self.spent, self.order = plan, out, {}, []
        self.started = self.last = self.event = time.time()

    def left(self) -> float:
        """Seconds left: each group's plan times the pace so far, less what it has spent."""
        done = self.order[:-1]
        planned, spent = sum(self.plan.get(g, 0.0) for g in done), sum(self.spent[g] for g in done)
        pace = min(3.0, max(0.5, spent / planned)) if planned > LIVE_SECONDS else 1.0
        return sum(max(0.0, seconds * pace - self.spent.get(group, 0.0)) for group, seconds in self.plan.items())

    def __call__(self, stage: str, seconds: float) -> None:
        """Count `seconds` of `stage`; print the time left when LIVE_SECONDS have passed since the last line."""
        group = eta_inputs.group_of(stage)
        self.spent[group] = self.spent.get(group, 0.0) + seconds
        if group not in self.order:
            self.order.append(group)
        self.event = time.time()
        self.tick()

    def tick(self) -> None:
        """Print the time left (less the time since the last stage ended) if LIVE_SECONDS passed since the last line."""
        now = time.time()
        if now - self.last >= LIVE_SECONDS:
            self.last = now
            left = max(0.0, self.left() - (now - self.event))
            self.out(f'estimate: about {minutes(left)} left, {minutes(now - self.started)} so far ({NOTE})')

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
