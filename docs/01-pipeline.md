# 파이프라인 단계와 지표

## 단계

| 순서 | 도구 | 역할 | 코드 |
| --- | --- | --- | --- |
| 1 | RFdiffusion3 | 표적 hotspot에 접근하는 결합체 백본 생성 | [rfd3_design/](../src/rfd3_design/) |
| 2 | LigandMPNN | 백본에 맞는 서열 설계 | [rfd3_design/](../src/rfd3_design/) |
| 3 | AlphaFold2 initial guess | 복합체 예측 후 채점 | [af2_filter/](../src/af2_filter/) |
| 4 | — | 실험 검증 | 범위 밖 |

## 3단계 입력 구성

업스트림 `af2_initial_guess/predict.py`가 입력 복합체 PDB에서 특징을 만드는 방식.

| 특징 | 출처 | 비고 |
| --- | --- | --- |
| MSA | 없음 (단일 서열) | 설계 서열에는 동족체가 없음 |
| 템플릿 | **표적 잔기만** 전체 원자 좌표·마스크 | 결합체 잔기는 0으로 마스크 |
| 초기 좌표 | 복합체 **전체**의 전체 원자 좌표 | `initial_guess` |
| recycle | 3 | |
| 모델 | `model_1_ptm` | |

표적 템플릿에 사이드체인 좌표까지 들어감 — 입력 PDB의 표적 사이드체인이 실제 구조와
다르면 AF2가 잘못된 표면을 봄. 재현 실패의 원인
([기록](issues/2026-11-18-trka-target-sidechains.md)).

## 지표

| 지표 | 정의 | 산출 |
| --- | --- | --- |
| `pae_interaction` | 사슬 간 PAE 블록 두 개의 평균 | 업스트림 |
| `plddt_binder` | 결합체 구간 pLDDT 평균 | 업스트림 |
| `binder_aligned_rmsd` | 결합체만 정렬한 RMSD — **접힘** | 업스트림 |
| `target_aligned_rmsd` | 표적 정렬 좌표계의 결합체 RMSD — **배치** | 업스트림 |
| `rmsd_vs_original_design` | 표적 고정 후 Cα RMSD, 원 설계 기준 | [compare.py](../src/af2_filter/compare.py) |
| `rmsd_vs_published_af2` | 같은 계산, 공개 AF2 구조 기준 | 같음 |

접힘과 배치를 분리해서 봄. 전자가 작고 후자가 크면 접힘은 맞고 배치가 틀린 것 —
TrkA_88 재현 실패가 0.594 Å 대 31.135 Å로 이 형태.

RMSD는 반사를 허용하지 않는 Kabsch 중첩. 표적 Cα로 정렬 변환을 구한 뒤 결합체에 적용.
결합체를 따로 최적 정렬하지 않음.

## 통과 기준

Watson et al. 2023, Extended Data Fig. 8:

> "In silico success is defined in line with current best practice:
> **AF2 pLDDT of the monomer > 80, AF2 interaction pAE < 10,
> AF2 r.m.s.d. monomer vs design < 1 Å.**"

| 논문 표기 | 기준 | 출력 |
| --- | --- | --- |
| AF2 interaction pAE | < 10 | `pae_interaction` |
| AF2 pLDDT (monomer) | > 80 | `plddt_binder` |
| AF2 r.m.s.d. monomer vs design | < 1 Å | `binder_aligned_rmsd` |

업스트림 저장소도 같은 지표를 지목 — *"`pae_interaction` is the score that showed the
most predictivity in the experiments performed in the paper."*

이 저장소의 측정:

| 집단 | `pae_interaction` 통과 | 나머지 두 기준 |
| --- | --- | --- |
| 선별 후 공개 설계 20개 | 결합 5/6, 비결합 14/14 | 두 그룹을 가르지 않음 |
| 직접 설계 40개 | 0/40 | `plddt` 32/40, 접힘 21/40 |
| 직접 설계 160개 | 1/160 | `plddt` 126/160, 접힘 63/160 |

기준 셋 중 탈락을 결정하는 것은 `pae_interaction` 하나.
[02](02-filter-calibration.md) · [03](03-design-run.md) · [04](04-scale-run.md)

## 검증 지점

입력 준비 코드가 실행 중 단정하는 항목:

- 준비된 복합체 서열이 `결합체 + 표적` 순서와 일치
- 사슬 1 경계가 결합체 길이와 일치
- 서열 치환이 설계 주사슬 좌표를 바꾸지 않음 (허용 오차 0.002 Å)
- 공개 결합체 서열이 공개 AF2 구조의 사슬 중 하나와 일치
- **표적 잔기에 사이드체인 원자 존재** (GLY 제외)

마지막 항목은 사후 추가. 이 검사가 없던 동안 표적 사이드체인이 비어 있어도 파이프라인이
정상 종료하며 틀린 값을 냈음.

### 실행 후 점검

단정으로 잡히지 않는 항목 — 생성된 백본이 지정한 hotspot에 붙었는지.
[check_interface.py](../src/rfd3_design/check_interface.py)가 백본별 계면 잔기와 hotspot
최단 거리를 산출.

RFdiffusion3가 표적 사슬을 1부터 재번호하므로 사양의 hotspot 번호와 직접 비교 불가.
표적 입력의 첫 잔기 번호를 기준으로 옮긴 뒤 **옮긴 자리의 잔기 이름이 사양과 같은지
교차 검증** — 번호를 잘못 옮긴 채 "접촉 없음"으로 결론 내는 것을 방지.
