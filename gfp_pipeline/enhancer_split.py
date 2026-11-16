import copy
import random
import sys

import numpy as np
import torch

from benchmark import align_target, apply_chain_templates, guard_template_pipeline, measure_pose, reference_ca
from common import AA, ROOT, measure, save_cif, write_csv, write_json
from rf3_runtime import create_model
from stages import atom_sequence, ca_array, read_json


def reset_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def self_rmsd(atoms, chain, reference):
    indices, native = reference_ca(reference)
    mobile = ca_array(atoms, chain).coord[indices].astype(float)
    if not np.isfinite(mobile).all():
        raise ValueError("Unresolved monomer coordinates.")
    rotation, center, native_center = align_target(mobile, native)
    return float(np.sqrt(np.mean(np.sum(((mobile - center) @ rotation + native_center - native) ** 2, axis=1))))


def predicted_reference(atoms, sequence):
    ca = ca_array(atoms, "A")
    if atom_sequence(atoms, "A") != sequence:
        raise ValueError("Monomer sequence does not match enhancer.")
    positions = {int(res_id): index for index, res_id in enumerate(ca.res_id)}
    rows = [{"index": positions[int(atom.res_id)], "atom": str(atom.atom_name),
             "coord": atom.coord.tolist()} for atom in atoms if atom.chain_id == "A" and not atom.hetero]
    if not all(np.isfinite(atom["coord"]).all() for atom in rows):
        raise ValueError("Monomer contains unresolved atoms.")
    return {"sequence": sequence, "atoms": rows}


def run_seed(seed):
    from rf3.utils.inference import InferenceInput

    settings = read_json("config/diagnostics.json")
    native = read_json("config/reference_enhancer.json")
    model = create_model(settings["rf3"], seed)
    sequence = native["binder"]["sequence"]
    ident = f"enhancer_monomer_seed{seed}"
    reset_seed(seed)
    with measure("RF3", "monomer", ident):
        spec = InferenceInput.from_json_dict({"name": ident, "components": [{"chain_id": "A", "seq": sequence}]})
        monomer, = model.run(inputs=spec, out_dir=None)[ident]
    predicted = predicted_reference(monomer.atom_array, sequence)
    save_cif(monomer.atom_array, ROOT / f"structures/{ident}.cif")
    write_json(ROOT / f"config/predicted_binder_seed{seed}.json", predicted)
    monomer_rmsd = self_rmsd(monomer.atom_array, "A", native["binder"])
    rows = [{"stage": "monomer", "seed": seed, "binder_self_rmsd_angstrom": monomer_rmsd,
             "file": f"structures/{ident}.cif"}]
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
                     "binder_self_rmsd_angstrom": self_rmsd(prediction.atom_array, "B", native["binder"]),
                     "iptm": confidence.get("iptm"), "has_clash": bool(confidence["has_clash"]),
                     **measure_pose(ca_array(prediction.atom_array, "A").coord,
                                    ca_array(prediction.atom_array, "B").coord,
                                    native, settings["contact_radius_angstrom"])})
    write_json(ROOT / f"metrics/enhancer_seed{seed}.json", rows)


def summarize():
    settings = read_json("config/diagnostics.json")
    rows = [row for seed in settings["seeds"] for row in read_json(f"metrics/enhancer_seed{seed}.json")]
    for row in rows:
        if row["stage"] != "monomer":
            row["contact_criterion_passed"] = (
                row["target_ca_rmsd_angstrom"] <= settings["max_target_rmsd_angstrom"]
                and row["benchmark_contact_jaccard"] >= settings["min_contact_jaccard"]
                and not row["has_clash"])
    write_csv(ROOT / "metrics/enhancer_split.csv", rows)
    write_json(ROOT / "metrics/diagnostic_summary.json", {"experiment": "enhancer_split", "rows": rows})


if __name__ == "__main__":
    if sys.argv[1] == "summary":
        summarize()
    else:
        run_seed(int(sys.argv[1]))
