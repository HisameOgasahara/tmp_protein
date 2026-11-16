import csv
import json
import math
import re
import sys
from urllib.request import urlopen

import numpy as np

from common import AA, ROOT, measure, save_cif, write_csv, write_json


TARGET_PDB = "3G9A"
TARGET_CHAIN = "A"
CONTACT_RADIUS = 8.0
BACKBONES = 2
SEQUENCES_PER_BACKBONE = 2
BINDER_LENGTH = 55


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def fetch(url):
    with urlopen(url, timeout=45) as response:
        return response.read().decode("utf-8")


def pdb_sequence(pdb, entity):
    fasta = fetch(f"https://www.rcsb.org/fasta/entry/{pdb}/display")
    for record in fasta.split(">")[1:]:
        header, *sequence = record.splitlines()
        if header.partition("|")[0] == f"{pdb}_{entity}":
            return "".join(sequence)
    raise ValueError(f"No FASTA entry for {pdb} entity {entity}.")


def ca_array(atoms, chain):
    return atoms[(atoms.chain_id == chain) & (atoms.atom_name == "CA") & ~atoms.hetero]


def atom_sequence(atoms, chain):
    return "".join(AA[str(residue)] for residue in ca_array(atoms, chain).res_name)


def points_from_pdb(lines, chain):
    return {int(line[22:26]): [float(line[start:start + 8]) for start in (30, 38, 46)]
            for line in lines if line.startswith("ATOM") and line[21] == chain
            and line[12:16].strip() == "CA" and line[16] in " A"}


def prepare():
    from Bio.Align import PairwiseAligner

    crystal = fetch(f"https://files.rcsb.org/download/{TARGET_PDB}.pdb").splitlines()
    target_points = points_from_pdb(crystal, TARGET_CHAIN)
    control_points = points_from_pdb(crystal, "B")
    positions = np.array(sorted(target_points))
    distances = np.linalg.norm(np.array([target_points[i] for i in positions])[:, None, :]
                               - np.array(list(control_points.values()))[None, :, :], axis=2)
    closest = positions[np.argsort(distances.min(axis=1))[:3]]
    spans = np.split(positions, np.where(np.diff(positions) != 1)[0] + 1)
    contig = ",".join(f"{TARGET_CHAIN}{span[0]}-{span[-1]}" for span in spans)
    target_path = ROOT / "structures/target.pdb"
    target_lines = [line for line in crystal if line.startswith("ATOM")
                    and line[21] == TARGET_CHAIN and line[16] in " A"]
    target_path.write_text("\n".join([*target_lines, "END", ""]))
    write_json(ROOT / "config/rfd3.json", {"gfp": {
        "input": str(target_path), "dialect": 2, "infer_ori_strategy": "hotspots",
        "contig": f"{BINDER_LENGTH}-{BINDER_LENGTH},/0,{contig}",
        "select_hotspots": {f"{TARGET_CHAIN}{index}": "CA" for index in closest},
        "is_non_loopy": True,
    }})

    target_sequence = pdb_sequence(TARGET_PDB, "1")
    if target_sequence.count("X") != 1 or "TTFXVQ" not in target_sequence:
        raise ValueError("Expected one collapsed GFP chromophore at TTFXVQ.")
    chromophore_index = target_sequence.index("X")
    target_sequence = target_sequence.replace("X", "SYG")
    ca_residues = {int(line[22:26]): AA[line[17:20].strip()]
                   for line in target_lines if line[12:16].strip() == "CA"}
    observed = "".join(ca_residues[index] for index in positions)
    aligner = PairwiseAligner(match_score=2, mismatch_score=-3,
                              open_gap_score=-5, extend_gap_score=-0.5)
    alignment = next(iter(aligner.align(target_sequence, observed)))
    mapped_positions = {int(positions[j]): int(i)
                        for i, j in zip(*alignment.indices) if i >= 0 and j >= 0}
    write_json(ROOT / "config/target.json", {
        "sequence": target_sequence, "pdb": TARGET_PDB, "chain": TARGET_CHAIN,
        "chromophore_indices": list(range(chromophore_index, chromophore_index + 3)),
        "hotspots": closest.tolist(),
        "hotspot_indices": [mapped_positions[int(index)] for index in closest],
    })

    with (ROOT / "config/assays.csv").open(encoding="utf-8-sig", newline="") as handle:
        assays = list(csv.DictReader(handle))
    ids = set()
    sequences = set()
    assay_ids = {row["assay"].strip() for row in assays}
    if len(assays) < 2 or len(assay_ids) != 1 or "" in assay_ids:
        raise ValueError("Supply at least two measured controls from one assay.")
    for row in assays:
        ident = row["id"].strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", ident) or ident in ids:
            raise ValueError(f"Invalid or duplicate control ID: {ident!r}")
        ids.add(ident)
        row["id"] = "control_" + ident
        ratio = float(row["ratio"])
        if not math.isfinite(ratio) or ratio <= 0 or not row["group"].strip() or not row["source"].strip():
            raise ValueError(f"Invalid ratio, group or source for control {ident!r}.")
        seq = (row.get("sequence") or "").strip().upper()
        if not seq:
            seq = pdb_sequence(row["pdb"].upper(), row["entity"]).removesuffix("HHHHHH")
        if not seq or set(seq) - set(AA.values()) or seq in sequences:
            raise ValueError(f"Invalid or duplicate control sequence: {ident!r}")
        sequences.add(seq)
        row.update(sequence=seq, ratio=ratio, group=row["group"].strip())
    write_json(ROOT / "config/controls.json", assays)


def generate_backbones():
    from rfd3.engine import RFD3InferenceConfig, RFD3InferenceEngine

    with measure("RFD3", "generation", "gfp"):
        config = RFD3InferenceConfig(
            diffusion_batch_size=1, low_memory_mode=True, compile_model=False,
            compile_cuda_graphs=False, inference_kernel_backend="torch", seed=0,
            inference_sampler={"num_timesteps": 200, "step_scale": 3.0, "gamma_0": 0.2},
        )
        model = RFD3InferenceEngine(**config)
        model._assign_override("trainer.precision", "32-true")
        output = model.run(inputs=str(ROOT / "config/rfd3.json"), n_batches=BACKBONES)
    samples = [sample for batch in (output or {}).values() for sample in batch]
    if len(samples) != BACKBONES:
        raise RuntimeError(f"Expected {BACKBONES} RFD3 structures, got {len(samples)}.")
    rows = []
    for index, sample in enumerate(samples, 1):
        atoms = sample.atom_array
        chains = np.unique(atoms.chain_id)
        binders = [str(chain) for chain in chains if len(ca_array(atoms, chain)) == BINDER_LENGTH]
        if len(binders) != 1:
            raise RuntimeError(f"Could not identify the designed chain in sample {index}.")
        ident = f"backbone_{index:02d}"
        path = f"structures/{ident}.cif"
        save_cif(atoms, ROOT / path)
        rows.append({"id": ident, "file": path, "binder_chain": binders[0]})
    write_json(ROOT / "config/backbones.json", rows)


def design_sequences():
    from mpnn.inference_engines.mpnn import MPNNInferenceEngine

    model = MPNNInferenceEngine(model_type="ligand_mpnn", is_legacy_weights=True,
                               write_structures=False, write_fasta=False, device="cuda")
    designs = []
    for backbone in read_json("config/backbones.json"):
        ident = backbone["id"]
        chain = backbone["binder_chain"]
        with measure("LigandMPNN", "design", ident):
            results = model.run(input_dicts=[{
                "structure_path": str(ROOT / backbone["file"]), "name": ident,
                "designed_chains": [chain], "batch_size": SEQUENCES_PER_BACKBONE,
                "temperature": 0.1, "seed": 0, "remove_waters": True,
            }])
        for index, result in enumerate(results, 1):
            seq = atom_sequence(result.atom_array, chain)
            if len(seq) != BINDER_LENGTH:
                raise RuntimeError(f"Unexpected binder length for {ident}.")
            designs.append({"id": f"{ident}_seq{index:02d}", "sequence": seq,
                            "backbone": backbone["file"]})
    write_json(ROOT / "config/designs.json", designs)
    (ROOT / "structures/designs.fasta").write_text("".join(
        f">{row['id']}\n{row['sequence']}\n" for row in designs))


def interface_features(atoms, target):
    target_ca = ca_array(atoms, "A")
    binder_ca = ca_array(atoms, "B")
    if not len(target_ca) or not len(binder_ca):
        raise ValueError("Expected two complex chains with C-alpha coordinates.")
    if atom_sequence(atoms, "A") != target["sequence"]:
        raise ValueError("RF3 GFP chain does not match the target sequence.")
    distances = np.linalg.norm(target_ca.coord[:, None] - binder_ca.coord[None, :], axis=2)
    contacts = distances <= CONTACT_RADIUS
    return {
        "hotspot_contact_fraction": float(np.mean(contacts[target["hotspot_indices"]].any(axis=1))),
        "target_contact_fraction": float(np.mean(contacts.any(axis=1))),
        "binder_contact_fraction": float(np.mean(contacts.any(axis=0))),
        "chromophore_ca_distance": float(distances[target["chromophore_indices"]].min()),
    }


def predict_complexes():
    from rf3.inference_engines.rf3 import RF3InferenceEngine
    from rf3.model.layers.af3_diffusion_transformer import AttentionPairBiasDiffusion
    from rf3.model.layers.pairformer_layers import AttentionPairBiasPairformerDeepspeed
    from rf3.utils.inference import InferenceInput

    model = RF3InferenceEngine(
        ckpt_path="rf3", num_steps=50, n_recycles=3, diffusion_batch_size=1,
        triangle_attention_backend="vanilla", dense_attention_backend="vanilla",
        early_stopping_plddt_threshold=None, trainer_overrides={"precision": "32-true"}, seed=0,
    )
    model.initialize()
    layers = [layer for layer in model.trainer.state["model"].modules()
              if isinstance(layer, (AttentionPairBiasPairformerDeepspeed, AttentionPairBiasDiffusion))]
    if not layers or any(layer.use_deepspeed_evo for layer in layers):
        raise RuntimeError("Expected native RF3 attention layers on T4.")
    for layer in layers:
        layer.force_bfloat16 = False

    target = read_json("config/target.json")
    rows = []
    for item in read_json("config/designs.json") + read_json("config/controls.json"):
        ident = item["id"]
        payload = {"name": ident, "components": [
            {"chain_id": "A", "seq": target["sequence"]},
            {"chain_id": "B", "seq": item["sequence"]},
        ]}
        with measure("RF3", "complex", ident):
            predictions = model.run(inputs=InferenceInput.from_json_dict(payload), out_dir=None)
        prediction, = predictions[ident]
        if atom_sequence(prediction.atom_array, "B") != item["sequence"]:
            raise ValueError(f"RF3 binder chain does not match {ident}.")
        path = f"structures/{ident}.cif"
        save_cif(prediction.atom_array, ROOT / path)
        summary = prediction.summary_confidences
        rows.append({"id": ident, "file": path, "iptm": summary.get("iptm"),
                     "ranking_score": summary.get("ranking_score"),
                     **interface_features(prediction.atom_array, target)})
        write_csv(ROOT / "metrics/complexes.csv", rows)
    write_json(ROOT / "metrics/complexes.json", rows)


def predict_fluorescence():
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    features = ("target_contact_fraction", "binder_contact_fraction", "chromophore_ca_distance")
    complexes = {row["id"]: row for row in read_json("metrics/complexes.json")}
    controls = read_json("config/controls.json")
    designs = read_json("config/designs.json")
    train = np.array([[complexes[row["id"]][key] for key in features] for row in controls])
    target = np.log2([row["ratio"] for row in controls])
    groups = [row["group"] for row in controls]
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    report = {
        "n_controls": len(controls), "n_groups": len(set(groups)),
        "assay": controls[0]["assay"], "feature_names": features,
        "label": "log2(GFP with binder fluorescence / reference fluorescence)",
        "scope": "Exploratory extrapolation from measured controls; validate new designs experimentally.",
    }
    if len(set(groups)) >= 3:
        held_out = cross_val_predict(model, train, target, groups=groups, cv=LeaveOneGroupOut())
        report["held_out_mae_log2"] = float(np.mean(np.abs(held_out - target)))
        report["no_effect_mae_log2"] = float(np.mean(np.abs(target)))
    else:
        report["validation"] = "Too few independent control groups for meaningful evaluation."
    model.fit(train, target)
    candidates = [[complexes[row["id"]][key] for key in features] for row in designs]
    results = []
    for design, score in zip(designs, model.predict(candidates), strict=True):
        result = complexes[design["id"]]
        results.append({"id": design["id"], "sequence": design["sequence"], "complex": result["file"],
                        "iptm": result["iptm"], "predicted_log2_ratio": float(score),
                        "predicted_fluorescence_ratio": float(2 ** score)})
    write_json(ROOT / "metrics/fluorescence_model.json", report)
    write_csv(ROOT / "metrics/fluorescence_predictions.csv", results)


if __name__ == "__main__":
    handlers = {"prepare": prepare, "backbones": generate_backbones, "sequences": design_sequences,
                "complexes": predict_complexes, "fluorescence": predict_fluorescence}
    handlers[sys.argv[1]]()
