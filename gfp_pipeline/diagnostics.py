import argparse
import json
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZipFile

from run import FOUNDRY_REV, SOURCE, prepare_runtime, run_logged
from megadock_runtime import prepare_megadock
from nanobody_fold import prepare_nanobody


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--experiment", choices=("minimizer_docking", "enhancer_split", "enhancer_docking"), required=True)
    args = parser.parse_args()
    settings = json.loads((SOURCE / "diagnostic_experiments.json").read_text(encoding="utf-8"))
    root = Path(mkdtemp(prefix=f"gfp_{args.experiment}_", dir="/content"))
    for folder in ("config", "runtime", "structures", "metrics"):
        (root / folder).mkdir()
    print(root, flush=True)
    (root / "config/diagnostics.json").write_text(json.dumps(settings, indent=2))
    (root / "config/source.json").write_text(json.dumps({
        "revision": args.revision, "version": settings["version"], "mode": "diagnostics",
        "diagnostic_version": settings["diagnostic_version"],
        "experiment": args.experiment, "foundry_revision": FOUNDRY_REV,
        "reference_run": settings["reference_run"],
        "binder_input": (
            "run07_predicted_monomer" if args.experiment == "enhancer_docking" else
            "crystal_monomer" if args.experiment == "minimizer_docking" else "predicted_and_crystal_monomers"
        ),
    }, indent=2))
    control = "minimizer" if args.experiment == "minimizer_docking" else "enhancer"
    previous = "minimizer_seed_search" if control == "minimizer" else "enhancer_target_only"
    baseline = SOURCE.parent / settings["reference_run"] / previous
    shutil.copyfile(baseline / f"config/reference_{control}.json", root / f"config/reference_{control}.json")
    shutil.copyfile(baseline / "metrics/benchmark_summary.json", root / "config/baseline_summary.json")
    if args.experiment == "enhancer_docking":
        archive = SOURCE.parent / settings["enhancer_monomer_archive"]
        with ZipFile(archive) as bundle:
            (root / "config/predicted_binder.json").write_bytes(
                bundle.read("enhancer_split/config/predicted_binder.json")
            )
    if args.experiment.endswith("_docking"):
        python, env = prepare_megadock(root, settings)
        print("MEGADOCK: GPU global search, pose generation, evaluation", flush=True)
        run_logged([python, SOURCE / "megadock_compare.py", root, args.experiment], root / "runtime/docking.log", env)
    else:
        fold_python, fold_env = prepare_nanobody(root, settings)
        print("Enhancer: NanoBodyBuilder2 monomer prediction and refinement", flush=True)
        run_logged([fold_python, SOURCE / "nanobody_fold.py", root], root / "runtime/nanobody.log", fold_env)
        python, env = prepare_runtime(root, benchmark_only=True)
        for seed in settings["seeds"]:
            print(f"Enhancer seed {seed}: NanoBodyBuilder2 structure, crystal control", flush=True)
            run_logged([python, SOURCE / "enhancer_split.py", seed], root / f"runtime/enhancer_seed{seed}.log", env)
        run_logged([python, SOURCE / "enhancer_split.py", "summary"], root / "runtime/summary.log", env)
    print(shutil.make_archive(str(root), "zip", root_dir=root), flush=True)


if __name__ == "__main__":
    main()
