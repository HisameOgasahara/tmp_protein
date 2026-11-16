"""Fit and evaluate a CSF1R IC50 regression model using ChEMBL assays."""

import csv
import json
from pathlib import Path
import sys
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen


API = 'https://www.ebi.ac.uk/chembl/api/data/activity.json'
QUERY = dict(target_chembl_id='CHEMBL1844', standard_type='IC50',
             standard_relation__exact='=', standard_units='nM', limit=500)


def fetch_activities():
    url = f'{API}?{urlencode(QUERY)}'
    while url:
        with urlopen(url, timeout=60) as response:
            page = json.load(response)
        yield from page['activities']
        next_page = page['page_meta']['next']
        url = urljoin(API, next_page) if next_page else None


def fit_and_predict(output):
    import numpy as np
    import pandas as pd
    from rdkit import Chem, DataStructs
    from rdkit.Chem import rdFingerprintGenerator
    from rdkit.Chem.Scaffolds import MurckoScaffold
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import GroupShuffleSplit

    raw = []
    for record in fetch_activities():
        if (record.get('bao_format') != 'BAO_0000357'
                or record.get('data_validity_comment')
                or record.get('assay_variant_mutation')
                or not record.get('canonical_smiles')
                or not record.get('pchembl_value')):
            continue
        mol = Chem.MolFromSmiles(record['canonical_smiles'])
        if mol is not None and len(Chem.GetMolFrags(mol)) == 1:
            raw.append((record['activity_id'], record['assay_chembl_id'],
                        record['document_chembl_id'], record['assay_description'],
                        Chem.MolToSmiles(mol), float(record['pchembl_value'])))
    data = pd.DataFrame(raw, columns=['activity_id', 'assay_id', 'document_id',
                                      'assay_description', 'smiles', 'pIC50'])
    train = data.groupby('smiles', as_index=False).pIC50.median() if raw else data
    if len(train) < 50:
        raise RuntimeError(f'유효한 CSF1R IC50 학습 분자가 부족합니다: {len(train)}')
    data.to_csv(output / 'csf1r_training_assays.csv', index=False)

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048,
                                                            includeChirality=True)
    molecules = [Chem.MolFromSmiles(smiles) for smiles in train.smiles]
    groups = [MurckoScaffold.MurckoScaffoldSmiles(mol=mol) for mol in molecules]
    features = np.stack([generator.GetFingerprintAsNumPy(mol) for mol in molecules])
    fingerprints = [generator.GetFingerprint(mol) for mol in molecules]
    target = train.pIC50.to_numpy()
    fit_ids, test_ids = next(GroupShuffleSplit(n_splits=1, test_size=.2, random_state=2026)
                             .split(features, target, groups))
    model = RandomForestRegressor(n_estimators=300, min_samples_leaf=2,
                                  random_state=2026, n_jobs=-1)
    model.fit(features[fit_ids], target[fit_ids])
    prediction = model.predict(features[test_ids])
    baseline = DummyRegressor(strategy='median').fit(features[fit_ids], target[fit_ids])
    train['scaffold'] = groups
    train['split'] = 'train'
    train.loc[test_ids, 'split'] = 'held_out'
    train.loc[test_ids, 'holdout_predicted_pIC50'] = prediction
    train.to_csv(output / 'csf1r_validation.csv', index=False)
    metrics = dict(dataset=f'{API}?{urlencode(QUERY)}', assay_count=data.assay_id.nunique(),
                   molecule_count=len(train), holdout_count=len(test_ids),
                   holdout_mae_pIC50=mean_absolute_error(target[test_ids], prediction),
                   holdout_r2=r2_score(target[test_ids], prediction),
                   holdout_median_baseline_mae_pIC50=mean_absolute_error(
                       target[test_ids], baseline.predict(features[test_ids])),
                   split='Bemis-Murcko scaffold', model='Morgan fingerprint / RandomForestRegressor')
    (output / 'csf1r_model_validation.json').write_text(json.dumps(metrics, indent=2))

    model.fit(features, target)
    rows = []
    with (output / 'generated_properties.csv').open(newline='') as stream:
        for record in csv.DictReader(stream):
            mol = Chem.MolFromSmiles(record['smiles'])
            value = float(model.predict(generator.GetFingerprintAsNumPy(mol)[None, :])[0])
            similarity = max(DataStructs.BulkTanimotoSimilarity(generator.GetFingerprint(mol),
                                                                fingerprints))
            rows.append(dict(sdf=record['sdf'], smiles=record['smiles'], predicted_pIC50=value,
                             predicted_IC50_nM=10 ** (9 - value),
                             nearest_training_tanimoto=similarity))
    pd.DataFrame(rows).to_csv(output / 'csf1r_predicted_ic50.csv', index=False)


if __name__ == '__main__':
    fit_and_predict(Path(sys.argv[1]))
