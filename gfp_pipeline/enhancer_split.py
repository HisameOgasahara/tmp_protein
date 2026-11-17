import copy
import random
import sys

import numpy as np
import torch

from benchmark import apply_chain_templates, guard_template_pipeline, measure_pose, pose_failure_reasons, recovery_criteria
from common import ROOT, measure, save_cif, write_csv, write_json
from rf3_runtime import create_model
from stages import atom_sequence, ca_array, read_json


def reset_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def run_seed(seed):
    from rf3.utils.inference import InferenceInput

    settings = read_json("config/diagnostics.json")
    native = read_json("config/reference_enhancer.json")
    model = create_model(settings["rf3"], seed)
    sequence = native["binder"]["sequence"]
    predicted = read_json("config/predicted_binder.json")
    monomer_rmsd = read_json("metrics/enhancer_monomer.json")["binder_self_rmsd_angstrom"]
    rows = []
    # Preserve the same complex RNG seed for both structure conditions.
    model.pipeline = guard_template_pipeline(model.pipeline, "both")
    for label, binder in (("predicted_binder", predicted), ("crystal_binder", native["binder"])):
        reset_seed(seed)
        ident = f"enhancer_{label}_seed{seed}"
        input_reference = copy.deepcopy(native)
        input_reference["binder"] = binder
        with measure("RF3", "complex", ident):
            spec = InferenceInput.from_json_dict({"name": ident, "components": [
                {"chain_id": "A", "seq": native["target"]["sequence"]},
                {"chain_id": "B", "seq": sequence},
            ]})
            apply_chain_templates(spec.atom_array, input_reference, "both", seed)
            prediction, = model.run(inputs=spec, out_dir=None)[ident]
        if atom_sequence(prediction.atom_array, "A") != native["target"]["sequence"] or atom_sequence(prediction.atom_array, "B") != sequence:
            raise ValueError("Complex sequence changed during prediction.")
        save_cif(prediction.atom_array, ROOT / f"structures/{ident}.cif")
        confidence = prediction.summary_confidences
        rows.append({"stage": label, "seed": seed, "file": f"structures/{ident}.cif",
                     "input_monomer_rmsd_angstrom": monomer_rmsd if label == "predicted_binder" else 0.0,
                     "iptm": confidence.get("iptm"), "has_clash": bool(confidence["has_clash"]),
                     **measure_pose(ca_array(prediction.atom_array, "A").coord,
                                    ca_array(prediction.atom_array, "B").coord,
                                    native, settings["contact_radius_angstrom"])})
    write_json(ROOT / f"metrics/enhancer_seed{seed}.json", rows)


def summarize():
    settings = read_json("config/diagnostics.json")
    rows = [read_json("metrics/enhancer_monomer.json")]
    rows.extend(row for seed in settings["seeds"] for row in read_json(f"metrics/enhancer_seed{seed}.json"))
    for row in rows:
        if row["stage"] != "monomer":
            row["pose_failure_reasons"] = pose_failure_reasons(row, settings)
            row["contact_criterion_passed"] = not row["pose_failure_reasons"]
    write_csv(ROOT / "metrics/enhancer_split.csv", rows)
    write_json(ROOT / "metrics/diagnostic_summary.json", {"experiment": "enhancer_split", "recovery_criteria": recovery_criteria(settings), "rows": rows})


if __name__ == "__main__":
    if sys.argv[1] == "summary":
        summarize()
    else:
        run_seed(int(sys.argv[1]))
