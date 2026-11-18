"""Design new TrkA binders: RFdiffusion3 backbones, then MPNN sequences.

Runs inside the foundry environment. Scoring happens separately in the AF2
environment, so this stage only produces structures, sequences and a manifest.

The target is the same TrkA domain the published designs bind, in the same
coordinate frame, with sidechains grafted from the crystal structure. Hotspots
are the three most deeply buried hydrophobic contacts of the published binder
TrkA_88 (Met108 3.21 A, Phe115 3.80 A, Leu145 3.15 A), so the campaign aims at
a known-targetable epitope rather than an arbitrary patch.
"""

import json
import sys
from pathlib import Path


SOURCE = Path(__file__).resolve().parent
BACKBONES = 20
SEQUENCES_PER_BACKBONE = 2


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sequence_of(atoms, chain):
    from Bio.SeqUtils import seq1

    selected = atoms[(atoms.chain_id == chain) & (atoms.atom_name == "CA") & ~atoms.hetero]
    return seq1("".join(selected.res_name))


def target_sequence(path):
    from Bio.PDB import PDBParser
    from Bio.SeqUtils import seq1

    chain = PDBParser(QUIET=True).get_structure("target", path)[0]["B"]
    return seq1("".join(residue.resname for residue in chain if "CA" in residue))


def write_complex_pdb(atoms, binder_chain, target_chain, path):
    """Write the design as a two-chain PDB: binder as A, target as B."""
    from io import StringIO

    from atomworks.io.utils.io_utils import to_cif_file
    from Bio.PDB import MMCIFParser, PDBIO

    staging = path.with_suffix("")
    to_cif_file(atoms, staging, file_type="cif")
    cif = staging.with_suffix(".cif")
    model = MMCIFParser(QUIET=True).get_structure(path.stem, cif)[0]
    rename = {binder_chain: "A", target_chain: "B"}
    for chain in list(model):
        if chain.id not in rename:
            model.detach_child(chain.id)
    # Two passes so a rename cannot collide with a chain that still holds the id.
    for chain in model:
        chain.id = "_" + rename[chain.id]
    for chain in model:
        chain.id = chain.id[1:]
    writer = PDBIO()
    writer.set_structure(model)
    writer.save(str(path))
    cif.unlink(missing_ok=True)


def prepare_target(root):
    """Write the grafted TrkA target and the RFdiffusion input next to it."""
    sys.path.insert(0, str(SOURCE.parent / "af2_filter"))
    from target_sidechains import graft

    inputs = root / "inputs"
    text = graft(inputs / "design.pdb", "B", inputs / "target_1www_chainX.pdb", "X")
    target = root / "trka_target.pdb"
    target.write_text(text + "END\n")
    specification = read_json(inputs / "design_spec.json")
    for entry in specification.values():
        entry["input"] = str(target)
    write_json(root / "trka.json", specification)
    print(f"표적 준비 완료: {target.name}", flush=True)


def generate_backbones(root):
    import numpy as np
    from rfd3.engine import RFD3InferenceConfig, RFD3InferenceEngine

    config = RFD3InferenceConfig(
        diffusion_batch_size=1, low_memory_mode=False, compile_model=False,
        compile_cuda_graphs=False, inference_kernel_backend="torch", seed=0,
    )
    model = RFD3InferenceEngine(**config)
    model._assign_override("trainer.precision", "32-true")
    output = model.run(inputs=str(root / "trka.json"), n_batches=BACKBONES)
    samples = [sample for batch in (output or {}).values() for sample in batch]
    if len(samples) != BACKBONES:
        raise RuntimeError(f"Expected {BACKBONES} RFdiffusion structures, got {len(samples)}.")

    wanted = target_sequence(root / "trka_target.pdb")
    backbones = []
    for index, sample in enumerate(samples, 1):
        atoms = sample.atom_array
        chains = [str(chain) for chain in np.unique(atoms.chain_id)]
        target_chain = next((c for c in chains if sequence_of(atoms, c) == wanted), None)
        if target_chain is None:
            raise RuntimeError(f"Backbone {index}: no chain matches the TrkA target sequence.")
        binder_chain, = [c for c in chains if c != target_chain]
        name = f"design_{index:02d}"
        path = root / "backbones" / f"{name}.pdb"
        write_complex_pdb(atoms, binder_chain, target_chain, path)
        backbones.append({"id": name, "file": f"backbones/{name}.pdb",
                          "binder_length": len(sequence_of(atoms, binder_chain))})
        print(f"  {index}/{BACKBONES} {name} 결합여 {backbones[-1]['binder_length']}잔기", flush=True)
    write_json(root / "backbones.json", backbones)


def design_sequences(root):
    from mpnn.inference_engines.mpnn import MPNNInferenceEngine

    model = MPNNInferenceEngine(model_type="ligand_mpnn", is_legacy_weights=True,
                                write_structures=False, write_fasta=False, device="cuda")
    designs = []
    for backbone in read_json(root / "backbones.json"):
        results = model.run(input_dicts=[{
            "structure_path": str(root / backbone["file"]), "name": backbone["id"],
            "designed_chains": ["A"], "batch_size": SEQUENCES_PER_BACKBONE,
            "temperature": 0.1, "seed": 0, "remove_waters": True,
        }])
        for index, result in enumerate(results, 1):
            sequence = sequence_of(result.atom_array, "A")
            if len(sequence) != backbone["binder_length"]:
                raise RuntimeError(f"{backbone['id']}: MPNN returned {len(sequence)} residues, "
                                   f"backbone has {backbone['binder_length']}.")
            designs.append({"name": f"{backbone['id']}_seq{index:02d}",
                            "design_pdb": backbone["file"], "sequence": sequence})
        print(f"  {backbone['id']} 서열 {len(results)}개", flush=True)
    if len(designs) != len(read_json(root / "backbones.json")) * SEQUENCES_PER_BACKBONE:
        raise RuntimeError("Unexpected number of sequence designs.")
    write_json(root / "manifest.json", designs)
    (root / "designs.fasta").write_text(
        "".join(f">{d['name']}\n{d['sequence']}\n" for d in designs), encoding="utf-8")
    print(f"설계 {len(designs)}개 완료", flush=True)


if __name__ == "__main__":
    stages = {stage.__name__: stage for stage in (prepare_target, generate_backbones, design_sequences)}
    stages[sys.argv[1]](Path(sys.argv[2]))
