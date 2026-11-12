"""Fit the build time estimate (fo4_import.pipeline.eta) on recorded builds of the reference machine and write it,
with its error on those builds.

    py -3.14 -m tools.release.fit_build_eta <log folders and .build.json stamps>... --benchmark <reference result>

A log folder holds `<n> <plugin> build.log` files (an overnight queue's); a stamp is a finished build's record.
Each group's coefficients are non-negative least squares over its features; FIXED ones (measured outside these
builds) are taken as given. The error is each build's total (animation left out: see FIXED) against the model's,
in sample, leaving that build out of the fit, and from its export alone.

See: docs/fork/fo4_build_resources.md#fit
"""

import argparse
import json
import statistics
from pathlib import Path

import numpy
from scipy.optimize import nnls

from fo4_import.pipeline import eta, eta_inputs
from fo4_import.pipeline.code_tag import ROOT

#: Features each group's time is fitted on.
FEATURES = {'mesh cache': ('one', 'meshes'), 'scripts': ('one', 'scripts', 'compiles', 'compile_size'),
            'people': ('one', 'npcs'), 'weapons': ('one', 'guns', 'guns_cold'), 'statics': ('statics',),
            'worlds': ('land', 'cells'), 'collision': ('meshes',), 'voice': ('info', 'voices_cold'),
            'archives': ('packed',), 'ledger': ('masters', 'meshes'),
            'records': ('one', 'masters', 'npcs', 'info', 'statics', 'cells', 'meshes')}
#: A build's weight in the fit is one over the root of its seconds (at least this): small builds count too.
LEAST_SECONDS = 60.0
#: Coefficients measured outside these builds (docs/fork/fo4_build_resources.md#fit), not fitted.
FIXED = {'mesh cache': {'meshes_cold': 0.072}, 'people': {'faces_cold': 0.12},
         'animation': {'one': 10.0, 'guns': 0.4, 'guns_cold': 1.5}}
#: Count names whose ratio to a warm count bounds a cold feature: {cold feature: (cold count, warm count)}.
COLD_RATIO = {'faces_cold': ('face fitted', 'NPC_'), 'voices_cold': ('voice files written', 'INFO')}
#: A masterless build with fewer exterior cells than this was a test block, not the whole game.
WHOLE_CELLS = 1000


def find_export(root: Path, plugin: str) -> 'Path | None':
    """`plugin`'s export folder under `root`: its name, or `_source` holds it."""
    if (root / plugin / '_HEADER.txt').is_file():
        return root / plugin
    return next((d for d in sorted(root.iterdir()) if (d / '_source' / plugin).is_file()), None)


def builds(sources: list) -> list:
    """[(plugin, {stage: seconds}, counts)] of every finished build in `sources` (log folders and stamps)."""
    out = []
    for source in sources:
        if source.is_dir():
            for log in sorted(source.glob('* build.log')):
                found = eta_inputs.log_build(log)
                out += [(log.name.split(' ', 1)[1][:-len(' build.log')], *found)] if found else []
        elif (found := eta_inputs.record_build(source)) is not None:
            out.append((source.name.removesuffix('.build.json'), *found))
    return out


def rows(found: list, root: Path) -> list:
    """Each build as {plugin, export, features, groups (seconds)}."""
    out = []
    for plugin, stages, counts in found:
        export = find_export(root, plugin)
        masters = eta_inputs.has_masters(export) if export else True
        out.append({'plugin': plugin, 'export': export, 'counts': counts,
                    'features': eta_inputs.features(counts, masters), 'groups': eta_inputs.grouped(stages)})
    return out


def fit_group(group: str, data: list) -> dict:
    """{feature: coefficient} of `group` over `data` rows: FIXED, plus non-negative least squares on the rest."""
    fixed, names = FIXED.get(group, {}), FEATURES.get(group, ())
    if not names or not data:
        return dict(fixed)
    weight = numpy.array([max(LEAST_SECONDS, _total(r['groups'])) ** -0.5 for r in data])
    a = numpy.array([[r['features'].get(n, 0.0) for n in names] for r in data]) * weight[:, None]
    b = numpy.array([r['groups'].get(group, 0.0) - sum(c * r['features'].get(n, 0.0) for n, c in fixed.items())
                     for r in data]) * weight
    coefs, _ = nnls(a, numpy.maximum(b, 0.0))
    return {**fixed, **{n: round(float(c), 6) for n, c in zip(names, coefs) if c > 0}}


def fit(data: list) -> dict:
    """{group: {feature: coefficient}} over `data`."""
    return {group: fit_group(group, data) for group in sorted({*FEATURES, *FIXED})}


def per_record(exports: list) -> dict:
    """{record type: median bytes a record} over the export folders `exports`, for the types EXPORT_TYPES reads."""
    kinds = sorted({k for kinds in eta_inputs.EXPORT_TYPES.values() for k in kinds})
    sizes = {k: [] for k in kinds}
    for export in exports:
        for kind in kinds:
            path = export / f'{kind}.txt'
            count = path.read_bytes().count(eta_inputs.RECORD_BEGIN) if path.is_file() else 0
            sizes[kind] += [path.stat().st_size / count] if count else []
    return {k: round(statistics.median(v), 1) for k, v in sizes.items() if v}


def export_model(data: list, model: dict) -> None:
    """Fill `model`'s ratios (a whole masterless build's feature over its export's records) and region (the median
    of what a build with masters takes beyond its own records)."""
    own = {id(r): eta_inputs.export_counts(r['export'], model['per_record']) for r in data if r['export']}
    whole = [r for r in data if id(r) in own and not r['features']['masters'] and r['features']['cells'] >= WHOLE_CELLS]
    ratios = {}
    for name, kinds in [*eta_inputs.EXPORT_TYPES.items(), ('meshes', ('meshes',))]:
        pairs = [(r['features'][name], sum(own[id(r)].get(k, 0.0) for k in kinds)) for r in whole]
        ratios[name] = round(sum(f for f, _ in pairs) / max(1.0, sum(o for _, o in pairs)), 4)
    ratios['packed'] = round(statistics.median(r['features']['packed'] / r['features']['meshes'] for r in data
                                               if r['features']['meshes']), 3)
    model['ratios'] = ratios
    region = {}
    for name in ratios:
        if name in eta_inputs.EXPORT_TYPES or name == 'meshes':
            kinds = eta_inputs.EXPORT_TYPES.get(name, ('meshes',))
            region[name] = round(statistics.median(max(0.0, r['features'][name] - ratios[name] * sum(
                own[id(r)].get(k, 0.0) for k in kinds)) for r in data if id(r) in own and r['features']['masters']
                and own[id(r)].get('CELL')), 1)
    model['region'] = region


def cold_ratios(data: list) -> dict:
    """{cold feature: largest cold count over its warm count seen} for COLD_RATIO's features; 1 for the rest."""
    out = {name: 1.0 for name in eta_inputs.COLD}
    for name, (cold, warm) in COLD_RATIO.items():
        seen = [r['counts'].get(cold, 0) / r['counts'][warm] for r in data if r['counts'].get(warm)]
        out[name] = round(min(1.0, max(seen, default=1.0)), 3)
    return out


def _total(seconds: dict) -> float:
    """Seconds of a {group: seconds} but the animation group."""
    return sum(s for g, s in seconds.items() if g != 'animation')


def errors(data: list, model: dict) -> list:
    """Per build: plugin, actual seconds, and the model's in sample, left out of the fit, and from its export alone
    (None for a test block or a build without an export), animation left out."""
    unit = {'serial': 1.0, 'pool': 1.0, 'disk': 1.0}
    out = []
    for i, r in enumerate(data):
        left_out = fit(data[:i] + data[i + 1:])
        row = {'plugin': r['plugin'], 'actual': _total(r['groups']),
               'in_sample': _total(eta.grouped_seconds(model['groups'], r['features'], unit)),
               'left_out': _total(eta.grouped_seconds(left_out, r['features'], unit)), 'export': None}
        scoped = not r['features']['masters'] and r['features']['cells'] < WHOLE_CELLS
        if r['export'] and not scoped:
            own = eta_inputs.export_counts(r['export'], model['per_record'])
            feats = eta_inputs.export_features(own, bool(r['features']['masters']), model)
            row['export'] = _total(eta.predict(model, feats, False))
        out.append(row)
    return out


def error_summary(table: list) -> dict:
    """{mode: {median, mean} absolute error as a share of the actual time, builds} over `table`."""
    out = {}
    for mode in ('in_sample', 'left_out', 'export'):
        shares = [abs(r[mode] - r['actual']) / r['actual'] for r in table if r[mode] is not None and r['actual']]
        out[mode] = {'median': round(statistics.median(shares), 3), 'mean': round(statistics.mean(shares), 3),
                     'builds': len(shares)}
    return out


def main() -> None:
    """The command line (the module notes): fit, print each build's error and the summary, write the model."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('sources', nargs='+', type=Path, help='Log folders and finished builds\' .build.json stamps')
    ap.add_argument('--benchmark', type=Path, required=True, help="The reference machine's machine_benchmark result")
    ap.add_argument('--export-root', type=Path, default=ROOT / 'export')
    ap.add_argument('--main-gb', type=float, default=9.0, help="The main process's peak on a whole game build")
    ap.add_argument('--out', type=Path, default=eta.DATA)
    args = ap.parse_args()
    data = rows(builds(args.sources), args.export_root)
    exports = sorted({r['export'] for r in data if r['export']})
    model = {'version': 1, 'reference': json.loads(args.benchmark.read_text(encoding='utf-8')),
             'main_gb': args.main_gb, 'groups': fit(data), 'cold_ratios': cold_ratios(data),
             'per_record': per_record(exports)}
    export_model(data, model)
    table = errors(data, model)
    for r in table:
        found = '' if r['export'] is None else f"{r['export']:8.0f}"
        print(f"{r['plugin'][:34]:34} {r['actual']:8.0f} {r['in_sample']:8.0f} {r['left_out']:8.0f} {found}")
    model['fit'] = {'builds': len(data), 'error': error_summary(table)}
    print(json.dumps(model['fit'], indent=1))
    args.out.write_text(json.dumps(model, indent=1) + '\n', encoding='utf-8')
    print(f'written: {args.out}')


if __name__ == '__main__':
    main()
