# TrkA 결합체 설계 파이프라인 재현과 교정

RFdiffusion3 → MPNN → AlphaFold2 initial guess 로 이어지는 de novo 단백질 결합체 설계
파이프라인을 직접 돌리고, **채점 지표가 무엇을 재는지 공개 데이터로 교정**하는 저장소다.
실험 검증 수단이 없으므로 결합 여부를 주장하지 않는다. 계산으로 확인 가능한 범위까지만 다룬다.

왜 이 구조가 됐는지는 [경과](docs/history.md)에 있다. 아래는 **지금 상태**다.

## 지금 상태

단계 정의와 번호는 [작업 순서](docs/00-purpose.md)에 있다.

| 무엇을 물었나 | 상태 | 상세 |
| --- | --- | --- |
| 설계한 구조대로 접히는 서열인가 | **확인.** 20개 중 16개가 Cα RMSD < 2 Å (최소 0.512 Å) | [결과](results/2026-11-16-monomer-selfconsistency) |
| 공개 결합체의 공개 결과를 다시 낼 수 있는가 | **성공.** 1.496 Å, `pae_interaction` 5.86 (논문 1.4 Å) | [문제 기록](docs/issues/2026-11-18-trka-target-sidechains.md) |
| 그 점수가 실제 결합을 가르는가 | **가르지 못한다.** 비결합체 14/14 통과, 결합체 5/6 통과 | [교정 결과](docs/02-filter-calibration.md) |
| 걸러지지 않은 날것은 어디에 놓이는가 | **0/40 통과.** 같은 배치의 양성 대조군은 통과 | [설계 실행 결과](docs/03-design-run.md) |
| 규모를 4배로 키우면 달라지는가 | **0/160 통과.** 다만 처음으로 계면 기준을 넘은 설계가 1개 (0.121 Å 차이로 탈락) | [규모 확대 결과](docs/04-scale-run.md) |

뒤의 두 줄을 합친 것이 현재의 핵심 결론이다.

> **이 필터는 선별 전 집단에서 거르고, 선별 후 집단에서는 더 이상 가르지 못한다.**

통과는 합격이 아니라 기본 확률을 얻는 것이고, 이 표적에서 그 값은 6/95 ≈ 6.3%다.
통과한 설계들 사이에서 `pae_interaction` 순서로 우선순위를 정할 근거는 없다.

설계 160개에서 잰 것: **이 파이프라인의 날것 출력이 필터를 통과할 확률은 1.9% 미만**
(0/160의 95% 상한). 떨어뜨리는 것은 언제나 계면 항 하나이고, 자신 있게 접힌 단백질에
계면이 없는 조합이 160개 중 106개다.

**결과를 가르는 것은 서열이 아니라 백본이다.** 백본 20개 중 19개는 서열을 8개씩 만들어도
전부 평탄면에 머물렀고, 쓸 만한 값은 백본 3개에서 나왔다.

## 문서 지도

| 문서 | 무엇이 들어 있나 |
| --- | --- |
| [docs/00-purpose.md](docs/00-purpose.md) | 취지, 범위, 무엇을 성공으로 볼지, 작업 순서 |
| [docs/01-pipeline.md](docs/01-pipeline.md) | 설계문서 — 파이프라인 단계, 지표 정의, 통과 기준, 검증 지점 |
| [docs/02-filter-calibration.md](docs/02-filter-calibration.md) | 교정 상세 — 분포, 한계, 지표를 어떻게 쓸 것인가 |
| [docs/03-design-run.md](docs/03-design-run.md) | 첫 설계 실행(40개) — 채점 결과, 소요 시간 분해, v0.2.0에 반영한 것 |
| [docs/04-scale-run.md](docs/04-scale-run.md) | 규모 확대 실행(160개) — 재컴파일 수정 검증, 백본별 분해, 통과율 상한 |
| [docs/history.md](docs/history.md) | **경과** — 각 단계가 무엇 때문에 다음을 바꿨는지, 버린 선택 |
| [docs/issues/](docs/issues/) | 생긴 문제와 대처법. 원인 미규명 건은 그렇다고 적는다 |
| [docs/references.md](docs/references.md) | 참고 논문, 공개 데이터, 고정한 업스트림 리비전과 가중치 |

## 폴더 지도

| 폴더 | 내용 |
| --- | --- |
| [notebooks/](notebooks/) | Colab 실행 진입점 |
| [src/](src/) | 파이프라인 코드 ([af2_filter](src/af2_filter) 채점, [rfd3_design](src/rfd3_design) 설계) |
| [inputs/](inputs/) | 고정 입력 — 공개 설계 구조·서열·실험 라벨·설계 사양 |
| [results/](results/) | 실행별 설정·지표·구조·로그. 실행 하나당 폴더 하나 |
| [diagnostics/](diagnostics/) | 문제 발생 시 원인을 좁히는 조건 비교 실험 |
| [docs/](docs/) | 위 문서 지도 참조 |

## 실행

GPU 가속이 필요하므로 Colab T4에서 실행한다. 로컬 PC에는 모델을 설치하지 않는다.

| 노트북 | 용도 | 소요 |
| --- | --- | --- |
| [01_af2_filter_T4](notebooks/01_af2_filter_T4.ipynb) | TrkA_88 한 건을 채점 — 재현 확인 | 설치 포함 약 7분 |
| [02_calibrate_filter_T4](notebooks/02_calibrate_filter_T4.ipynb) | 라벨된 설계 20개 채점 — 지표 교정 | 약 40분 |
| [03_design_trka_T4](notebooks/03_design_trka_T4.ipynb) | 새 결합여 160개 설계 후 채점 | 약 1.75시간 |
| [90_af2_conditions_T4](diagnostics/90_af2_conditions_T4.ipynb) | 12개 조건 비교로 실패 원인 분리 | 약 25분 |

실행하면 설정·입력 해시·지표·구조·로그를 담은 ZIP 하나가 나온다. 그 ZIP을 `results/` 아래
날짜 폴더로 풀어 보존한다. 규칙은 [results/README.md](results/README.md)에 있다.

**노트북은 clone한 코드를 실행한다.** 코드를 고친 뒤에는 push 후 다시 실행한다.

## 재현성

- 업스트림 AF2 실행 코드는 커밋 `cafa3853ac94dceb1b908c8d9e6954d71749871a`로 고정한다.
- AF2 가중치는 `alphafold_params_2022-12-06`의 `params_model_1_ptm`을 쓰고 SHA-256을 기록한다.
- 모든 입력 파일의 SHA-256과 저장소 커밋 해시를 실행마다 `source.json`에 남긴다.
- 과거 실행의 지표 값은 기준이 바뀌어도 원래 값으로 보존한다. 재평가는 새 폴더에 한다.

## 이력

재구성 이전 상태는 태그 `archive/2026-11-18-pre-restructure`에 보존돼 있다.
삭제된 GFP·CSF1R 실험 기록도 git 이력에 그대로 남아 있으며 해당 커밋에서 복구할 수 있다.
