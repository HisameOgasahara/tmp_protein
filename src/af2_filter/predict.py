import json
import shutil
import subprocess
import sys
from pathlib import Path

from Bio.PDB import PDBParser
import numpy as np
import pyrosetta
from pyrosetta.toolbox.mutants import mutate_residue

from compare import pose_rmsd, read_inputs
from target_sidechains import design_with_target_sidechains


def predict(root, upstream):
    inputs = root / "inputs"
    target, binder = read_inputs(inputs)
    pyrosetta.init("-mute all")
    # design.pdb is backbone-only, so the target sidechains come from an
    # experimental structure instead of being rebuilt from default rotamers.
    grafted = root / "design_with_target_sidechains.pdb"
    grafted.write_text(design_with_target_sidechains(inputs))
    pose = pyrosetta.pose_from_pdb(str(grafted))
    if pose.chain_sequence(2) != target or pose.chain_end(1) != len(binder):
        raise ValueError("Expected binder in chain 1 followed by TrkA in chain 2.")
    for index, residue in enumerate(binder, 1):
        mutate_residue(pose, index, residue)
    if pose.sequence() != binder + target:
        raise ValueError("Prepared sequence does not match the published sequences.")
    directory = root / "prepared"
    directory.mkdir()
    reference = directory / "TrkA_88.pdb"
    pose.dump_pdb(str(reference))
    # Sequence substitution must preserve every backbone coordinate.
    parser = PDBParser(QUIET=True)
    original = parser.get_structure("design", inputs / "design.pdb")[0]
    prepared = parser.get_structure("prepared", reference)[0]
    for chain in original:
        for before, after in zip(original[chain.id], prepared[chain.id], strict=True):
            for atom in ("N", "CA", "C", "O"):
                if not np.allclose(before[atom].coord, after[atom].coord, atol=0.002):
                    raise ValueError("Sequence preparation changed the design backbone.")
    # The target template and the initial guess carry sidechains, so a target
    # left with backbone atoms only would silently poison the prediction.
    bare = [
        residue.id[1] for residue in prepared["B"]
        if residue.resname != "GLY"
        and not any(atom.id not in ("N", "CA", "C", "O") for atom in residue)
    ]
    if bare:
        raise ValueError(f"Target residues are missing sidechains: {bare}")
    output = root / "original_af2_output"
    subprocess.run([
        sys.executable, str(upstream / "af2_initial_guess/predict.py"),
        "-pdbdir", str(directory), "-outpdbdir", str(output),
        "-scorefilename", str(root / "original_af2_scores.sc"),
        "-checkpoint_name", str(root / "original_af2.checkpoint"),
        "-recycle", "3", "-debug",
    ], check=True, cwd=root)
    prediction = root / "af2_reprediction.pdb"
    shutil.copyfile(output / "TrkA_88_af2pred.pdb", prediction)
    structure = parser.get_structure("prediction", prediction)[0]
    plddt = [residue["CA"].bfactor for chain in structure for residue in chain if "CA" in residue]
    score_lines = (root / "original_af2_scores.sc").read_text().splitlines()
    header = next(line.split()[1:] for line in score_lines if line.startswith("SCORE:") and "description" in line)
    values = next(line.split()[1:] for line in reversed(score_lines) if line.startswith("SCORE:") and "description" not in line)
    scores = dict(zip(header, values, strict=True))
    report = {
        "paper_pose_rmsd_angstrom": 1.4,
        "published_af2_vs_design_angstrom": pose_rmsd(inputs / "published_af2.pdb", reference, target, binder),
        "reprediction_vs_design_angstrom": pose_rmsd(reference, prediction, target, binder),
        "reprediction_vs_published_af2_angstrom": pose_rmsd(inputs / "published_af2.pdb", prediction, target, binder),
        "plddt": float(np.mean(plddt)), "original_af2_scores": scores,
    }
    (root / "comparison.json").write_text(json.dumps(report, indent=2) + chr(10))


if __name__ == "__main__":
    predict(Path(sys.argv[1]), Path(sys.argv[2]))
