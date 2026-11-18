import hashlib
import json
import shutil
import sys
import traceback
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

import numpy as np

from workflow import AF2_REVISION, SOURCE, prepare_runtime, run_logged


VERSION = "0.2.0"


def build_cases():
    baseline = {
        "threading": "original", "input": "design", "recycles": 3,
        "initial_guess": True, "target_template": True, "seed": 0, "precision": "default",
    }
    variants = [
        ("mutate_baseline", {"threading": "mutate"}),
        ("original_thread", {}),
        ("seed_1", {"seed": 1}),
        ("seed_2", {"seed": 2}),
        ("recycles_12", {"recycles": 12}),
        ("no_initial_guess", {"initial_guess": False}),
        ("empty_target_template", {"target_template": False}),
        ("grafted_target_sidechains", {"input": "grafted_target"}),
        ("published_coordinates_control", {"input": "published"}),
        ("published_target_control", {"input": "published_target"}),
        ("highest_precision", {"precision": "highest"}),
        ("original_thread_repeat", {}),
    ]
    return [{"id": name, **baseline, **changes} for name, changes in variants]


def feature_differences(root):
    differences = {}
    baseline = root / "original_thread"
    for case in build_cases():
        entries = {}
        for name in ("raw_features", "processed_features", "initial_guess"):
            reference_path = baseline / f"{name}.npz"
            compared_path = root / case["id"] / f"{name}.npz"
            if not reference_path.is_file() or not compared_path.is_file():
                continue
            with np.load(reference_path) as reference, np.load(compared_path) as compared:
                for key in sorted(set(reference.files) | set(compared.files)):
                    if key not in reference or key not in compared:
                        entries[f"{name}/{key}"] = {"different_keys": True}
                        continue
                    left, right = reference[key], compared[key]
                    if left.shape != right.shape:
                        entries[f"{name}/{key}"] = {"reference_shape": left.shape, "case_shape": right.shape}
                    elif not np.array_equal(left, right, equal_nan=True):
                        entries[f"{name}/{key}"] = {
                            "maximum_absolute_difference": float(np.nanmax(np.abs(left.astype(float) - right.astype(float))))
                        }
        differences[case["id"]] = entries
    (root / "feature_differences.json").write_text(json.dumps(differences, indent=2))


def run(revision):
    root = Path(mkdtemp(prefix="trka88_diagnostics_", dir="/content"))
    (root / "runtime").mkdir()
    shutil.copytree(SOURCE.parents[1] / "inputs/trka", root / "inputs")
    cases = build_cases()
    source = {"diagnostic_version": VERSION, "revision": revision, "af2_revision": AF2_REVISION,
              "paper_rmsd_angstrom": 1.4, "cases": cases}
    (root / "source.json").write_text(json.dumps(source, indent=2))
    reports = []
    try:
        python, upstream, env = prepare_runtime(root)
        parameter = upstream / "af2_initial_guess/model_weights/params/params_model_1_ptm.npz"
        with parameter.open("rb") as handle:
            source["weights_sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
        source["upstream_source_sha256"] = {
            str(path.relative_to(upstream)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (upstream / "af2_initial_guess").rglob("*.py")
        }
        (root / "source.json").write_text(json.dumps(source, indent=2))
        for index, case in enumerate(cases, 1):
            directory = root / case["id"]
            directory.mkdir()
            (directory / "case.json").write_text(json.dumps(case, indent=2))
            print(f"{index}/{len(cases)} {case['id']}", flush=True)
            start = perf_counter()
            try:
                run_logged([python, SOURCE / "diagnostic_case.py", directory, root / "inputs", upstream],
                           directory / "execution.log", env)
                report = json.loads((directory / "result.json").read_bytes())
            except Exception as error:
                report = {**case, "status": "failed", "error": str(error)}
                (directory / "failure.txt").write_text(traceback.format_exc())
            report["seconds"] = perf_counter() - start
            reports.append(report)
            (root / "diagnostic_summary.json").write_text(json.dumps(reports, indent=2))
            print(case["id"], report["status"], report.get("rmsd_vs_original_design"), flush=True)
        feature_differences(root)
    except Exception:
        (root / "runtime/setup_failure.txt").write_text(traceback.format_exc())
        print("Setup failed; details are included in the ZIP.", flush=True)
    finally:
        print(shutil.make_archive(str(root), "zip", root), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
