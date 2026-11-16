from pathlib import Path
from datetime import datetime, timezone
import json
import os
import platform
import shutil
import subprocess
import time

from types import SimpleNamespace


def install(num_samples=5, batch_size=1):
    if not Path('/content').is_dir() or not shutil.which('nvidia-smi'):
        raise RuntimeError('Google Colab GPU 런타임에서 실행하세요.')

    BASE = Path('/content/conditar_v001')
    RUN = BASE / datetime.now(timezone.utc).strftime('run_%Y%m%d_%H%M%S_%f')
    OUTPUT = RUN / 'results'
    INPUTS = OUTPUT / 'inputs'
    SAMPLE_ROOT = OUTPUT / 'generated'
    SAMPLES = SAMPLE_ROOT / '8w1l'
    RUNTIME = OUTPUT / 'runtime'
    for directory in (INPUTS, SAMPLES, RUNTIME):
        directory.mkdir(parents=True)

    REPO = BASE / 'upstream'
    REVISION = '8b322d0f08b973bce4c8e30d8517e30b5c65f342'
    ENV_DIR = BASE / 'env'
    PYTHON = ENV_DIR / 'bin/python'
    MAMBA = BASE / 'bin/micromamba'
    # The isolated subprocess has no Colab inline Matplotlib backend.
    ENV = dict(os.environ, MAMBA_ROOT_PREFIX=str(BASE / 'mamba'),
               PYTHONUNBUFFERED='1', MPLBACKEND='Agg')

    def run(args, **kwargs):
        subprocess.run([str(arg) for arg in args], env=ENV, check=True, **kwargs)

    def download(url, path):
        partial = path.with_name(path.name + '.part')
        run(['curl', '--fail', '--location', '--retry', '3', '--silent', '--show-error',
             '--output', partial, url])
        partial.replace(path)

    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total',
                                   '--format=csv'], text=True)
    print(gpu)
    (RUNTIME / 'host.txt').write_text(platform.python_version() + '\n' + gpu)
    if not (REPO / '.git').is_dir():
        run(['git', 'clone', 'https://github.com/ninglab/conDitar-dev.git', REPO])
    run(['git', '-C', REPO, 'checkout', '--detach', REVISION])

    if not MAMBA.exists():
        archive = BASE / 'micromamba.tar.bz2'
        download('https://micro.mamba.pm/api/micromamba/linux-64/latest', archive)
        run(['tar', '-xjf', archive, '-C', BASE, 'bin/micromamba'])
    if not PYTHON.exists():
        run([MAMBA, 'create', '-y', '-p', ENV_DIR, '-f', REPO / 'docker/environment.yml'])
    ENV['PATH'] = str(PYTHON.parent) + os.pathsep + ENV['PATH']
    run([PYTHON, '-m', 'pip', 'install', 'uv'])
    uv = [PYTHON, '-m', 'uv', 'pip', 'install', '--python', PYTHON]
    run([*uv, 'torch==2.5.1', '--index-url', 'https://download.pytorch.org/whl/cu124'])
    run([*uv, 'torch-geometric==2.7.0', 'torch-scatter==2.1.2', 'torch-sparse==0.6.18',
         'torch-cluster==1.6.3', 'torch-spline-conv==1.2.2', '--only-binary', ':all:',
         '--find-links', 'https://data.pyg.org/whl/torch-2.5.1+cu124.html'])
    run([*uv, 'meeko==0.1.dev3', 'pdb2pqr', 'tqdm', 'vina', 'cvxpy', 'biopython', 'matplotlib',
         'git+https://github.com/Valdes-Tresanco-MS/AutoDockTools_py3'])
    probes = {
        "torch": "import torch; print(torch.__version__, torch.version.cuda); assert torch.cuda.is_available(), 'CUDA unavailable'; print(torch.cuda.get_device_name()); print(torch.ones(1, device='cuda').item())",
        "pyg_extensions": "import torch, torch_cluster, torch_scatter; print(torch_cluster.__file__, torch_scatter.__file__)",
        "sampling_import": "import matplotlib; from scripts.conDitar import sample; print(sample.__file__)",
        "evaluation_import": "from scripts.conDitar import evaluate_mol; print(evaluate_mol.__file__)",
    }
    for name, command in probes.items():
        probe = subprocess.run([str(PYTHON), '-u', '-c', command], env=ENV, cwd=REPO,
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (RUNTIME / f'{name}.log').write_text(probe.stdout, encoding='utf-8')
        print(f'[{name}] {probe.stdout}', flush=True)
        if probe.returncode:
            raise RuntimeError(f'검증 실패 [{name}]\n{probe.stdout.rstrip()}')
    (RUNTIME / 'packages.txt').write_text(subprocess.check_output(
        [str(PYTHON), '-m', 'pip', 'freeze'], text=True, env=ENV))

    CONFIG = OUTPUT / 'sample.yml'
    TARGET = INPUTS / '8w1l'
    return SimpleNamespace(BASE=BASE, RUN=RUN, OUTPUT=OUTPUT, INPUTS=INPUTS,
                           SAMPLE_ROOT=SAMPLE_ROOT, SAMPLES=SAMPLES, RUNTIME=RUNTIME,
                           REPO=REPO, REVISION=REVISION, PYTHON=PYTHON, ENV=ENV,
                           CONFIG=CONFIG, TARGET=TARGET, NUM_SAMPLES=num_samples,
                           BATCH_SIZE=batch_size, run=run, download=download)
