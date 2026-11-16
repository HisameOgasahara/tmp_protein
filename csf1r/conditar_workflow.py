from hashlib import file_digest
import json
from pathlib import Path
import shutil
import subprocess
from textwrap import dedent
import time

from conditar_runtime import command_error


def stage(context, name, args):
    RUNTIME, REPO, ENV = context.RUNTIME, context.REPO, context.ENV
    start = time.perf_counter()
    monitor_path = RUNTIME / f'{name}_gpu.csv'
    log_path = RUNTIME / f'{name}.log'
    with monitor_path.open('w') as gpu_log, log_path.open('wb') as log:
        monitor = subprocess.Popen(
            ['nvidia-smi', '--query-gpu=timestamp,memory.used', '--format=csv,noheader,nounits', '-l', '1'],
            stdout=gpu_log)
        try:
            status = subprocess.run([str(arg) for arg in args], cwd=REPO, env=ENV,
                                    stdout=log, stderr=subprocess.STDOUT).returncode
        finally:
            monitor.terminate()
            monitor.wait()
    measurements = [int(line.rsplit(',', 1)[-1]) for line in monitor_path.read_text().splitlines()
                    if line.rsplit(',', 1)[-1].strip().isdigit()]
    stats = {'seconds': round(time.perf_counter() - start, 2),
             'device_peak_sampled_mib': max(measurements, default=None), 'exit_code': status}
    (RUNTIME / f'{name}.json').write_text(json.dumps(stats, indent=2))
    if status:
        raise command_error(name, status, log_path)
    peak = stats['device_peak_sampled_mib']
    print(f"{name} 완료 · {stats['seconds']}초 · GPU 최대 {str(peak) + ' MiB' if peak is not None else '미측정'}")


def prepare_inputs(context):
    BASE = context.BASE
    TARGET = context.TARGET
    CONFIG = context.CONFIG
    REPO = context.REPO
    REVISION = context.REVISION
    RUNTIME = context.RUNTIME
    NUM_SAMPLES = context.NUM_SAMPLES
    BATCH_SIZE = context.BATCH_SIZE
    PYTHON = context.PYTHON
    download = context.download
    run = context.run
    CHECKPOINTS = BASE / 'checkpoints'
    CHECKPOINTS.mkdir(exist_ok=True)
    weights = {
        'Diff.pt': ('1Jv4NDVmyRoH_-CmCuWJe9ZIdS6XzPwQ9', 125799286),
        'PocketAE.pt': ('1c046SsBpVz96ugJyiRyaXyEtxJEc5n_E', 39516702),
    }
    weight_records = {}
    for name, (file_id, expected_bytes) in weights.items():
        path = CHECKPOINTS / name
        if not path.exists() or path.stat().st_size != expected_bytes:
            download(f'https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t', path)
        if path.stat().st_size != expected_bytes:
            raise RuntimeError(f'{name} 다운로드 크기 불일치')
        with path.open('rb') as stream:
            weight_records[name] = {'drive_id': file_id, 'bytes': expected_bytes,
                                    'sha256': file_digest(stream, 'sha256').hexdigest()}
        print(name, f'{expected_bytes / 1e6:.1f} MB')

    TARGET.mkdir(exist_ok=True)
    download('https://files.rcsb.org/download/8W1L.cif', TARGET / '8w1l.cif')
    download('https://models.rcsb.org/v1/8w1l/ligand?auth_asym_id=A&auth_seq_id=1001&encoding=sdf',
             TARGET / '8w1l.sdf')
    run([PYTHON, '-c', dedent('''
    from pathlib import Path
    import sys
    import yaml
    from Bio.PDB import MMCIFParser, PDBIO, Select
    from rdkit import Chem

    source, config_path, checkpoint_dir, target = map(Path, sys.argv[1:])
    structure = MMCIFParser(QUIET=True).get_structure("8w1l", target / "8w1l.cif")

    class ProteinChainA(Select):
        def accept_chain(self, chain):
            return chain.id == "A"

        def accept_residue(self, residue):
            return residue.id[0] == " "

    writer = PDBIO()
    writer.set_structure(structure[0])
    writer.save(str(target / "8w1l.pdb"), ProteinChainA())
    assert any(line.startswith("ATOM") for line in (target / "8w1l.pdb").read_text().splitlines())
    assert Chem.SDMolSupplier(str(target / "8w1l.sdf"))[0] is not None
    config = yaml.safe_load(source.read_text())
    config["model"]["checkpoint"] = str(checkpoint_dir / "Diff.pt")
    config["model"]["checkpoint_pocket"] = str(checkpoint_dir / "PocketAE.pt")
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    '''), REPO / 'configs/sample_container.yml', CONFIG, CHECKPOINTS, TARGET])
    (RUNTIME / 'settings.json').write_text(json.dumps({
        'upstream_commit': REVISION, 'weights': weight_records, 'pdb': '8W1L',
        'reference_ligand': 'A1AE3', 'num_samples': NUM_SAMPLES, 'batch_size': BATCH_SIZE,
        'input_preparation': 'RCSB mmCIF chain A standard residues and bound reference SDF',
    }, indent=2))


def generate(context):
    PYTHON = context.PYTHON
    CONFIG = context.CONFIG
    INPUTS = context.INPUTS
    NUM_SAMPLES = context.NUM_SAMPLES
    BATCH_SIZE = context.BATCH_SIZE
    SAMPLES = context.SAMPLES
    RUN = context.RUN
    stage(context, 'generation', [PYTHON, '-m', 'scripts.conDitar.sample', CONFIG,
          '--device', 'cuda:0', '--protein_root', INPUTS, '--pdb_filename', '8w1l/8w1l.pdb',
          '--sdf_filename', '8w1l/8w1l.sdf', '--pocket_radius', '10',
          '--num_samples', NUM_SAMPLES, '--batch_size', BATCH_SIZE, '--result_path', SAMPLES,
          '--tmp_dir', RUN / 'sample_tmp'])
    generated = sorted(SAMPLES.glob('*_generated_*.sdf'))
    if not generated:
        raise RuntimeError('복원된 분자가 없습니다. generation.log를 확인하세요.')
    print('저장된 분자:', len(generated))


def show_properties(context):
    run = context.run
    PYTHON = context.PYTHON
    OUTPUT = context.OUTPUT
    from IPython.display import Image, display
    import pandas as pd

    run([PYTHON, '-c', dedent('''
    from pathlib import Path
    import csv
    import sys
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Draw, QED

    results = Path(sys.argv[1])
    rows, molecules, names = [], [], []
    for path in sorted((results / "generated/8w1l").glob("*_generated_*.sdf")):
        mol = Chem.SDMolSupplier(str(path))[0]
        if mol is None:
            raise ValueError(f"Invalid SDF: {path}")
        rows.append((path.name, Chem.MolToSmiles(mol), round(Descriptors.MolWt(mol), 3),
                     round(QED.qed(mol), 4), "not_measured"))
        molecules.append(mol)
        names.append(path.stem)
    with (results / "generated_properties.csv").open("w", newline="") as handle:
        csv.writer(handle).writerows([("sdf", "smiles", "molecular_weight_da", "qed", "assay"), *rows])
    Draw.MolsToGridImage(molecules, molsPerRow=3, subImgSize=(300, 230), legends=names).save(
        str(results / "generated_molecules.png"))
    '''), OUTPUT])
    display(pd.read_csv(OUTPUT / 'generated_properties.csv'))
    display(Image(filename=str(OUTPUT / 'generated_molecules.png')))


def score_vina(context):
    PYTHON = context.PYTHON
    SAMPLE_ROOT = context.SAMPLE_ROOT
    INPUTS = context.INPUTS
    RUN = context.RUN
    run = context.run
    OUTPUT = context.OUTPUT
    REPO = context.REPO
    import pandas as pd
    from IPython.display import display

    stage(context, 'vina', [PYTHON, '-m', 'scripts.conDitar.evaluate_mol',
                   '--sample_path', SAMPLE_ROOT, '--protein_root', INPUTS,
                   '--docking_mode', 'vina_score', '--tmp_dir', RUN / 'vina_tmp'])
    run([PYTHON, '-c', dedent('''
    import csv
    from pathlib import Path
    import sys
    import torch

    results = Path(sys.argv[1])
    records = torch.load(results / "generated/eval_results/metrics_-1.pt",
                         map_location="cpu", weights_only=False)["all_results"]
    with (results / "vina_scores.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("sdf", "vina_pose_score_kcal_mol", "vina_minimized_score_kcal_mol"))
        for record in records:
            writer.writerow((record["ligand_filename"], record["vina"]["score_only"][0]["affinity"],
                             record["vina"]["minimize"][0]["affinity"]))
    '''), OUTPUT], cwd=REPO)
    scores = pd.read_csv(OUTPUT / 'vina_scores.csv')
    if scores.empty:
        raise RuntimeError('Vina 평가 결과가 비었습니다. runtime/vina.log를 확인하세요.')
    display(pd.read_csv(OUTPUT / 'vina_scores.csv'))


def predict_potency(context):
    import pandas as pd
    from IPython.display import display

    script = Path(__file__).with_name('conditar_potency.py')
    context.run([context.PYTHON, script, context.OUTPUT])
    metrics = json.loads((context.OUTPUT / 'csf1r_model_validation.json').read_text())
    print(f"분자 {metrics['molecule_count']}개 · 독립 골격 평가 MAE "
          f"{metrics['holdout_mae_pIC50']:.2f} pIC50 · "
          f"중앙값 기준 MAE {metrics['holdout_median_baseline_mae_pIC50']:.2f}")
    display(pd.read_csv(context.OUTPUT / 'csf1r_predicted_ic50.csv').drop(columns='smiles'))


def download_zip(context):
    RUN = context.RUN
    OUTPUT = context.OUTPUT
    from google.colab import files

    archive = shutil.make_archive(str(RUN / 'conditar_v005_results'), 'zip', root_dir=OUTPUT)
    files.download(archive)
