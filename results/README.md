# 결과

실행 하나당 폴더 하나. 이름은 `YYYY-MM-DD-<내용>`.

## 저장 규칙

노트북 실행이 끝나면 ZIP 하나가 나오고, 그 내용을 새 폴더에 보존. 폴더 필수 항목:

| 항목 | 내용 |
| --- | --- |
| `source.json` | 코드 버전, 저장소 커밋 해시, 설정값, 입력 파일 SHA-256 |
| 결과 JSON 또는 `metrics/` | 지표 |
| `runtime/` | 설치·실행·환경 로그, 소요 시간, `nvidia-smi` |
| 예측 구조 | 출력 PDB/CIF |

`source.json`의 커밋 해시로 당시 코드를 복원. 과거 실행의 지표는 기준이 바뀌어도 원래
값으로 보존하고, 재평가는 새 폴더에서.

## 목록

| 폴더 | 내용 | 결과 |
| --- | --- | --- |
| [2026-11-16-monomer-selfconsistency](2026-11-16-monomer-selfconsistency) | 표적 없는 80잔기 단량체 설계 → 서열 설계 → 역검증 | 20개 중 16개가 Cα RMSD < 2 Å, 최소 0.512 Å |
| [2026-11-18-pdl1-8aom-rf3](2026-11-18-pdl1-8aom-rf3) | PD-L1 설계 16개, RF3 서열 전용 채점 | 자세 RMSD 8.9–31.1 Å. 채점 방법이 부적절해 결론에 쓰지 않음 |
| [2026-11-18-trka88-af2-colabdesign](2026-11-18-trka88-af2-colabdesign) | TrkA_88 재현, ColabDesign 경로 | 실패. 38.66 Å, 결합면 PAE 26.37 |
| [2026-11-18-trka88-af2-upstream](2026-11-18-trka88-af2-upstream) | TrkA_88 재현, 업스트림 AF2 코드 | 실패. 31.14 Å, `pae_interaction` 26.07 |
| [2026-11-18-trka88-diagnostics](2026-11-18-trka88-diagnostics) | 11조건 비교 | 원인 확정 — 표적 전체 원자 좌표 |
| [2026-11-18-trka88-diagnostics-v2](2026-11-18-trka88-diagnostics-v2) | 12조건, 사이드체인 이식 포함 | **재현 성공. 1.496 Å, `pae` 5.86** |
| [2026-11-18-trka88-calibration](2026-11-18-trka88-calibration) | 실험 라벨된 설계 20개 채점 | 비결합 14/14 통과 |
| [2026-11-19-trka-design](2026-11-19-trka-design) | 결합여 40개 설계·채점 | **0/40**, 대조군은 통과 |
| [2026-11-19-trka-design-v2](2026-11-19-trka-design-v2) | 길이 고정 후 160개로 확대 | **0/160**, 최저 `pae` 8.480 |
| [2026-11-19-design04-focus](2026-11-19-design04-focus) | 백본 `design_04` 1개에 서열 50개 | **1/50 통과** — `design_04_r22`, `pae` 9.389 |

## 실행별 메모

### 2026-11-16-monomer-selfconsistency

| 항목 | 값 |
| --- | --- |
| 생성 | RFdiffusion3, 80잔기, 백본 2개 |
| 서열 설계 | LigandMPNN, 백본당 10개, 총 20개 |
| 역검증 | RF3, recycle 10, 시드 0 |
| Cα RMSD < 2 Å | 16/20 |
| 최소 RMSD | 0.512 Å |

표적이 없으므로 확인된 것은 ① 자기일관성뿐
([단계 정의](../docs/00-purpose.md)). `iptm`이 전부 0인 것은 단일 사슬이라 사슬 간
지표가 정의되지 않기 때문.

주요 파일:
[metrics/representative_structures.csv](2026-11-16-monomer-selfconsistency/metrics/representative_structures.csv),
[metrics/definitions.json](2026-11-16-monomer-selfconsistency/metrics/definitions.json),
[figures/](2026-11-16-monomer-selfconsistency/figures)

### 2026-11-18-pdl1-8aom-rf3

RFdiffusion3 공식 8AOM 예제로 백본 8개, 서열 16개 생성 후 RF3로 채점. 설계 단계는 정상
(백본 231초, 서열 24초).

채점 결과는 결론에 쓰지 않음 — RF3에 서열만 넘기고 표적 템플릿·초기 좌표를 주지 않아
논문의 AF2 initial guess와 다른 방법. 설계 품질과 채점 부적절을 구분할 수 없음.

### 2026-11-18-trka88-af2-colabdesign / -upstream

같은 재현 시도의 두 경로. 둘 다 실패하고 실패 양상이 동일. 업스트림 실행에서 결합체
자체 접힘은 `binder_aligned_rmsd` 0.594 Å로 정확하고 배치만 31.14 Å 어긋남.

벽시계: colabdesign 267초, upstream 411초 (설치·가중치 다운로드 포함).

### 2026-11-18-trka88-diagnostics

원본 ZIP 102 MB 중 대부분이 조건별 특징 배열(`.npz`). GitHub 파일 크기 제한으로 텍스트
산출물만 보존 — 조건 정의, 지표, 배열 메타데이터와 SHA-256, 모델 설정, 예측·입력 PDB,
실행 로그.

`*.npz` 원본 배열과 AF2 체크포인트는 제외. 배열 비교 결론은
[feature_differences.json](2026-11-18-trka88-diagnostics/feature_differences.json),
각 배열의 shape·dtype·SHA-256은 같은 이름의 `.json` 사이드카. 원본 배열은 같은 커밋으로
노트북을 다시 실행하면 재생성됨.

조건별 결과표는 [진단](../diagnostics/README.md).

### 2026-11-18-trka88-diagnostics-v2

수정안 `grafted_target_sidechains`를 포함한 12조건.

| 조건 | 설계 기준 RMSD | 공개 AF2 기준 | `pae_interaction` |
| --- | --- | --- | --- |
| `original_thread` (수정 전) | 32.780 Å | 32.157 Å | 26.15 |
| **`grafted_target_sidechains`** | **1.496 Å** | **0.191 Å** | **5.86** |
| `published_target_control` | 1.654 Å | 0.412 Å | 4.86 |

업스트림이 자체 산출한 `target_aligned_rmsd`도 1.497 Å로 일치. 앞 실행과 겹치는 11조건의
값은 동일(`recycles_12`만 40.216 → 40.204 Å).

원본 ZIP 113 MB. 앞 실행과 같은 기준으로 텍스트 산출물만 보존(170개 파일, 7.6 MB).

### 2026-11-19-trka-design

| 항목 | 값 |
| --- | --- |
| 구성 | 백본 20개 → 서열 40개 → AF2 41회 (설계 40 + 대조군 1) |
| 통과 | **0/40** |
| 대조군 TrkA_88 | 통과, `pae_interaction` 5.862 |
| `pae_interaction` | 최소 10.235 / 중앙값 26.625 / 최대 27.464 |
| `plddt_binder` > 80 | 32/40 |
| 접힘 < 1 Å | 21/40 |
| 배치 < 5 Å | 1개 (`design_08_seq02`, 3.700 Å) |

벽시계: 백본 500초, 서열 37초, 채점 2531초, 전체 3753초(62.6분).

설계 단계는 [interface_check.txt](2026-11-19-trka-design/interface_check.txt)로 확인 —
백본 20개 전부가 Met108·Leu145에 접촉(Phe115는 8/20), 옮긴 번호의 잔기 이름이 사양과
일치. 분석은 [03-design-run](../docs/03-design-run.md).

원본 ZIP(6.7 MB) 포함. 제외: `work/`(19 MB, PyRosetta 중간 복합체), `inputs/`(저장소
`inputs/trka/`와 동일).

### 2026-11-19-trka-design-v2

결합여 길이를 73·80·87·93으로 고정하고 설계를 160개로 확대. 백본 20개 → 서열 160개 →
AF2 161회.

| 항목 | v0.1.0 | v0.2.0 |
| --- | --- | --- |
| 설계 | 40개 | **160개** |
| 통과 | 0/40 | **0/160** |
| 최저 `pae_interaction` | 10.235 | **8.480** (`design_13_seq03`) |
| 접힘·배치 동시 만족 | 0개 | **9개**, 최소 배치 1.190 Å |
| 컴파일 횟수 / 비중 | 17회 / 62% | **4회 / 9.2%** |
| 설계당 채점 | 61.7초 | **25.5초** |
| 대조군 | 5.862 | 5.862 |

벽시계: 백본 518초, 서열 38초, 채점 4099초, 전체 6296초(104.9분).

`design_13_seq03`이 `pae_interaction` 8.480 / `plddt_binder` 86.04로 두 기준 통과,
접힘 1.121 Å로 0.121 Å 부족해 탈락. 분석은 [04-scale-run](../docs/04-scale-run.md).

[interface_check.txt](2026-11-19-trka-design-v2/interface_check.txt) — 길이가 요청대로
4종 각 5개, 백본 20개 전부가 Met108·Leu145에 접촉.

원본 ZIP(25.9 MB)은 보존 파일과 중복이라 제외. 함께 제외: `work/`(73 MB),
`inputs/`(저장소와 동일). 보존 40 MB.

### 2026-11-19-design04-focus

백본을 생성하지 않고 앞 실행의 `design_04.pdb`로 서열만 50개 재추출.

| 항목 | v0.2.0의 같은 백본 (서열 8) | 이 실행 (서열 50) |
| --- | --- | --- |
| 세 기준 통과 | 0 | **1 — `design_04_r22`** |
| `pae_interaction` 최소 | 12.934 | **9.389** |
| `pae_interaction` 중앙값 | 18.794 | 19.788 |
| `plddt_binder` > 80 | 8/8 | 50/50 |
| 접힘 < 1 Å | 7/8 | 47/50 |

두 표본의 분포가 사실상 동일. 통과율 2%에서 8개를 뽑아 하나도 못 건질 확률 85% —
한계 지점은 서열 추출 수. 분석은 [05-focus-run](../docs/05-focus-run.md).

벽시계: 백본 준비 0.7초, 서열 36초, 채점 1216초, 전체 2048초(34.1분). 길이 2종이므로
JAX 컴파일 2회.

MPNN 서열 점수를 기록하려 했으나 `MPNNInferenceOutput`에 스칼라 속성이 없어
`mpnn_scores.json`의 `mpnn` 칸이 비어 있음
([로그](2026-11-19-design04-focus/runtime/design_sequences.log)).

원본 ZIP 제외. 함께 제외: `work/`(23 MB), `inputs/`(저장소와 동일). 보존 12 MB.
