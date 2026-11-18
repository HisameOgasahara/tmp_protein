"""Design TrkA binders and score them with the calibrated AF2 filter.

Two environments are involved and they cannot be merged: RFdiffusion3 and MPNN
need the foundry stack on Python 3.12, while the upstream AF2 predictor needs
JAX and PyRosetta on Python 3.11. This script runs in the notebook's own
interpreter and drives both as subprocesses, so each stage sees its own venv.
"""

import importlib.util
import json
import shutil
import sys
import traceback
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter


VERSION = "0.2.0"
SOURCE = Path(__file__).resolve().parent
AF2_SOURCE = SOURCE.parent / "af2_filter"
RECYCLES = 3


def load(name, path):
    """Load by path. Both packages hold a workflow.py, so names alone collide."""
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


design_runtime = load("rfd3_runtime", SOURCE / "runtime.py")
af2_workflow = load("af2_workflow", AF2_SOURCE / "workflow.py")
trka_design = load("trka_design", SOURCE / "trka_design.py")
FOUNDRY_REV = design_runtime.FOUNDRY_REV


def run(revision):
    root = Path(mkdtemp(prefix="trka_design_", dir="/content"))
    (root / "runtime").mkdir()
    (root / "backbones").mkdir()
    shutil.copytree(SOURCE.parents[1] / "inputs/trka", root / "inputs")
    settings = {"recycles": RECYCLES}
    (root / "settings.json").write_text(json.dumps(settings, indent=2))
    source = {
        "design_version": VERSION, "revision": revision, "foundry_revision": FOUNDRY_REV,
        "af2_revision": af2_workflow.AF2_REVISION, "target": "TrkA D5 domain, design frame",
        "hotspots": ["B108 MET", "B115 PHE", "B145 LEU"],
        "binder_lengths": None, "backbones_per_length": None,
        "backbones": None, "sequences_per_backbone": None, **settings,
    }
    (root / "source.json").write_text(json.dumps(source, indent=2))
    timings = {}
    start = perf_counter()
    try:
        print("=== 1/2 설계 (RFdiffusion3 + MPNN) ===", flush=True)
        design_python, design_env = design_runtime.prepare_runtime(root)
        source["binder_lengths"] = list(trka_design.BINDER_LENGTHS)
        source["backbones_per_length"] = trka_design.BACKBONES_PER_LENGTH
        source["backbones"] = trka_design.BACKBONES
        source["sequences_per_backbone"] = trka_design.SEQUENCES_PER_BACKBONE
        (root / "source.json").write_text(json.dumps(source, indent=2))
        for stage in ("prepare_target", "generate_backbones", "design_sequences"):
            print(f"-- {stage}", flush=True)
            began = perf_counter()
            af2_workflow.run_streamed([design_python, "-u", SOURCE / "trka_design.py", stage, root],
                                      root / f"runtime/{stage}.log", design_env)
            timings[stage] = perf_counter() - began
            (root / "runtime/timings.json").write_text(json.dumps(timings, indent=2))

        print("\n=== 2/2 채점 (AF2 initial guess) ===", flush=True)
        af2_python, upstream, af2_env = af2_workflow.prepare_runtime(root)
        began = perf_counter()
        af2_workflow.run_streamed(
            [af2_python, "-u", SOURCE.parent / "af2_filter/score_designs.py", root, upstream],
            root / "runtime/score_designs.log", af2_env)
        timings["score_designs"] = perf_counter() - began
    except Exception:
        (root / "runtime/failure.txt").write_text(traceback.format_exc())
        print("실패 기록을 ZIP에 저장했습니다.", flush=True)
    finally:
        timings["total"] = perf_counter() - start
        (root / "runtime/timings.json").write_text(json.dumps(timings, indent=2))
        print(shutil.make_archive(str(root), "zip", root), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
