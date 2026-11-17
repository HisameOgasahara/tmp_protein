import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

from benchmark import align_target, build_chain_reference, reference_ca
from run import ensure_uv, run_logged, save_environment


def prepare_nanobody(root, settings):
    config = settings["nanobody"]
    state = Path("/content") / f"gfp_nanobody_{settings['version']}"
    state.mkdir(exist_ok=True)
    weights = state / "weights"
    weights.mkdir(exist_ok=True)
    env = dict(os.environ, DESIGN_RUN=str(root), NANOBODY_WEIGHTS=str(weights), PYTHONUNBUFFERED="1")
    log = root / "runtime/nanobody_installation.log"
    uv = ensure_uv(state, log, env)
    python = state / "venv/bin/python"
    if not (state / "installed").is_file():
        run_logged([uv, "venv", "--allow-existing", "--python", config["python_version"], state / "venv"], log, env)
        run_logged(["apt-get", "update", "-qq"], log, env)
        run_logged(["apt-get", "install", "-y", "-qq", "hmmer"], log, env)
        run_logged([uv, "pip", "install", "--python", python, "--index-url", config["torch_index"],
                    config["torch_package"]], log, env)
        run_logged([uv, "pip", "install", "--python", python, *config["packages"]], log, env)
        run_logged([python, "-c", "from ImmuneBuilder import NanoBodyBuilder2; import anarci, pdbfixer, openmm"], log, env)
        run_logged([uv, "pip", "check", "--python", python], log, env)
        (state / "installed").touch()
    # Keep each environment's inventory separate in the shared experiment output.
    inventory = root / "runtime/nanobody_environment"
    (inventory / "runtime").mkdir(parents=True, exist_ok=True)
    save_environment(uv, python, inventory, env)
    return python, env


def evaluate_fold(predicted, native):
    indices, target = reference_ca(native)
    predicted_ca = {atom["index"]: atom["coord"] for atom in predicted["atoms"] if atom["atom"] == "CA"}
    if not set(indices).issubset(predicted_ca):
        raise ValueError("NanoBodyBuilder2 output is missing evaluated reference residues.")
    mobile = np.asarray([predicted_ca[index] for index in indices], dtype=float)
    if not np.isfinite(mobile).all():
        raise ValueError("NanoBodyBuilder2 output has nonfinite coordinates.")
    rotation, center, native_center = align_target(mobile, target)
    return float(np.sqrt(np.mean(np.sum(((mobile - center) @ rotation + native_center - target) ** 2, axis=1))))


def predict_nanobody(root):
    import torch
    from ImmuneBuilder import NanoBodyBuilder2
    from ImmuneBuilder.refine import refine
    from common import measure

    root = Path(root)
    settings = json.loads((root / "config/diagnostics.json").read_text())
    native = json.loads((root / "config/reference_enhancer.json").read_text())
    if not torch.cuda.is_available():
        raise RuntimeError("NanoBodyBuilder2 requires the selected Colab GPU runtime.")
    weights = Path(os.environ["NANOBODY_WEIGHTS"])
    model = NanoBodyBuilder2(weights_dir=str(weights), numbering_scheme="raw",
                            model_ids=settings["nanobody"]["model_ids"])
    output = root / "structures/enhancer_nanobody.pdb"
    with measure("NanoBodyBuilder2", "monomer", "enhancer_nanobody"):
        prediction = model.predict({"H": native["binder"]["sequence"]})
        for index in prediction.ranking:
            unrefined = root / f"structures/enhancer_nanobody_model{index}_unrefined.pdb"
            prediction.save_single_unrefined(str(unrefined), index=index)
            if refine(str(unrefined), str(output), n_threads=os.cpu_count() or 1):
                selected_index = index
                break
        else:
            raise RuntimeError("NanoBodyBuilder2 structural refinement failed for every ranked model.")
    predicted = build_chain_reference(output.read_text().splitlines(), "H", native["binder"]["sequence"])
    rmsd = evaluate_fold(predicted, native["binder"])
    (root / "config/predicted_binder.json").write_text(json.dumps(predicted))
    report = {"stage": "monomer", "model": "NanoBodyBuilder2", "binder_self_rmsd_angstrom": rmsd,
              "fold_criterion_passed": rmsd <= settings["max_binder_self_rmsd_angstrom"],
              "file": "structures/enhancer_nanobody.pdb", "selected_model_index": selected_index,
              "model_ranking": prediction.ranking, "refinement_succeeded": True,
              "selection": "ensemble uncertainty ranking followed by successful refinement",
              "weights_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in weights.iterdir() if path.is_file()}}
    (root / "metrics/enhancer_monomer.json").write_text(json.dumps(report, indent=2))
    print(f"NanoBodyBuilder2 fold RMSD: {rmsd:.3f} angstrom", flush=True)


if __name__ == "__main__":
    predict_nanobody(sys.argv[1])
