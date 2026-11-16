import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

from run import FOUNDRY_REV, SOURCE, ensure_uv, prepare_runtime, run_logged, save_environment


def prepare_lightdock(root, settings):
    config = settings["docking"]
    state = Path("/content") / f"gfp_lightdock_{settings['version']}"
    state.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    log = root / "runtime/installation.log"
    uv = ensure_uv(state, log, env)
    venv = state / "venv"
    python = venv / "bin/python"
    if not (state / "installed").exists():
        run_logged([uv, "venv", "--allow-existing", "--python", config["python_version"], venv], log, env)
        install = [uv, "pip", "install", "--python", python]
        run_logged([*install, *config["build_packages"]], log, env)
        run_logged([*install, "--no-build-isolation", *config["packages"]], log, env)
        run_logged([uv, "pip", "check", "--python", python], log, env)
        (state / "installed").touch()
    save_environment(uv, python, root, env)
    return python, env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--experiment", choices=("minimizer_docking", "enhancer_split"), required=True)
    args = parser.parse_args()
    settings = json.loads((SOURCE / "diagnostic_experiments.json").read_text(encoding="utf-8"))
    root = Path(mkdtemp(prefix=f"gfp_{args.experiment}_", dir="/content"))
    for folder in ("config", "runtime", "structures", "metrics"):
        (root / folder).mkdir()
    print(root, flush=True)
    (root / "config/diagnostics.json").write_text(json.dumps(settings, indent=2))
    (root / "config/source.json").write_text(json.dumps({
        "revision": args.revision, "version": settings["version"], "mode": "diagnostics",
        "experiment": args.experiment, "foundry_revision": FOUNDRY_REV,
        "reference_run": settings["reference_run"],
    }, indent=2))
    control = "minimizer" if args.experiment == "minimizer_docking" else "enhancer"
    previous = "minimizer_seed_search" if control == "minimizer" else "enhancer_target_only"
    baseline = SOURCE.parent / settings["reference_run"] / previous
    shutil.copyfile(baseline / f"config/reference_{control}.json", root / f"config/reference_{control}.json")
    shutil.copyfile(baseline / "metrics/benchmark_summary.json", root / "config/baseline_summary.json")
    if control == "minimizer":
        python, env = prepare_lightdock(root, settings)
        print("LightDock: setup, global search, clustering, ranking", flush=True)
        run_logged([python, SOURCE / "lightdock_compare.py", root], root / "runtime/docking.log", env)
    else:
        python, env = prepare_runtime(root, benchmark_only=True)
        for seed in settings["seeds"]:
            print(f"Enhancer seed {seed}: monomer, predicted structure, crystal control", flush=True)
            run_logged([python, SOURCE / "enhancer_split.py", seed], root / f"runtime/enhancer_seed{seed}.log", env)
        run_logged([python, SOURCE / "enhancer_split.py", "summary"], root / "runtime/summary.log", env)
    print(shutil.make_archive(str(root), "zip", root_dir=root), flush=True)


if __name__ == "__main__":
    main()
