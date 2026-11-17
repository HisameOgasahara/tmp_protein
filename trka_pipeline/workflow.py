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


VERSION = "0.3.3"
AF2_REVISION = "cafa3853ac94dceb1b908c8d9e6954d71749871a"
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
    env = dict(os.environ, PYTHONUNBUFFERED="1", XLA_PYTHON_CLIENT_PREALLOCATE="false",
               MPLBACKEND="Agg")
    log = root / "runtime/installation.log"
    uv = shutil.which("uv")
    if uv is None:
        run_logged([sys.executable, "-m", "pip", "install", "uv"], log, env)
        uv = shutil.which("uv")
    python = state / "original_venv/bin/python"
    if not (state / "original_installed").is_file():
        run_logged([uv, "venv", "--allow-existing", "--python", "3.11", state / "original_venv"], log, env)
        run_logged([
            uv, "pip", "install", "--python", python,
            "jax[cuda12]==0.4.35", "numpy==1.26.4", "dm-haiku==0.0.13",
            "biopython==1.81", "tensorflow-cpu==2.18.1", "ml-collections==0.1.1",
            "dm-tree==0.1.9", "scipy==1.12.0", "pandas==2.2.3", "mock==5.1.0",
            "--find-links", "https://west.rosettacommons.org/pyrosetta/quarterly/release/",
            "pyrosetta==2026.3+releasequarterly.5e498f1409",
        ], log, env)
        run_logged([uv, "pip", "check", "--python", python], log, env)
        (state / "original_installed").touch()
    cuda_root = subprocess.check_output([
        str(python), "-c",
        "import importlib.util,pathlib; "
        "spec=importlib.util.find_spec('nvidia.cuda_nvcc'); "
        "root=pathlib.Path(next(iter(spec.submodule_search_locations))); "
        "assert (root/'bin/ptxas').is_file(), root; "
        "assert (root/'nvvm/libdevice/libdevice.10.bc').is_file(), root; "
        "print(root)",
    ], env=env, text=True).strip()
    env["CUDA_ROOT"] = cuda_root
    env["PATH"] = str(Path(cuda_root) / "bin") + os.pathsep + env.get("PATH", "")
    run_logged([python, "-c", "import sys,jax; print(sys.version); print(jax.__version__); print(jax.devices()); assert any(d.platform == 'gpu' for d in jax.devices())"],
               root / "runtime/environment.log", env)
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
    upstream = state / f"dl_binder_design_{AF2_REVISION}"
    if not (upstream / "af2_initial_guess/predict.py").is_file():
        upstream.mkdir(exist_ok=True)
        archive = state / "dl_binder_design.tar.gz"
        run_logged(["curl", "--fail", "--location", "--retry", "3", "--output", archive,
                    f"https://codeload.github.com/nrbennet/dl_binder_design/tar.gz/{AF2_REVISION}"],
                   log, env)
        run_logged(["tar", "-xzf", archive, "--strip-components=1", "-C", upstream], log, env)
    env["PYTHONPATH"] = str(upstream / "af2_initial_guess")
    env["TF_CPP_MIN_LOG_LEVEL"] = "2"
    env["TF_NUM_INTRAOP_THREADS"] = "1"
    env["TF_NUM_INTEROP_THREADS"] = "1"
    run_logged([python, "-c", "from alphafold.model import model; import pyrosetta; print('Original AF2 and PyRosetta imports succeeded.')"],
               root / "runtime/environment.log", env)
    model_weights = upstream / "af2_initial_guess/model_weights"
    model_weights.mkdir(exist_ok=True)
    weight_link = model_weights / "params_model_1_ptm.npz"
    if not weight_link.exists():
        weight_link.symlink_to(parameters / "params_model_1_ptm.npz")
    return python, upstream, env


def run(revision):
    root = Path(mkdtemp(prefix="trka88_af2_", dir="/content"))
    (root / "runtime").mkdir()
    shutil.copytree(SOURCE.parent / "examples/trka88", root / "inputs")
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in (root / "inputs").iterdir() if path.is_file()}
    source = {
        "version": VERSION, "revision": revision, "af2_repository": "https://github.com/nrbennet/dl_binder_design",
        "af2_revision": AF2_REVISION,
        "candidate": "TrkA_88", "model": "model_1_ptm", "seed": 0, "num_recycles": 3,
        "initial_guess": True, "target_template": True, "binder_template": False,
        "msa": "single_sequence", "input_sha256": hashes,
    }
    (root / "source.json").write_text(json.dumps(source, indent=2) + "\n")
    print(f"TrkA_88 쨌 v{VERSION} 쨌 logs: {root / 'runtime'}", flush=True)
    start = perf_counter()
    try:
        python, upstream, env = prepare_runtime(root)
        run_logged([python, SOURCE / "predict.py", root, upstream], root / "runtime/af2.log", env)
    except Exception:
        print("Failure archive: " + shutil.make_archive(str(root) + "_failed", "zip", root), flush=True)
        raise
    finally:
        (root / "runtime/timing.json").write_text(json.dumps({"seconds": perf_counter() - start}))
    print(shutil.make_archive(str(root), "zip", root), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
