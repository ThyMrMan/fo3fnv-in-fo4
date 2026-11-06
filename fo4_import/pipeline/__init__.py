"""The FO4 pipeline: the spike's converters run over a scope with the export read once, meshes and Elric's
physics cached, and scripts compiled incrementally. A process of a recorded build (a worker) records its
inputs from its first import of this package (build_inputs.resume).

See: docs/fork/fo4_pipeline.md#skeleton
See: docs/fork/fo4_plugin_layout.md#build-plan
"""

from fo4_import.pipeline import build_inputs

build_inputs.resume()
