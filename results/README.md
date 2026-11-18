# 결과

실행 하나당 폴더 하나다. 이름은 `YYYY-MM-DD-<내용>`.

## 저장 규칙

노트북 실행이 끝나면 ZIP 하나가 나온다. 그 ZIP을 새 폴더에 풀고, ZIP 원본도 함께 둔다.
폴더 안에는 최소한 다음이 있어야 한다.

| 항목 | 내용 |
| --- | --- |
| `source.json` | 코드 버전, 저장소 커밋 해시, 설정값, 입력 파일 SHA-256 |
| `metrics/` 또는 결과 JSON | 지표 |
| `runtime/` | 설치·실행·환경 로그, 소요 시간, `nvidia-smi` 출력 |
| 예측 구조 | 실제 출력 PDB/CIF |

`source.json`의 커밋 해시가 핵심이다. 이 해시로 당시 코드를 정확히 복원할 수 있다.
**과거 실행의 지표 값은 나중에 기준이 바뀌어도 원래 값으로 보존한다.** 재평가가 필요하면
새 폴더를 만든다.

## 목록

| 폴더 | 내용 | 결과 |
| --- | --- | --- |
| [2026-11-16-monomer-selfconsistency](2026-11-16-monomer-selfconsistency) | 표적 없는 80잔기 단량체 설계 → 서열 설계 → 역검증 | **설계 20개 중 16개가 Cα RMSD < 2 Å**, 최소 0.512 Å |
| [2026-11-18-pdl1-8aom-rf3](2026-11-18-pdl1-8aom-rf3) | PD-L1 표적 설계 16개, RF3 서열 전용 채점 | 자세 RMSD 8.9–31.1 Å, ipTM 0.13–0.20. **채점 방법이 부적절해 결론에 쓰지 않음** |
| [2026-11-18-trka88-af2-colabdesign](2026-11-18-trka88-af2-colabdesign) | TrkA_88 재현, ColabDesign 경로 | 실패. 38.66 Å, 결합면 PAE 26.37, ipTM 0.099 |
| [2026-11-18-trka88-af2-upstream](2026-11-18-trka88-af2-upstream) | TrkA_88 재현, 업스트림 AF2 코드 | 실패. 31.14 Å, `pae_interaction` 26.07 |
| [2026-11-18-trka88-diagnostics](2026-11-18-trka88-diagnostics) | 11개 조건 비교로 실패 원인 분리 | **원인 확정** — 표적 전체 원자 좌표 |
| [2026-11-18-trka88-diagnostics-v2](2026-11-18-trka88-diagnostics-v2) | 12개 조건. 사이드체인 이식 수정안 포함 | **재현 성공. 1.496 Å, `pae_interaction` 5.86** |
| [2026-11-18-trka88-calibration](2026-11-18-trka88-calibration) | 실험 라벨이 붙은 설계 20개 채점 | **비결합체 14/14 통과 — 지표가 결합을 못 가름** |
| [2026-11-19-trka-design](2026-11-19-trka-design) | RFdiffusion3로 TrkA 결합여 40개 설계 후 같은 필터로 채점 | **0/40 통과, 같은 배치의 양성 대조군은 통과** |
| [2026-11-19-trka-design-v2](2026-11-19-trka-design-v2) | 길이 고정 후 설계 160개로 확대 | **0/160 통과.** 최저 `pae_interaction` 8.480 — 통과선 아래 첫 사례, 접힘 0.121 Å 차이로 탈락 |

## 실행별 메모

### 2026-11-16-monomer-selfconsistency

파이프라인 전체가 끝까지 도는 것을 확인한 실행이다. **표적이 없는 단량체**이므로 결합과는
무관하고, 확인한 것은 ① 자기일관성뿐이다 (단계 정의는
[취지 문서](../docs/00-purpose.md) 참조).

| 항목 | 값 |
| --- | --- |
| 생성 | RFdiffusion3, 80잔기, 백본 2개 |
| 서열 설계 | LigandMPNN, 백본당 10개, 총 20개 |
| 역검증 | RF3, recycle 10, 시드 0 |
| Cα RMSD < 2 Å | 20개 중 16개 |
| 최소 RMSD | 0.512 Å |

주요 파일: [metrics/representative_structures.csv](2026-11-16-monomer-selfconsistency/metrics/representative_structures.csv),
[metrics/definitions.json](2026-11-16-monomer-selfconsistency/metrics/definitions.json),
[figures/](2026-11-16-monomer-selfconsistency/figures)

`iptm`이 전부 0인 것은 정상이다. 단일 사슬이므로 사슬 간 지표가 정의되지 않는다.

### 2026-11-18-pdl1-8aom-rf3

RFdiffusion3 공식 8AOM 예제로 백본 8개와 서열 16개를 만들고 RF3로 채점했다.
설계 단계는 정상 작동했다 (백본 231초, 서열 24초).

**이 실행의 채점 결과는 결론에 쓰지 않는다.** RF3에 서열만 넘겼고 표적 템플릿과 초기
좌표를 주지 않았다. 논문의 성공률 기준인 AF2 initial guess와 다른 방법이므로, 설계가
나빴는지 채점이 부적절했는지 이 결과로는 구분되지 않는다. 교정된 AF2 필터로 재평가해야 한다.

### 2026-11-18-trka88-af2-colabdesign / -upstream

같은 재현 시도의 두 경로다. ColabDesign으로 돌린 것과 업스트림 `predict.py`를 직접
실행한 것 둘 다 실패했고, 실패 양상이 같았다. 업스트림 실행에서 결합체 자체 접힘은
`binder_aligned_rmsd` 0.594 Å로 정확했고 배치만 31.14 Å 어긋났다.

전체 벽시계: colabdesign 267초, upstream 411초 (설치·가중치 다운로드 포함).

### 2026-11-18-trka88-diagnostics

원본 ZIP은 102 MB이고 대부분이 조건별 특징 배열(`.npz`)이다. GitHub 파일 크기 제한
때문에 **텍스트 산출물만** 옮겼다 — 조건 정의, 지표, 배열 메타데이터와 SHA-256,
모델 설정, 예측·입력 PDB, 실행 로그.

빠진 것은 `*.npz` 원본 배열과 AF2 체크포인트다. 배열 비교 결론은
[feature_differences.json](2026-11-18-trka88-diagnostics/feature_differences.json)에
남아 있고, 각 배열의 shape·dtype·SHA-256은 같은 이름의 `.json` 사이드카에 있다.
원본 배열이 필요하면 같은 커밋으로 노트북을 다시 실행하면 재생성된다.

조건별 결과표는 [진단 문서](../diagnostics/README.md)에 있다.

### 2026-11-18-trka88-diagnostics-v2

수정안(`grafted_target_sidechains`)을 포함한 12개 조건. **재현에 성공한 실행이다.**

| 조건 | 설계 기준 RMSD | 공개 AF2 기준 | `pae_interaction` |
| --- | --- | --- | --- |
| `original_thread` (수정 전) | 32.780 Å | 32.157 Å | 26.15 |
| **`grafted_target_sidechains`** | **1.496 Å** | **0.191 Å** | **5.86** |
| `published_target_control` | 1.654 Å | 0.412 Å | 4.86 |

업스트림 코드가 자체 산출한 `target_aligned_rmsd`도 1.497 Å로 일치한다.
v0.1.0 실행과 겹치는 11개 조건의 값은 동일하다(`recycles_12`만 40.216 → 40.204 Å).

원본 ZIP은 113 MB이므로 앞 실행과 같은 기준으로 텍스트 산출물만 옮겼다(170개 파일, 7.6 MB).
`*.npz` 배열과 AF2 체크포인트는 제외했고, 배열의 shape·dtype·SHA-256은 사이드카 `.json`에 있다.

### 2026-11-19-trka-design

**설계 단계를 실제로 돌린 첫 실행이다.** RFdiffusion3 백본 20개 → MPNN 서열 40개 →
교정된 AF2 필터 41회(설계 40 + 양성 대조군 1).

| 항목 | 값 |
| --- | --- |
| 통과 | **0/40** |
| 양성 대조군 (공개 TrkA_88, 같은 배치) | **통과.** `pae_interaction` 5.862 |
| `pae_interaction` | 최소 10.235 / 중앙값 26.625 / 최대 27.464 |
| `plddt_binder` > 80 | 32/40 |
| `binder_aligned_rmsd` < 1 Å | 21/40 — **그 21개 전부 배치는 5 Å 이상 어긋남** |
| 배치 5 Å 미만 | 1개 (`design_08_seq02`, 3.700 Å) |

벽시계: 백본 500초, 서열 37초, 채점 2531초, 전체 3753초(62.6분).

설계 단계가 의도한 에피토프를 잡았는지 먼저 확인했다 —
[interface_check.txt](2026-11-19-trka-design/interface_check.txt). 백본 20개 전부가
Met108과 Leu145에 접촉했고(Phe115는 8/20), 옮긴 번호의 잔기 이름이 사양과 일치한다.
따라서 탈락은 표적을 못 찾아서가 아니다. 분석은
[설계 실행 결과](../docs/03-design-run.md)에 있다.

원본 ZIP(6.7 MB)을 함께 뒀다. 폴더에서 제외한 것은 `work/`(19 MB, PyRosetta가 수소를
붙여 쓴 중간 복합체)와 `inputs/`(저장소 `inputs/trka/`와 동일)뿐이다. 백본·예측 구조·로그·
체크포인트는 전부 들어 있다.

### 2026-11-19-trka-design-v2

같은 날의 두 번째 설계 실행이다. 결합여 길이를 **73·80·87·93으로 고정**해 JAX
재컴파일을 17회에서 4회로 줄이고, 아낀 시간을 설계 수에 썼다. 백본 20개 → MPNN 서열
160개 → AF2 161회(설계 160 + 양성 대조군 1).

| 항목 | v0.1.0 (앞 실행) | v0.2.0 (이 실행) |
| --- | --- | --- |
| 설계 | 40개 | **160개** |
| 통과 | 0/40 | **0/160** |
| 최저 `pae_interaction` | 10.235 | **8.480** (`design_13_seq03`) |
| 접힘·배치 동시 만족 | 0개 | **9개** (최소 배치 1.190 Å) |
| 컴파일 횟수 / 비중 | 17회 / 62% | **4회 / 9.2%** |
| 설계당 채점 | 61.7초 | **25.5초** |
| 양성 대조군 | 5.862 통과 | **5.862 통과** (동일) |

벽시계: 백본 518초, 서열 38초, 채점 4099초, 전체 6296초(104.9분).

`design_13_seq03`이 `pae_interaction` 8.480과 `plddt_binder` 86.04로 두 기준을 통과하고
접힘 1.121 Å로 **0.121 Å 모자라** 탈락했다. 분석은
[규모 확대 결과](../docs/04-scale-run.md)에 있다.

설계 단계는 [interface_check.txt](2026-11-19-trka-design-v2/interface_check.txt)로
확인했다 — 길이가 요청대로 4종 각 5개, 백본 20개 전부가 Met108과 Leu145에 접촉.

**원본 ZIP은 두지 않았다.** 25.9 MB이고 아래 파일들과 완전히 중복된다. 앞 실행은 ZIP이
6.7 MB라 함께 뒀지만 같은 기준을 여기 적용하면 저장소만 무거워진다. 제외한 것은
`work/`(73 MB, PyRosetta 중간 복합체)와 `inputs/`(저장소 `inputs/trka/`와 동일)이고,
백본·예측 구조 161개·로그·체크포인트·점수는 전부 들어 있다(40 MB).
