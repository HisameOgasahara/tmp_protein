"""Graft experimental target sidechains onto the published design backbone.

The public ``design.pdb`` carries only N, CA, C and O. Reading it with PyRosetta
rebuilds every missing sidechain from default rotamers, and the upstream AF2
featurizer puts those invented atoms straight into the target template and the
initial guess. That produced a clashing interface and moved the predicted binder
31 A away from the design. See docs/issues/2026-11-18-trka-target-sidechains.md.

This module copies the sidechains from an experimental structure of the same
target. Each residue is transformed on its own N/CA/C frame, so the design
backbone is preserved exactly and only sidechain atoms are added.
"""

import numpy as np
from Bio.PDB import PDBParser
from Bio.SeqUtils import seq1


BACKBONE = ("N", "CA", "C", "O")
FRAME = ("N", "CA", "C")


def _residues(path, chain):
    model = PDBParser(QUIET=True).get_structure(path.stem, path)[0]
    return [residue for residue in model[chain] if residue.id[0] == " " and "CA" in residue]


def _superpose(mobile, reference):
    """Rotation and translation placing `mobile` onto `reference` (no reflection)."""
    mobile_center, reference_center = mobile.mean(0), reference.mean(0)
    left, _, right = np.linalg.svd((mobile - mobile_center).T @ (reference - reference_center))
    left[:, -1] *= np.linalg.det(left @ right)
    rotation = left @ right
    return rotation, reference_center - mobile_center @ rotation


def graft(design_path, design_chain, reference_path, reference_chain):
    """Return PDB text for the target chain with experimental sidechains.

    Both chains must hold the same sequence in the same order. Only sidechain
    atoms are taken from the reference; backbone coordinates stay as designed.
    """
    design = _residues(design_path, design_chain)
    reference = _residues(reference_path, reference_chain)
    design_sequence = seq1("".join(residue.resname for residue in design))
    reference_sequence = seq1("".join(residue.resname for residue in reference))
    if design_sequence != reference_sequence:
        raise ValueError("Design target and reference target sequences differ.")

    lines = []
    serial = 0
    incomplete = []
    for residue, source in zip(design, reference, strict=True):
        if not all(atom in source for atom in FRAME):
            raise ValueError(f"Reference residue {source.id[1]} lacks a backbone frame.")
        rotation, translation = _superpose(
            np.array([source[atom].coord for atom in FRAME], dtype=float),
            np.array([residue[atom].coord for atom in FRAME], dtype=float),
        )
        atoms = [(atom, residue[atom].coord) for atom in BACKBONE if atom in residue]
        sidechain = [
            atom for atom in source
            if atom.id not in BACKBONE and atom.id != "OXT" and atom.element != "H"
        ]
        if not sidechain and residue.resname != "GLY":
            incomplete.append(residue.id[1])
        atoms += [(atom.id, atom.coord @ rotation + translation) for atom in sidechain]
        for name, point in atoms:
            serial += 1
            label = f" {name:<3s}" if len(name) < 4 else name
            lines.append(
                f"ATOM  {serial:5d} {label}{residue.resname:>4s} {design_chain}"
                f"{residue.id[1]:4d}    {point[0]:8.3f}{point[1]:8.3f}{point[2]:8.3f}"
                f"  1.00  0.00          {name[0]:>2s}"
            )
    if incomplete:
        raise ValueError(f"Reference residues without sidechain atoms: {incomplete}")
    return "\n".join(lines) + "\nTER\n"


def design_with_target_sidechains(inputs, binder_chain="A", target_chain="B"):
    """Return PDB text for the full complex: design binder plus grafted target."""
    design_path = inputs / "design.pdb"
    binder = [
        line for line in design_path.read_text().splitlines()
        if line.startswith("ATOM") and line[21] == binder_chain
    ]
    target = graft(design_path, target_chain, inputs / "target_1www_chainX.pdb", "X")
    return "\n".join(binder) + "\nTER\n" + target + "END\n"
