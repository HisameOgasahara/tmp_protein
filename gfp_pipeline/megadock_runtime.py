import json
import os
import shutil
import subprocess
from pathlib import Path

from run import ensure_uv, run_logged, save_environment


def prepare_megadock(root, settings):
    config = settings["docking"]
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,compute_cap", "--format=csv,noheader"],
                         capture_output=True, text=True, check=True)
    name, capability = gpu.stdout.splitlines()[0].rsplit(",", 1)
    architecture = "sm_" + capability.strip().replace(".", "")
    nvcc = shutil.which("nvcc")
    if nvcc is None:
        raise RuntimeError("MEGADOCK requires a Colab GPU runtime with the CUDA compiler nvcc.")
    state = Path("/content") / f"gfp_megadock_{settings['version']}_{architecture}"
    state.mkdir(exist_ok=True)
    log = root / "runtime/installation.log"
    uv = ensure_uv(state, log, env)
    python = state / "venv/bin/python"
    source = state / "MEGADOCK"
    samples = state / "cuda-samples"
    if not (state / "installed").is_file():
        run_logged([uv, "venv", "--allow-existing", "--python", config["python_version"], state / "venv"], log, env)
        run_logged([uv, "pip", "install", "--python", python, *config["packages"]], log, env)
        run_logged(["apt-get", "update", "-qq"], log, env)
        run_logged(["apt-get", "install", "-y", "-qq", "build-essential", "libfftw3-dev"], log, env)
        for repository, revision, destination in (
            ("akiyamalab/MEGADOCK", config["revision"], source),
            ("NVIDIA/cuda-samples", config["cuda_samples_revision"], samples),
        ):
            archive = state / (destination.name + ".tar.gz")
            run_logged(["curl", "--fail", "--location", "--retry", "3", "--output", archive,
                        f"https://codeload.github.com/{repository}/tar.gz/{revision}"], log, env)
            destination.mkdir(exist_ok=True)
            run_logged(["tar", "-xzf", archive, "--strip-components=1", "-C", destination], log, env)
        run_logged(["make", "-f", "Makefile.colab", f"SM_VERSIONS={architecture}",
                    f"CUDA_INSTALL_PATH={Path(nvcc).resolve().parent.parent}",
                    f"CUDA_SAMPLES_PATH={samples}", "FFTW_INSTALL_PATH=/usr",
                    "-j", str(os.cpu_count() or 1)], log, env, cwd=source)
        for binary in ("megadock-gpu", "decoygen"):
            if not (source / binary).is_file():
                raise RuntimeError(f"MEGADOCK build did not produce {binary}")
        run_logged([uv, "pip", "check", "--python", python], log, env)
        (state / "installed").touch()
    env["MEGADOCK_BIN"] = str(source)
    env["OMP_NUM_THREADS"] = str(os.cpu_count() or 1)
    save_environment(uv, python, root, env)
    run_logged(["nvidia-smi"], root / "runtime/environment.log", env)
    run_logged([nvcc, "--version"], root / "runtime/environment.log", env)
    (root / "config/docking_backend.json").write_text(json.dumps({
        "backend": "MEGADOCK", "revision": config["revision"],
        "cuda_samples_revision": config["cuda_samples_revision"],
        "gpu": name.strip(), "architecture": architecture,
        "cpu_threads": env["OMP_NUM_THREADS"],
    }, indent=2))
    return python, env
