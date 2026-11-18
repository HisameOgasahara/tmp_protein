import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path


FOUNDRY_REV = "0d0b0ba44fab7ca76aa4b625c014ce5964c7d284"
SOURCE = Path(__file__).resolve().parent


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
    run_logged([python, "-u", SOURCE / "checkpoints.py", weights],
               root / "runtime/checkpoints.log", env)
    return python, env
