# TrkA 결합체 설계 파이프라인 재현과 교정

RFdiffusion3 → ProteinMPNN → AlphaFold2 initial guess 로 이어지는 de novo 단백질 결합체
설계 파이프라인을 직접 돌리고, **채점 지표가 무엇을 재는지 공개 데이터로 교정**하는 저장소다.
실험 검증 수단이 없으므로 결합 여부를 주장하지 않는다. 계산으로 확인 가능한 범위까지만 다룬다.

## 현재까지 확인된 결과

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| 단량체 설계 자기일관성 | 설계 20개 중 **16개가 Cα RMSD < 2 Å** (최소 0.512 Å) | [결과](results/2026-11-16-monomer-selfconsistency) |
| 공개 TrkA_88 AF2 재현 | **실패.** 결합체 자세 31.14 Å, `pae_interaction` 26.07 | [결과 색인](results/README.md) |
| 실패 원인 | 공개 `design.pdb`가 주사슬 전용 → 표적 사이드체인이 재구성되며 충돌하는 결합면 생성 | [문제 기록](docs/issues/2026-11-18-trka-target-sidechains.md) |
| 원인 검증 | 표적 좌표만 교체 시 **31.14 Å → 1.65 Å**, `pae_interaction` 26.15 → 4.86 | [진단](diagnostics/README.md) |

재현 대상 설계(TrkA_88)는 결합체 **자체 접힘은 0.594 Å로 정확**했다. 어긋난 것은 표적에 대한
배치뿐이다. 즉 실패는 설계나 AF2가 아니라 입력 준비 단계에서 발생했다.

## 폴더 지도

| 폴더 | 내용 |
| --- | --- |
| [docs/00-purpose.md](docs/00-purpose.md) | 프로젝트 취지, 범위, 무엇을 성공으로 볼지 |
| [docs/01-pipeline.md](docs/01-pipeline.md) | 설계문서 — 파이프라인 단계, 지표 정의, 통과 기준 |
| [docs/issues/](docs/issues/) | 생긴 문제와 대처법 |
| [docs/references.md](docs/references.md) | 참고 논문, 공개 데이터, 고정한 업스트림 리비전 |
| [notebooks/](notebooks/) | Colab 실행 진입점 |
| [src/](src/) | 파이프라인 코드 |
| [diagnostics/](diagnostics/) | 문제 발생 시 원인을 좁히는 조건 비교 실험 |
| [inputs/](inputs/) | 고정 입력 (공개 설계 구조·서열·실험 라벨) |
| [results/](results/) | 실행별 설정·지표·구조·로그 |

## 실행

GPU 가속이 필요하므로 Colab T4에서 실행한다. 로컬 PC에는 모델을 설치하지 않는다.

| 노트북 | 용도 | 소요 |
| --- | --- | --- |
| [notebooks/01_af2_filter_T4.ipynb](notebooks/01_af2_filter_T4.ipynb) | 공개 설계를 AF2 initial guess로 채점 | 설치 포함 약 7분 |
| [diagnostics/90_af2_conditions_T4.ipynb](diagnostics/90_af2_conditions_T4.ipynb) | 11개 조건 비교로 실패 원인 분리 | AF2 11회, 약 23분 |

실행하면 설정·입력 해시·지표·구조·로그를 담은 ZIP 하나가 나온다. 그 ZIP을 `results/` 아래
날짜 폴더로 풀어 보존한다. 규칙은 [results/README.md](results/README.md)에 있다.

## 재현성

- 업스트림 AF2 실행 코드는 커밋 `cafa3853ac94dceb1b908c8d9e6954d71749871a`로 고정한다.
- AF2 가중치는 `alphafold_params_2022-12-06`의 `params_model_1_ptm`을 쓰고 SHA-256을 기록한다.
- 모든 입력 파일의 SHA-256을 실행마다 `source.json`에 남긴다.
- 실행 시 저장소 커밋 해시를 `source.json`에 기록한다.

## 이력

재구성 이전 상태는 태그 `archive/2026-11-18-pre-restructure`에 보존돼 있다.
삭제된 GFP·CSF1R 실험 기록도 git 이력에 그대로 남아 있으며 해당 커밋에서 복구할 수 있다.
