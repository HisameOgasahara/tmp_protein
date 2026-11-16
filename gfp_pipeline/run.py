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


def run_logged(args, log, env):
    args = [str(arg) for arg in args]
    with log.open("a", encoding="utf-8") as handle:
        print(">", *args, file=handle, flush=True)
        result = subprocess.run(args, env=env, stdout=handle, stderr=subprocess.STDOUT)
    if result.returncode:
        with log.open(encoding="utf-8", errors="replace") as handle:
            print("".join(deque(handle, maxlen=60)), file=sys.stderr)
        raise RuntimeError(f"Exit {result.returncode}. Full log: {log}")


def prepare_runtime(root):
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
        uv = shutil.which("uv")
        if uv is None:
            tools = state / "tools"
            run_logged(["bash", "-o", "pipefail", "-c",
                        'curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$1" UV_NO_MODIFY_PATH=1 sh',
                        "uv-bootstrap", tools], log, env)
            uv = tools / "uv"
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
    run_logged([venv / "bin/foundry", "install", "rfd3", "ligandmpnn", "rf3",
                "--checkpoint-dir", weights], root / "runtime/checkpoints.log", env)
    return python, env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--assays", type=Path, default=SOURCE / "controls.csv")
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    root = Path(mkdtemp(prefix="gfp_binder_", dir="/content"))
    for folder in ("config", "runtime", "structures", "metrics"):
        (root / folder).mkdir()
    print(root, flush=True)
    shutil.copyfile(args.assays, root / "config/assays.csv")
    (root / "config/source.json").write_text(json.dumps({
        "revision": args.revision, "foundry_revision": FOUNDRY_REV,
        "assay_file": args.assays.name,
    }))
    python, env = prepare_runtime(root)
    stages = (("prepare", "preparing GFP and assay data"), ("backbones", "1/4 RFD3"),
              ("sequences", "2/4 LigandMPNN"), ("complexes", "3/4 RF3"),
              ("fluorescence", "4/4 Ridge"))
    for stage, label in stages:
        print(label, flush=True)
        run_logged([python, "-u", SOURCE / "stages.py", stage],
                   root / "runtime" / f"{stage}.log", env)
    archive = shutil.make_archive(str(root), "zip", root_dir=root)
    print(archive, flush=True)


if __name__ == "__main__":
    main()
