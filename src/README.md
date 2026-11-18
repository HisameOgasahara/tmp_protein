# 코드

| 폴더 / 파일 | 역할 |
| --- | --- |
| [af2_filter/](af2_filter/) | AlphaFold2 initial guess 채점 (3단계) |
| [rfd3_design/](rfd3_design/) | RFdiffusion3 백본 생성 + MPNN 서열 설계 (1·2단계) |
| [figures.py](figures.py) | 보존된 결과에서 README의 그림 두 장을 SVG로 생성 |

`figures.py`는 로컬 실행, 설치 불필요. `results/`에서 좌표와 점수를 읽어 SVG를 직접 씀
(`python src/figures.py`).

## af2_filter

업스트림 `dl_binder_design`의 `af2_initial_guess/predict.py`를 고정 리비전 그대로 실행하는
래퍼. 모델·특징 전처리·템플릿 마스킹·점수 산출을 직접 구현하지 않음.

| 파일 | 역할 |
| --- | --- |
| `workflow.py` | 런타임 구성(가상환경·CUDA·가중치·업스트림 체크아웃), 단일 설계 실행 |
| `predict.py` | 입력 복합체 준비, 업스트림 실행, 지표 집계 |
| `compare.py` | 구조 읽기, 표적 고정 후 결합체 자세 RMSD |
| `diagnostic_workflow.py` | 조건 비교 실험 진행과 배열 차이 비교 |
| `diagnostic_case.py` | 조건 1개 실행. AF2 특징·초기 좌표·신뢰도 배열을 가로채 저장 |
| `target_sidechains.py` | 주사슬 전용 설계에 실험 구조의 표적 사이드체인을 잔기별로 이식 |
| `calibration_workflow.py` | 공개 자료 아카이브 확보와 교정 실행 진행 |
| `calibration.py` | 라벨된 설계 선택·준비·채점, 그룹별 분포 요약 |
| `score_designs.py` | 새 설계를 같은 필터로 채점. 양성 대조군 포함 |

구현 결정:

- `diagnostic_case.py`는 업스트림 `model.RunModel`을 감싸 **실제로 모델에 들어간 배열을
  그대로 저장**. 입력을 추측하지 않고 확인하기 위함.
- `workflow.py`·`diagnostic_workflow.py`·`calibration_workflow.py`는 설치 상태를
  `/content` 아래 같은 폴더에 두고 한 Colab 세션에서 공유. 두 번째 실행부터 설치와
  가중치 다운로드 생략.
- `calibration.py`는 선택된 설계를 전부 준비한 뒤 업스트림 `predict.py`에 디렉터리째 한 번
  전달. 설계마다 호출하면 모델 적재가 반복됨. 업스트림이 `-pdbdir`·`-checkpoint_name`을
  지원해 중단 후 재개 가능.
- 결합여 길이는 설계마다 다름(65–94잔기). 길이를 가정하는 코드를 두지 않음. 표적 101잔기는
  공개 설계 95개에서 동일하므로 같은 참조 구조 사용.

## rfd3_design

| 파일 | 역할 |
| --- | --- |
| `runtime.py` | 설치와 환경 구성 |
| `checkpoints.py` | 모델 가중치 다운로드 |
| `rf3_runtime.py` | RF3 모델 생성 |
| `trka_workflow.py` | TrkA 설계 전체 진행. 설계 환경과 AF2 환경을 차례로 실행 |
| `trka_design.py` | 표적 준비 → RFD3 백본 → MPNN 서열. 결합여 길이를 고정 집합으로 추출 |
| `check_interface.py` | 생성된 백본이 지정 hotspot에 붙었는지 확인 (실행 후 점검) |
| `focus_workflow.py` | 백본 1개 집중 재추출 진행. 백본 생성 생략 |
| `focus_design.py` | 저장된 백본으로 서열 50개 설계, MPNN 점수 기록 |

### 환경이 두 개인 이유

RFdiffusion3·MPNN은 Python 3.12 foundry 스택, 업스트림 AF2는 Python 3.11 JAX·PyRosetta.
한 가상환경에 합칠 수 없어 `trka_workflow.py`가 노트북 인터프리터에서 두 환경을
서브프로세스로 호출.

두 패키지 모두 `workflow.py`를 갖고 있어 모듈 이름이 충돌. `importlib`으로 파일 경로를
지정해 적재하고 `sys.path` 순서에 의존하지 않음.

### 결합여 길이 고정

`trka_design.py`의 `BINDER_LENGTHS`가 contig 범위를 단일 값 몇 개로 좁힘. JAX가 총 서열
길이마다 커널을 다시 컴파일하기 때문 — 실측 길이당 92초, 실제 추론 10.5초. v0.1.0은
70–95 자유 추출로 백본 20개에서 17종이 나와 채점 시간의 62%를 재컴파일에 소모
([03](../docs/03-design-run.md) · [04](../docs/04-scale-run.md)).

`generate_backbones`는 길이마다 단일 항목 입력 파일로 `model.run`을 따로 호출 — 한 파일에
여러 길이를 넣고 `n_batches`로 나누는 방식은 의미가 검증되지 않음. 뽑힌 백본의 길이가
요청과 다르면 실행 중단.

## 규약

- 실행마다 `source.json`에 코드 버전, 저장소 커밋, 설정, 입력 SHA-256 기록.
- 서브프로세스 출력은 전부 `runtime/` 아래 로그. 실패 시 마지막 40줄 출력.
- 입력 준비 단계에서 서열·사슬 경계·주사슬 좌표 보존, **표적 사이드체인 존재**를 단정으로
  검사. GLY를 제외한 표적 잔기에 주사슬 외 원자가 없으면 중단 —
  [그 문제](../docs/issues/2026-11-18-trka-target-sidechains.md)의 재발 방지책.
