import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path
from tempfile import mkdtemp


FOUNDRY_REV = "0d0b0ba44fab7ca76aa4b625c014ce5964c7d284"
SOURCE = Path(__file__).resolve().parent
BENCHMARK_SEEDS = (0, 1, 2)


def run_logged(args, log, env, cwd=None):
    args = [str(arg) for arg in args]
    with log.open("a", encoding="utf-8") as handle:
        print(">", *args, file=handle, flush=True)
        result = subprocess.run(args, env=env, cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        with log.open(encoding="utf-8", errors="replace") as handle:
            print("".join(deque(handle, maxlen=60)), file=sys.stderr)
        raise RuntimeError(f"Exit {result.returncode}. Full log: {log}")


def ensure_uv(state, log, env):
    uv = shutil.which("uv")
    if uv is None:
        uv = state / "tools/uv"
        if not uv.is_file():
            run_logged(["bash", "-o", "pipefail", "-c",
                        'curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$1" UV_NO_MODIFY_PATH=1 sh',
                        "uv-bootstrap", uv.parent], log, env)
    return uv


def save_environment(uv, python, root, env):
    with (root / "runtime/packages.json").open("w", encoding="utf-8") as handle:
        subprocess.run([str(uv), "pip", "list", "--python", str(python), "--format", "json"],
                       env=env, stdout=handle, check=True)
    run_logged([python, "-c", "import sys,platform; print(sys.version); print(platform.platform())"],
               root / "runtime/environment.log", env)


def prepare_runtime(root, benchmark_only):
    state = Path("/content") / ("gfp_foundry_" + FOUNDRY_REV[:8])
    state.mkdir(exist_ok=True)
    weights = state / "weights"
    weights.mkdir(exist_ok=True)
    venv = state / "venv"
    python = venv / "bin/python"
    env = dict(os.environ, DESIGN_RUN=str(root), FOUNDRY_CHECKPOINT_DIRS=str(weights),
               DISABLE_CUEQUIVARIANCE="1", PYTHONUNBUFFERED="1")
    env.pop("RFD3_LOW_MEMORY_MODE", None)
    log = root / "runtime/installation.log"
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                         capture_output=True, text=True)
    if gpu.returncode or not any("T4" in name for name in gpu.stdout.splitlines()):
        raise RuntimeError("Select a Google Colab T4 GPU runtime.")
    if not (state / "installed").exists():
        uv = ensure_uv(state, log, env)
        run_logged([uv, "venv", "--allow-existing", "--python", "3.12", venv], log, env)
        index = "https://download.pytorch.org/whl/cu128"
        install = [uv, "pip", "install", "--python", python]
        constraints = state / "constraints.txt"
        constraints.write_text("torch==2.11.0+cu128\natomworks==3.0.1\n")
        run_logged([*install, "--index-url", index, "torch==2.11.0+cu128"], log, env)
        run_logged([*install, "--extra-index-url", index, "--index-strategy", "unsafe-best-match",
                    "--constraint", constraints,
                    f"rc-foundry[rfd3] @ git+https://github.com/RosettaCommons/foundry.git@{FOUNDRY_REV}",
                    "atomworks[ml]==3.0.1", "biopython", "scikit-learn"], log, env)
        run_logged([uv, "pip", "check", "--python", python], log, env)
        (state / "installed").touch()
    save_environment(ensure_uv(state, log, env), python, root, env)
    run_logged([python, "-c", "import torch; print('torch',torch.__version__); print('CUDA',torch.version.cuda); print('GPU',torch.cuda.get_device_name())"],
               root / "runtime/environment.log", env)
    models = ["rf3"] if benchmark_only else []
    run_logged([python, "-u", SOURCE / "checkpoints.py", weights, *models],
               root / "runtime/checkpoints.log", env)
    return python, env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assays", type=Path, default=SOURCE / "controls.csv")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--benchmark-only", action="store_true")
    parser.add_argument("--benchmark-template", choices=("target", "both"), default="both")
    parser.add_argument("--benchmark-recycles", type=int, choices=(3, 10), default=10)
    parser.add_argument("--benchmark-seeds", type=int, nargs="+", default=list(BENCHMARK_SEEDS))
    parser.add_argument("--benchmark-controls", nargs="+", choices=("enhancer", "minimizer"),
                        default=["enhancer", "minimizer"])
    args = parser.parse_args()
    if args.benchmark_only and args.assays != SOURCE / "controls.csv":
        parser.error("--assays is available in the full pipeline.")
    if any(seed < 0 or seed >= 2**32 for seed in args.benchmark_seeds) or len(set(args.benchmark_seeds)) != len(args.benchmark_seeds):
        parser.error("Benchmark seeds must be unique integers in [0, 2**32).")
    root = Path(mkdtemp(prefix="gfp_binder_", dir="/content"))
    for folder in ("config", "runtime", "structures", "metrics"):
        (root / folder).mkdir()
    print(root, flush=True)
    shutil.copyfile(args.assays, root / "config/assays.csv")
    (root / "config/source.json").write_text(json.dumps({
        "revision": args.revision, "foundry_revision": FOUNDRY_REV,
        "assay_file": args.assays.name,
        "mode": "benchmark" if args.benchmark_only else "full",
        "rf3_seeds": args.benchmark_seeds if args.benchmark_only else (0,),
        "benchmark_template": args.benchmark_template if args.benchmark_only else None,
        "benchmark_controls": list(dict.fromkeys(args.benchmark_controls)) if args.benchmark_only else None,
        "rf3": {"num_steps": 50, "diffusion_batch_size": 1,
                "n_recycles": args.benchmark_recycles if args.benchmark_only else 3},
    }))
    python, env = prepare_runtime(root, args.benchmark_only)
    stages = [("preparing GFP and assay data", "prepare")]
    if args.benchmark_only:
        stages.extend((f"RF3 controls: seed {seed}", "benchmark", str(seed))
                      for seed in args.benchmark_seeds)
        stages.append(("comparing poses with crystal structures", "benchmark_report"))
    else:
        stages.extend([("1/4 RFD3", "backbones"), ("2/4 LigandMPNN", "sequences"),
                       ("3/4 RF3", "complexes"), ("4/4 Ridge", "fluorescence")])
    for label, stage, *parameters in stages:
        print(label, flush=True)
        log_name = "_".join((stage, *parameters))
        run_logged([python, "-u", SOURCE / "stages.py", stage, *parameters],
                   root / "runtime" / f"{log_name}.log", env)
    archive = shutil.make_archive(str(root), "zip", root_dir=root)
    print(archive, flush=True)


if __name__ == "__main__":
    main()
