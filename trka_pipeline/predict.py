import json
import sys
from pathlib import Path

import jax
import numpy as np
from colabdesign.af import mk_af_model

from compare import design_reference, pose_rmsd, read_inputs


def predict(root, parameter_directory):
    inputs = root / "inputs"
    target, binder = read_inputs(inputs)
    reference = root / "design_with_published_sequence.pdb"
    reference.write_text(design_reference(inputs, binder))
    if not any(device.platform == "gpu" for device in jax.devices()):
        raise RuntimeError("AF2 requires a connected GPU runtime.")
    model = mk_af_model(
        protocol="binder", initial_guess=True, use_multimer=False,
        model_names=["model_1_ptm"], data_dir=str(parameter_directory),
    )
    model.prep_inputs(
        str(reference), target_chain="B", binder_chain="A",
        rm_binder=True, rm_binder_seq=True, rm_binder_sc=True, seed=0,
    )
    model.predict(seq=binder, num_recycles=3, verbose=False)
    prediction = root / "af2_reprediction.pdb"
    model.save_current_pdb(str(prediction))
    np.savez_compressed(root / "af2_confidence.npz", plddt=model.aux["plddt"], pae=model.aux["pae"])
    log = model.aux["log"]
    report = {
        "paper_pose_rmsd_angstrom": 1.4,
        "published_af2_vs_design_angstrom": pose_rmsd(
            reference, inputs / "published_af2.pdb", target, binder
        ),
        "reprediction_vs_design_angstrom": pose_rmsd(reference, prediction, target, binder),
        "reprediction_vs_published_af2_angstrom": pose_rmsd(
            inputs / "published_af2.pdb", prediction, target, binder
        ),
        "plddt": float(log["plddt"]) * 100,
        "interface_pae_angstrom": float(log["i_pae"]) * 31,
        "iptm": float(log["i_ptm"]),
    }
    (root / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    predict(Path(sys.argv[1]), Path(sys.argv[2]))
