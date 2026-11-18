import numpy as np
from Bio.PDB import PDBParser
from Bio.SeqUtils import seq1


def read_chains(path):
    model = PDBParser(QUIET=True).get_structure(path.stem, path)[0]
    chains = {}
    for chain in model:
        residues = [residue for residue in chain if "CA" in residue]
        sequence = seq1("".join(residue.resname for residue in residues))
        chains[sequence] = np.array([residue["CA"].coord for residue in residues], dtype=float)
    return chains


def read_inputs(folder):
    binder = "".join((folder / "binder.fasta").read_text().splitlines()[1:])
    chains = read_chains(folder / "published_af2.pdb")
    if binder not in chains:
        raise ValueError("Published binder sequence does not match the published AF2 structure.")
    target, = [sequence for sequence in chains if sequence != binder]
    return target, binder


def pose_rmsd(reference_path, prediction_path, target_sequence, binder_sequence):
    reference, predicted = read_chains(reference_path), read_chains(prediction_path)
    target, mobile_target = reference[target_sequence], predicted[target_sequence]
    binder, mobile_binder = reference[binder_sequence], predicted[binder_sequence]
    left, _, right = np.linalg.svd(
        (mobile_target - mobile_target.mean(0)).T @ (target - target.mean(0))
    )
    left[:, -1] *= np.linalg.det(left @ right)
    aligned = (mobile_binder - mobile_target.mean(0)) @ left @ right + target.mean(0)
    return float(np.sqrt(np.mean(np.sum((aligned - binder) ** 2, axis=1))))


def design_reference(design_path, binder_sequence):
    # Raw RFdiffusion models use placeholder residues for the generated binder.
    lines = design_path.read_text().splitlines()
    from Bio.SeqUtils import seq3

    residues = {}
    output = []
    for line in lines:
        if line.startswith("ATOM") and line[21] == "A":
            key = line[22:27]
            if key not in residues:
                residues[key] = len(residues)
            index = residues[key]
            line = line[:17] + seq3(binder_sequence[index]).upper() + line[20:]
        output.append(line)
    if len(residues) != len(binder_sequence):
        raise ValueError("Design backbone and published binder have different lengths.")
    return "\n".join(output) + "\n"
