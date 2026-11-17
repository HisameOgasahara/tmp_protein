import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter


VERSION = "0.3.0"
COLABDESIGN_REVISION = "27b15b11e39e0b99383975895bca9e0b0e907da1"
SOURCE = Path(__file__).resolve().parent


def run_logged(arguments, log, env):
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps([str(argument) for argument in arguments]) + "\n")
        handle.flush()
        result = subprocess.run([str(argument) for argument in arguments], stdout=handle,
                                stderr=subprocess.STDOUT, env=env)
    if result.returncode:
        with log.open(encoding="utf-8", errors="replace") as handle:
            print("".join(deque(handle, maxlen=40)), flush=True)
        raise RuntimeError(f"Exit {result.returncode}. Full log: {log}")


def prepare_runtime(root):
    state = Path("/content/trka88_af2_v0_3_0")
    state.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONUNBUFFERED="1", XLA_PYTHON_CLIENT_PREALLOCATE="false")
    log = root / "runtime/installation.log"
    uv = shutil.which("uv")
    if uv is None:
        run_logged([sys.executable, "-m", "pip", "install", "uv"], log, env)
        uv = shutil.which("uv")
    python = state / "venv/bin/python"
    if not (state / "installed").is_file():
        run_logged([uv, "venv", "--allow-existing", "--python", "3.11", state / "venv"], log, env)
        run_logged([
            uv, "pip", "install", "--python", python,
            "jax[cuda12]==0.4.35", "numpy==1.26.4", "dm-haiku==0.0.13",
            "chex==0.1.88", "optax==0.2.4", "biopython==1.85",
            f"colabdesign @ git+https://github.com/sokrypton/ColabDesign.git@{COLABDESIGN_REVISION}",
        ], log, env)
        run_logged([uv, "pip", "check", "--python", python], log, env)
        (state / "installed").touch()
    parameters = state / "params"
    parameters.mkdir(exist_ok=True)
    if not (parameters / "params_model_1_ptm.npz").is_file():
        archive = state / "alphafold_params.tar"
        run_logged([
            "curl", "--fail", "--location", "--retry", "3", "--output", archive,
            "https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar",
        ], log, env)
        # Extract into a temporary directory so an interrupted write is retried.
        staging = Path(mkdtemp(prefix="params_", dir=state))
        run_logged(["tar", "-xf", archive, "-C", staging, "params_model_1_ptm.npz"], log, env)
        (staging / "params_model_1_ptm.npz").replace(parameters / "params_model_1_ptm.npz")
        staging.rmdir()
        archive.unlink()
    run_logged([uv, "pip", "list", "--python", python], root / "runtime/packages.log", env)
    run_logged(["nvidia-smi"], root / "runtime/environment.log", env)
    run_logged([python, "-c", "import sys,jax; print(sys.version); print(jax.__version__); print(jax.devices())"],
               root / "runtime/environment.log", env)
    return python, parameters, env


def run(revision):
    root = Path(mkdtemp(prefix="trka88_af2_", dir="/content"))
    (root / "runtime").mkdir()
    shutil.copytree(SOURCE.parent / "examples/trka88", root / "inputs")
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (root / "inputs").iterdir() if path.is_file()}
    source = {
        "version": VERSION, "revision": revision, "colabdesign_revision": COLABDESIGN_REVISION,
        "candidate": "TrkA_88", "model": "model_1_ptm", "seed": 0, "num_recycles": 3,
        "initial_guess": True, "target_template": True, "binder_template": False,
        "msa": "single_sequence", "input_sha256": hashes,
    }
    (root / "source.json").write_text(json.dumps(source, indent=2) + "\n")
    print(f"TrkA_88 · v{VERSION} · logs: {root / 'runtime'}", flush=True)
    start = perf_counter()
    try:
        python, parameters, env = prepare_runtime(root)
        run_logged([python, SOURCE / "predict.py", root, parameters], root / "runtime/af2.log", env)
    except Exception:
        print("Failure archive: " + shutil.make_archive(str(root) + "_failed", "zip", root), flush=True)
        raise
    finally:
        (root / "runtime/timing.json").write_text(json.dumps({"seconds": perf_counter() - start}))
    print(shutil.make_archive(str(root), "zip", root), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
