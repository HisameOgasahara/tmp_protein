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
