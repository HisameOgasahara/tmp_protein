import csv
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

from runtime import FOUNDRY_REV, prepare_runtime, run_logged


EXAMPLE = Path(__file__).resolve().parents[2] / "inputs/pdl1_8aom"
VERSION = "0.2.0"
BACKBONES = 8
SEQUENCES_PER_BACKBONE = 2


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def ca_atoms(atoms, chain):
    return atoms[(atoms.chain_id == chain) & (atoms.atom_name == "CA") & ~atoms.hetero]


def sequence(atoms, chain):
    from Bio.SeqUtils import seq1

    return seq1("".join(ca_atoms(atoms, chain).res_name))


def save_cif(atoms, path):
    from atomworks.io.utils.io_utils import to_cif_file

    to_cif_file(atoms, path.with_suffix(""), file_type="cif")
    if not path.is_file():
        raise FileNotFoundError(path)


def generate_backbones(root):
    import numpy as np
    from rfd3.engine import RFD3InferenceConfig, RFD3InferenceEngine

    config = RFD3InferenceConfig(
        diffusion_batch_size=1, low_memory_mode=False, compile_model=False,
        compile_cuda_graphs=False, inference_kernel_backend="torch", seed=0,
    )
    model = RFD3InferenceEngine(**config)
    model._assign_override("trainer.precision", "32-true")
    output = model.run(inputs=str(root / "pdl1.json"), n_batches=BACKBONES)
    samples = [sample for batch in (output or {}).values() for sample in batch]
    if len(samples) != BACKBONES:
        raise RuntimeError(f"Expected {BACKBONES} RFD3 structures, got {len(samples)}.")
    target_sequence = sequence_from_example(root / "pdl1_cropped.pdb")
    backbones = []
    for index, sample in enumerate(samples, 1):
        atoms = sample.atom_array
        target, = [str(chain) for chain in np.unique(atoms.chain_id) if sequence(atoms, chain) == target_sequence]
        binder, = [str(chain) for chain in np.unique(atoms.chain_id) if chain != target]
        name = f"backbone_{index:02d}"
        path = f"structures/{name}.cif"
        save_cif(atoms, root / path)
        backbones.append({"id": name, "file": path, "target": target, "binder": binder})
    write_json(root / "backbones.json", backbones)


def sequence_from_example(path):
    from Bio.PDB import PDBParser
    from Bio.SeqUtils import seq1

    chain = PDBParser(QUIET=True).get_structure("8aom", path)[0]["B"]
    return seq1("".join(residue.resname for residue in chain if "CA" in residue))


def design_sequences(root):
    from mpnn.inference_engines.mpnn import MPNNInferenceEngine

    model = MPNNInferenceEngine(model_type="ligand_mpnn", is_legacy_weights=True,
                               write_structures=False, write_fasta=False, device="cuda")
    designs = []
    for backbone in read_json(root / "backbones.json"):
        chain = backbone["binder"]
        results = model.run(input_dicts=[{
            "structure_path": str(root / backbone["file"]), "name": backbone["id"],
            "designed_chains": [chain], "batch_size": SEQUENCES_PER_BACKBONE,
            "temperature": 0.1, "seed": 0, "remove_waters": True,
        }])
        for index, result in enumerate(results, 1):
            name = f"{backbone['id']}_seq{index:02d}"
            designs.append({"id": name, "sequence": sequence(result.atom_array, chain), "backbone": backbone})
    if len(designs) != BACKBONES * SEQUENCES_PER_BACKBONE:
        raise RuntimeError(f"Unexpected number of sequence designs: {len(designs)}.")
    write_json(root / "designs.json", designs)
    (root / "designs.fasta").write_text(
        "".join(f">{design['id']}\n{design['sequence']}\n" for design in designs), encoding="utf-8"
    )


def predict_complexes(root):
    import numpy as np
    from Bio.PDB import MMCIFParser
    from rf3.utils.inference import InferenceInput
    from rf3_runtime import create_model

    settings = {"num_steps": 50, "n_recycles": 3, "diffusion_batch_size": 1}
    model = create_model(settings, seed=0)
    target_sequence = sequence_from_example(root / "pdl1_cropped.pdb")
    parser = MMCIFParser(QUIET=True)
    rows = []
    for design in read_json(root / "designs.json"):
        name = design["id"]
        components = [{"chain_id": "A", "seq": target_sequence},
                      {"chain_id": "B", "seq": design["sequence"]}]
        spec = InferenceInput.from_json_dict({"name": name, "components": components})
        prediction, = model.run(inputs=spec, out_dir=None)[name]
        atoms = prediction.atom_array
        if sequence(atoms, "A") != target_sequence or sequence(atoms, "B") != design["sequence"]:
            raise ValueError(f"RF3 sequences do not match the input for {name}.")
        backbone = design["backbone"]
        reference = parser.get_structure(name, root / backbone["file"])[0]
        target = ca_atoms(atoms, "A").coord
        binder = ca_atoms(atoms, "B").coord
        reference_target, reference_binder = (
            np.array([residue["CA"].coord for residue in reference[backbone[chain]] if "CA" in residue])
            for chain in ("target", "binder")
        )
        left, _, right = np.linalg.svd((target - target.mean(0)).T @ (reference_target - reference_target.mean(0)))
        left[:, -1] *= np.linalg.det(left @ right)
        aligned_binder = (binder - target.mean(0)) @ left @ right + reference_target.mean(0)
        rmsd = float(np.sqrt(np.mean(np.sum((aligned_binder - reference_binder) ** 2, axis=1))))
        path = f"structures/{name}.cif"
        save_cif(atoms, root / path)
        confidence = prediction.summary_confidences
        rows.append({"id": name, "file": path, "binder_pose_rmsd_angstrom": rmsd,
                     "iptm": confidence.get("iptm"), "has_clash": bool(confidence.get("has_clash", False))})
        with (root / "complexes.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def run(revision):
    root = Path(mkdtemp(prefix="pdl1_8aom_", dir="/content"))
    print(root, flush=True)
    for folder in ("runtime", "structures"):
        (root / folder).mkdir()
    shutil.copyfile(EXAMPLE / "pdl1_cropped.pdb", root / "pdl1_cropped.pdb")
    inputs = read_json(EXAMPLE / "pdl1.json")
    for spec in inputs.values():
        spec["input"] = str(root / "pdl1_cropped.pdb")
    write_json(root / "pdl1.json", inputs)
    write_json(root / "source.json", {
        "version": VERSION, "revision": revision, "foundry_revision": FOUNDRY_REV,
        "source_pdb": "8AOM", "backbones": BACKBONES,
        "diffusion_batch_size": 1, "sequences_per_backbone": SEQUENCES_PER_BACKBONE,
    })
    python, env = prepare_runtime(root)
    durations = {}
    for stage in ("generate_backbones", "design_sequences", "predict_complexes"):
        print(stage, flush=True)
        start = perf_counter()
        run_logged([python, __file__, stage, root], root / f"runtime/{stage}.log", env)
        durations[stage] = perf_counter() - start
        write_json(root / "runtime/timings.json", durations)
    print(shutil.make_archive(str(root), "zip", root_dir=root), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        run(sys.argv[1])
    else:
        stages = {stage.__name__: stage for stage in (generate_backbones, design_sequences, predict_complexes)}
        stages[sys.argv[1]](Path(sys.argv[2]))
