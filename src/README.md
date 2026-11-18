# 코드

| 폴더 | 역할 |
| --- | --- |
| [af2_filter/](af2_filter/) | AlphaFold2 initial guess 채점 (파이프라인 3단계) |
| [rfd3_design/](rfd3_design/) | RFdiffusion3 백본 생성 + MPNN 서열 설계 (1·2단계) |

| 파일 | 역할 |
| --- | --- |
| [figures.py](figures.py) | 보존된 결과에서 README의 그림 두 장을 SVG로 생성 |

`figures.py`는 로컬에서 돌고 설치가 필요 없다. 좌표와 점수를 `results/`에서 읽어 직접
SVG를 쓴다(`python src/figures.py`). 그림이 어떤 실행에서 나왔는지 코드로 고정된다.

## af2_filter

업스트림 `dl_binder_design`의 `af2_initial_guess/predict.py`를 **고친 리비전 그대로**
실행하는 래퍼다. 모델·특징 전처리·템플릿 마스킹·점수 산출을 직접 구현하지 않는다.

| 파일 | 역할 |
| --- | --- |
| `workflow.py` | 런타임 구성(가상환경·CUDA·가중치·업스트림 체크아웃), 단일 설계 실행 |
| `predict.py` | 입력 복합체 준비, 업스트림 실행, 지표 집계 |
| `compare.py` | 구조 읽기, 표적 고정 후 결합체 자세 RMSD |
| `diagnostic_workflow.py` | 조건 비교 실험 전체 진행과 배열 차이 비교 |
| `diagnostic_case.py` | 조건 1개 실행. AF2 특징·초기 좌표·신뢰도 배열을 가로채 저장 |
| `target_sidechains.py` | 주사슬 전용 설계에 실험 구조의 표적 사이드체인을 잔기별로 이식 |
| `calibration_workflow.py` | 공개 자료 아카이브 확보와 교정 실행 진행 |
| `calibration.py` | 라벨된 설계 선택·준비·채점. 그룹별 분포 요약 |
| `score_designs.py` | 새로 설계한 후보를 같은 필터로 채점. 양성 대조군 포함 |

`diagnostic_case.py`는 업스트림 `model.RunModel`을 감싸서 **실제로 모델에 들어간 배열을
그대로 저장**한다. 입력을 추측하지 않고 확인하기 위한 장치다.

`workflow.py`, `diagnostic_workflow.py`, `calibration_workflow.py`는 설치 상태를 `/content`
아래 같은 폴더에 두고 한 Colab 세션에서 공유한다. 두 번째 실행부터는 설치와 가중치
다운로드를 건너뛴다. 공개 자료 아카이브도 같은 방식으로 한 번만 받는다.

`calibration.py`는 선택된 설계를 **모두 준비한 뒤 업스트림 `predict.py`에 디렉터리째
한 번** 넘긴다. 설계마다 따로 호출하면 모델 적재가 매번 반복되기 때문이다. 업스트림이
`-pdbdir`와 `-checkpoint_name`을 지원하므로 중간에 끊겨도 이어서 돌 수 있다.

결합여 길이는 설계마다 다르다(65~94잔기). 길이를 가정하는 코드를 두지 않는다. 표적
101잔기는 공개 설계 95개에서 모두 동일하므로 같은 참조 구조를 쓴다.

## rfd3_design

| 파일 | 역할 |
| --- | --- |
| `runtime.py` | 설치와 환경 구성 |
| `checkpoints.py` | 모델 가중치 다운로드 |
| `rf3_runtime.py` | RF3 모델 생성 |
| `trka_workflow.py` | **TrkA 설계 전체 진행.** 설계 환경과 AF2 환경을 차례로 띄운다 |
| `trka_design.py` | 표적 준비 → RFD3 백본 → MPNN 서열. 결합여 길이를 고정 집합으로 뽑는다 |
| `check_interface.py` | 생성된 백본이 지정한 hotspot에 붙었는지 확인 (실행 후 점검) |
| `focus_workflow.py` | **백본 1개 집중 재추출 진행.** 백본 생성을 건너뛴다 |
| `focus_design.py` | 저장된 백본을 가져와 서열 50개 설계, MPNN 점수도 기록 |
| `workflow.py` | 과거 PD-L1 실행 (채점 방법이 부적절해 결론에 쓰지 않음) |

### 환경이 두 개인 이유

RFdiffusion3·MPNN은 Python 3.12의 foundry 스택을, 업스트림 AF2는 Python 3.11의 JAX와
PyRosetta를 요구한다. 한 가상환경에 합칠 수 없다. `trka_workflow.py`는 노트북의 인터프리터에서
돌면서 두 환경을 각각 서브프로세스로 호출한다.

두 패키지 모두 `workflow.py`를 갖고 있어 모듈 이름이 겹친다. `trka_workflow.py`는
`importlib`으로 **파일 경로를 지정해** 불러온다. `sys.path` 순서에 기대지 않는다.

### 결합여 길이를 고정하는 이유

`trka_design.py`의 `BINDER_LENGTHS`가 contig의 범위를 몇 개의 단일 값으로 좁힌다.
**채점 비용 때문이다.** 업스트림 AF2는 JAX로 돌고, JAX는 총 서열 길이가 바뀌면 커널을
다시 컴파일한다. 실측으로 길이당 92초이고 실제 추론은 10.5초다. 첫 실행은 길이를
70–95에서 자유 추출해 백본 20개에서 17종을 뽑았고 채점 시간의 62%를 재컴파일에 썼다
([설계 실행 결과](../docs/03-design-run.md), [규모 확대 결과](../docs/04-scale-run.md)).

길이를 고정하면 설계가 몇 개든 컴파일은 길이 종류 수만큼만 일어난다. `generate_backbones`는
길이마다 단일 항목 입력 파일을 써서 `model.run`을 따로 호출한다. 한 파일에 여러 길이를
넣고 `n_batches`로 나누는 방식은 의미가 검증되지 않았으므로 쓰지 않는다. 뽑힌 백본의
길이가 요청과 다르면 실행을 멈춘다 — 고정 길이가 깨지면 속도 이득이 사라지기 때문이다.

**주의.** 현재 `workflow.py`의 `predict_complexes`는 RF3에 서열만 넘긴다. 표적 템플릿도
초기 좌표도 주지 않으므로 논문의 채점 방법과 다르다. 설계 단계(`generate_backbones`,
`design_sequences`)는 정상 작동이 확인됐다. 채점은 `af2_filter`로 교체해야 한다.
자세한 내용은 [results/README.md](../results/README.md)의 PD-L1 실행 메모 참조.

## 규약

- 실행마다 `source.json`에 코드 버전, 저장소 커밋, 설정, 입력 SHA-256을 남긴다.
- 서브프로세스 출력은 전부 `runtime/` 아래 로그로 남기고, 실패 시 마지막 40줄을 출력한다.
- 입력 준비 단계에서 서열·사슬 경계·주사슬 좌표 보존, **표적 사이드체인 존재**를
  단정으로 검사한다. 사이드체인 검사는 [그 문제](../docs/issues/2026-11-18-trka-target-sidechains.md)의
  재발 방지책이다. GLY를 제외한 표적 잔기에 주사슬 외 원자가 없으면 실행을 멈춘다.
