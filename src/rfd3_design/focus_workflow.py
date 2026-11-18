"""Drive the focused resampling run: one backbone, 50 sequences, same filter.

Mirrors trka_workflow but skips RFdiffusion3 entirely -- the backbone comes from
a previous run that is committed to the repository, so the expensive stage is
not repeated and the result is directly comparable to it.
"""

import importlib.util
import json
import shutil
import sys
import traceback
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter


VERSION = "0.3.0"
SOURCE = Path(__file__).resolve().parent
AF2_SOURCE = SOURCE.parent / "af2_filter"
RECYCLES = 3


def load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


design_runtime = load("rfd3_runtime", SOURCE / "runtime.py")
af2_workflow = load("af2_workflow", AF2_SOURCE / "workflow.py")
focus_design = load("focus_design", SOURCE / "focus_design.py")
FOUNDRY_REV = design_runtime.FOUNDRY_REV


def run(revision):
    root = Path(mkdtemp(prefix="trka_focus_", dir="/content"))
    (root / "runtime").mkdir()
    (root / "backbones").mkdir()
    shutil.copytree(SOURCE.parents[1] / "inputs/trka", root / "inputs")
    settings = {"recycles": RECYCLES}
    (root / "settings.json").write_text(json.dumps(settings, indent=2))
    source = {
        "design_version": VERSION, "revision": revision, "foundry_revision": FOUNDRY_REV,
        "af2_revision": af2_workflow.AF2_REVISION, "target": "TrkA D5 domain, design frame",
        "mode": "focused resampling of one backbone",
        "backbone": focus_design.BACKBONE, "backbone_source": focus_design.SOURCE_RUN,
        "binder_length": focus_design.BINDER_LENGTH,
        "sequences": focus_design.SEQUENCES, "mpnn_seeds": list(focus_design.SEEDS),
        **settings,
    }
    (root / "source.json").write_text(json.dumps(source, indent=2))
    timings = {}
    start = perf_counter()
    try:
        print("=== 1/2 서열 설계 (MPNN, 백본 생성 없음) ===", flush=True)
        design_python, design_env = design_runtime.prepare_runtime(root)
        for stage in ("prepare_backbone", "design_sequences"):
            print(f"-- {stage}", flush=True)
            began = perf_counter()
            af2_workflow.run_streamed(
                [design_python, "-u", SOURCE / "focus_design.py", stage, root],
                root / f"runtime/{stage}.log", design_env)
            timings[stage] = perf_counter() - began
            (root / "runtime/timings.json").write_text(json.dumps(timings, indent=2))

        print("\n=== 2/2 채점 (AF2 initial guess) ===", flush=True)
        af2_python, upstream, af2_env = af2_workflow.prepare_runtime(root)
        began = perf_counter()
        af2_workflow.run_streamed(
            [af2_python, "-u", AF2_SOURCE / "score_designs.py", root, upstream],
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
