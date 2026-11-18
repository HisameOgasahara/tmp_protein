# TrkA 결합체 설계 — 파이프라인 재현과 채점 지표 교정

RFdiffusion3 → LigandMPNN → AlphaFold2 initial guess, Colab T4.
공개 실험 라벨로 채점 기준을 먼저 교정하고, 그 자로 직접 설계한 결합여를 측정. 실험 수단 없음.

| 고정 | 값 |
| --- | --- |
| 표적 | TrkA D5 도메인, 공개 설계 좌표계 |
| 에피토프 | Met108 · Phe115 · Leu145 |
| 통과 기준 | `pae_interaction` < 10, `plddt_binder` > 80, 접힘 RMSD < 1 Å (Watson 2023) |
| 양성 대조군 | TrkA_88, 모든 채점 배치에 동봉 |

## 실행과 결과

| 실행 | 조건 | 결과 |
| --- | --- | --- |
| [단량체 자기일관성](results/2026-11-16-monomer-selfconsistency) | 표적 없음, 백본 2 × 서열 10 | 20개 중 16개 Cα RMSD < 2 Å, 최소 0.512 Å |
| [TrkA_88 재현](docs/issues/2026-11-18-trka-target-sidechains.md) | 공개 설계 1건 | **1.496 Å, `pae` 5.862** (논문 1.4 Å) |
| [지표 교정](docs/02-filter-calibration.md) | 실험 라벨된 공개 설계 20개 | 비결합 **14/14 통과**, 결합 5/6 통과 |
| [설계 v0.1.0](docs/03-design-run.md) | 백본 20 × 서열 2 = 40 | **0/40**, `pae` 최소 10.235 |
| [설계 v0.2.0](docs/04-scale-run.md) | 길이 4종 고정, 백본 20 × 서열 8 = 160 | **0/160**, `pae` 최소 8.480 |
| [집중 v0.3.0](docs/05-focus-run.md) | `design_04` 1개 × 서열 50 | **1/50 — `design_04_r22`** |

![세 집단의 pae_interaction 분포](docs/figures/pae-overview.svg)

## 문제와 선택

| 문제 | 선택 | 결과 | 상세 |
| --- | --- | --- | --- |
| 공개 설계 재현 실패. ColabDesign·업스트림 두 경로가 같은 양상 | 설정 탐색 중단, 12조건 통제 실험 | 원인은 표적 사이드체인 누락. 이식 후 31.1 Å → **1.496 Å** | [조건별 판정](diagnostics/README.md#수정안의-판정-결과) |
| 교정 집합 20개는 저자들이 이미 필터를 통과시켜 실험에 보낸 95개에서 나온 것 | 선별 전 날것을 직접 설계해 측정 | 0/40. 같은 배치 대조군은 통과 | [무엇이 떨어뜨렸나](docs/03-design-run.md#기준별-탈락) |
| 채점 2531초 중 1564초(62%)가 JAX 재컴파일. contig `70-95`가 길이 17종 생성 | 길이를 73·80·87·93으로 고정 | 컴파일 17회 → **4회(9.2%)**, 설계당 61.7초 → **25.5초** | [시간 분해](docs/03-design-run.md#소요-시간-분해) · [검증](docs/04-scale-run.md#길이-고정-효과) |
| 0/160. AF2에 보낼 백본을 미리 고를 수단 필요 | 백본 기하 설명자 8종과 AF2 결과의 상관 측정 | \|r\| ≤ 0.24. 사전 필터 안 폐기 | [상관 표](docs/04-scale-run.md#사전-필터-검증) |
| 백본별 분해로 "서열 줄이고 백본 늘리기" 제안 | 백본당 첫 서열만으로 선별했을 때를 역산 | 20개 전부 평탄면(24.9–27.5). 제안 철회, 서열 8개 유지 | [seq01 역산](docs/04-scale-run.md#백본별-분해) |
| `design_04` 배치 1.190 Å인데 `pae` 12.934에서 정지 | 같은 백본에 서열 50개 재추출 | **1/50 통과.** 한계는 백본이 아니라 서열 수 | [백본별 분포 비교](docs/05-focus-run.md#백본별-분포-비교) |

## 통과한 설계

| `design_04_r22` | 값 | 기준 |
| --- | --- | --- |
| `pae_interaction` | 9.389 | < 10 |
| `plddt_binder` | 89.58 | > 80 |
| 접힘 RMSD | 0.702 Å | < 1 |
| 설계 위치와의 거리 | 1.407 Å | 대조군 1.497 Å |

같은 백본 50개 / 넓은 실행 160개 비교 — `plddt` > 80: 50개 전부 / 126, 접힘 < 1 Å: 47 / 63,
배치 < 5 Å: 41 / 11, `pae` < 20: 27 / 10.

![design_04_r22 예측 구조](docs/figures/design04-r22.svg)

## 구조

| 폴더 | 내용 |
| --- | --- |
| [notebooks/](notebooks/) | Colab 실행 진입점 |
| [src/](src/) | [af2_filter](src/af2_filter) 채점, [rfd3_design](src/rfd3_design) 설계, [figures.py](src/figures.py) 그림 생성 |
| [inputs/](inputs/) | 공개 설계 구조·서열·실험 라벨·설계 사양 |
| [results/](results/) | 실행 하나당 폴더 하나. 설정·입력 해시·지표·구조·로그 |
| [diagnostics/](diagnostics/) | 조건 비교 실험 |
| [docs/figures/](docs/figures/) | 위 두 그림. `python src/figures.py`로 결과에서 재생성 |

| 문서 | 내용 |
| --- | --- |
| [00-purpose](docs/00-purpose.md) | 취지, 범위, 단계별 성공의 정의, 작업 순서 |
| [01-pipeline](docs/01-pipeline.md) | 파이프라인 단계, 지표 정의, 통과 기준, 검증 지점 |
| [02-filter-calibration](docs/02-filter-calibration.md) | 교정 — 라벨된 20개의 분포 |
| [03-design-run](docs/03-design-run.md) | 설계 40개 — 채점 결과, 소요 시간 분해 |
| [04-scale-run](docs/04-scale-run.md) | 설계 160개 — 재컴파일 수정 검증, 백본별 분해 |
| [05-focus-run](docs/05-focus-run.md) | 백본 1개 × 서열 50 — 첫 통과 |
| [history](docs/history.md) | 각 실행이 다음 결정을 바꾼 경과, 버린 선택 |
| [issues/](docs/issues/) | 생긴 문제와 대처 |
| [references](docs/references.md) | 논문, 공개 데이터, 고정한 업스트림 리비전과 가중치 |

## 실행

| 노트북 | 용도 | 소요 |
| --- | --- | --- |
| [01_af2_filter_T4](notebooks/01_af2_filter_T4.ipynb) | TrkA_88 1건 채점 — 재현 확인 | 7분 |
| [02_calibrate_filter_T4](notebooks/02_calibrate_filter_T4.ipynb) | 라벨된 20개 채점 — 지표 교정 | 40분 |
| [03_design_trka_T4](notebooks/03_design_trka_T4.ipynb) | 새 결합여 160개 설계·채점 | 1.75시간 |
| [04_focus_design04_T4](notebooks/04_focus_design04_T4.ipynb) | 백본 1개에 서열 50개 재추출·채점 | 30분 |
| [90_af2_conditions_T4](diagnostics/90_af2_conditions_T4.ipynb) | 12조건 비교로 실패 원인 분리 | 25분 |

설치 포함 실측. 노트북은 clone한 코드를 실행 — 코드 수정 후 push 필요.
실행당 ZIP 하나 → [results/](results/) 아래 날짜 폴더로 보존.

## 재현성

- 업스트림 AF2 실행 코드: 커밋 `cafa3853ac94dceb1b908c8d9e6954d71749871a` 고정
- AF2 가중치: `alphafold_params_2022-12-06`의 `params_model_1_ptm`, SHA-256 기록
- 실행마다 입력 파일 SHA-256 + 저장소 커밋 해시를 `source.json`에 기록
