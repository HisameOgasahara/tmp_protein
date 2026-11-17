import json
import math
from pathlib import Path

import numpy as np

from residues import AA


def build_chain_reference(lines, chain, sequence):
    from Bio.Align import PairwiseAligner

    residues = {}
    for line in lines:
        if not (line.startswith("ATOM") and line[21] == chain and line[16] in " A"):
            continue
        key = (int(line[22:26]), line[26])
        residue = residues.setdefault(key, {"name": line[17:20].strip(), "atoms": {}})
        residue["atoms"][line[12:16].strip()] = [
            float(line[start:start + 8]) for start in (30, 38, 46)
        ]
    observed = [residue for residue in residues.values() if "CA" in residue["atoms"]]
    observed_sequence = "".join(AA[residue["name"]] for residue in observed)
    aligner = PairwiseAligner(match_score=2, mismatch_score=-3,
                              open_gap_score=-5, extend_gap_score=-0.5)
    alignment = next(iter(aligner.align(sequence, observed_sequence)))
    atoms = []
    for i, j in zip(*alignment.indices):
        if i < 0 or j < 0:
            continue
        if sequence[i] != observed_sequence[j]:
            raise ValueError(f"Reference sequence mismatch in chain {chain} at {i}.")
        atoms.extend({"index": int(i), "atom": name, "coord": coord}
                     for name, coord in observed[j]["atoms"].items())
    if sum(atom["atom"] == "CA" for atom in atoms) < 3:
        raise ValueError(f"Insufficient reference coordinates for chain {chain}.")
    return {"sequence": sequence, "atoms": atoms}


def reference_ca(reference):
    atoms = sorted((atom for atom in reference["atoms"] if atom["atom"] == "CA"),
                   key=lambda atom: atom["index"])
    return ([atom["index"] for atom in atoms],
            np.array([atom["coord"] for atom in atoms], dtype=np.float64))


def make_reference(lines, target_chain, binder_chain, target_sequence, binder_sequence):
    return {
        "target": build_chain_reference(lines, target_chain, target_sequence),
        "binder": build_chain_reference(lines, binder_chain, binder_sequence),
    }


def apply_chain_templates(atoms, reference, mode, seed):
    rng = np.random.default_rng(seed)
    selected = np.zeros(len(atoms), dtype=bool)
    for chain, name in (("A", "target"), ("B", "binder")):
        if chain == "B" and mode == "target":
            continue
        chain_reference = reference[name]
        ca = atoms[(atoms.chain_id == chain) & (atoms.atom_name == "CA") & ~atoms.hetero]
        if "".join(AA[str(residue)] for residue in ca.res_name) != chain_reference["sequence"]:
            raise ValueError(f"Benchmark chain {chain} does not match its reference sequence.")
        positions = {int(res_id): index for index, res_id in enumerate(ca.res_id)}
        coords = np.array([atom["coord"] for atom in chain_reference["atoms"]])
        coords -= coords.mean(axis=0)
        rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        rotation[:, -1] *= np.linalg.det(rotation)
        coords = coords @ rotation
        # Independent coordinate frames remove the native relative orientation.
        coords += rng.normal(size=3) * np.linalg.norm(coords, axis=1).max()
        template = {(atom["index"], atom["atom"]): coord
                    for atom, coord in zip(chain_reference["atoms"], coords, strict=True)}
        for i in np.flatnonzero(atoms.chain_id == chain):
            key = (positions[int(atoms.res_id[i])], str(atoms.atom_name[i]))
            if key in template:
                atoms.coord[i] = template[key]
                selected[i] = True
        expected = sum(atom["atom"] == "CA" for atom in chain_reference["atoms"])
        actual = np.count_nonzero(selected & (atoms.chain_id == chain) & (atoms.atom_name == "CA"))
        if actual != expected:
            raise ValueError(f"Template lost observed C-alpha positions in chain {chain}.")
    atoms.occupancy[selected] = 1.0
    atoms.set_annotation("is_input_file_templated", selected)


def guard_template_pipeline(pipeline, mode):
    from atomworks.ml.utils.token import get_af3_token_center_masks

    def run(data):
        output = pipeline(data)
        atoms = output["atom_array"]
        centers = atoms[get_af3_token_center_masks(atoms)]
        mask = output["feats"]["has_distogram_condition"].detach().cpu().numpy()
        chains = centers.chain_id
        cross_chain = chains[:, None] != chains[None, :]
        if mask.shape != cross_chain.shape or np.any(mask & cross_chain):
            raise ValueError("RF3 benchmark leaked inter-chain template distances.")
        for chain in ("A", "B") if mode == "both" else ("A",):
            within = (chains[:, None] == chain) & (chains[None, :] == chain)
            np.fill_diagonal(within, False)
            if not np.any(mask & within):
                raise ValueError(f"RF3 benchmark lost the chain {chain} template.")
        if mode == "target" and np.any(mask[chains == "B"]):
            raise ValueError("Target-only benchmark unexpectedly conditioned the binder.")
        return output

    return run


def align_target(mobile, reference):
    mobile_center = mobile.mean(axis=0)
    reference_center = reference.mean(axis=0)
    u, _, vt = np.linalg.svd((mobile - mobile_center).T @ (reference - reference_center))
    rotation = u @ np.diag([1, 1, np.linalg.det(u @ vt)]) @ vt
    return rotation, mobile_center, reference_center


def measure_pose(target_ca, binder_ca, reference, contact_radius):
    target_indices, native_target = reference_ca(reference["target"])
    binder_indices, native_binder = reference_ca(reference["binder"])
    target = np.asarray(target_ca, dtype=np.float64)[target_indices]
    binder = np.asarray(binder_ca, dtype=np.float64)[binder_indices]
    if not (np.isfinite(target).all() and np.isfinite(binder).all()):
        raise ValueError("Unresolved benchmark C-alpha coordinates.")
    rotation, mobile_center, reference_center = align_target(target, native_target)
    aligned_target = (target - mobile_center) @ rotation + reference_center
    aligned_binder = (binder - mobile_center) @ rotation + reference_center
    binder_rotation, binder_center, native_binder_center = align_target(binder, native_binder)
    self_aligned_binder = (binder - binder_center) @ binder_rotation + native_binder_center
    native_contacts = np.linalg.norm(native_target[:, None] - native_binder[None, :], axis=2) <= contact_radius
    predicted_contacts = np.linalg.norm(target[:, None] - binder[None, :], axis=2) <= contact_radius
    native_sites = native_contacts.any(axis=1)
    predicted_sites = predicted_contacts.any(axis=1)
    if not native_contacts.any():
        raise ValueError("Reference complex has no contacts under the configured radius.")
    return {
        "target_ca_rmsd_angstrom": float(np.sqrt(np.mean(np.sum((aligned_target - native_target) ** 2, axis=1)))),
        "binder_ca_rmsd_after_target_alignment_angstrom": float(np.sqrt(np.mean(np.sum((aligned_binder - native_binder) ** 2, axis=1)))),
        "binder_self_rmsd_angstrom": float(np.sqrt(np.mean(np.sum((self_aligned_binder - native_binder) ** 2, axis=1)))),
        "benchmark_contact_jaccard": float(np.count_nonzero(native_sites & predicted_sites)
                                            / np.count_nonzero(native_sites | predicted_sites)),
        "native_ca_contact_pair_recovery": float(np.count_nonzero(native_contacts & predicted_contacts)
                                                  / np.count_nonzero(native_contacts)),
        "native_ca_contact_pairs": int(np.count_nonzero(native_contacts)),
        "target_reference_ca_count": len(target_indices),
        "binder_reference_ca_count": len(binder_indices),
    }


def recovery_criteria(settings=None):
    defaults = json.loads(Path(__file__).with_name("diagnostic_experiments.json").read_text())
    defaults.update(settings or {})
    return {key: defaults[key] for key in (
        "max_target_rmsd_angstrom", "max_binder_pose_rmsd_angstrom", "max_binder_self_rmsd_angstrom",
        "min_contact_jaccard", "min_native_contact_pair_recovery",
    )}


def pose_failure_reasons(row, settings=None):
    criteria = recovery_criteria(settings)
    reasons = []
    for metric, threshold, upper_bound in (
        ("target_ca_rmsd_angstrom", "max_target_rmsd_angstrom", True),
        ("binder_ca_rmsd_after_target_alignment_angstrom", "max_binder_pose_rmsd_angstrom", True),
        ("binder_self_rmsd_angstrom", "max_binder_self_rmsd_angstrom", True),
        ("benchmark_contact_jaccard", "min_contact_jaccard", False),
        ("native_ca_contact_pair_recovery", "min_native_contact_pair_recovery", False),
    ):
        value = row.get(metric)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            reasons.append(f"missing_or_nonfinite:{metric}")
        elif (upper_bound and value > criteria[threshold]) or (not upper_bound and value < criteria[threshold]):
            reasons.append(metric)
    if row.get("has_clash") is not False:
        reasons.append("clash_or_missing_clash_assessment")
    return reasons
