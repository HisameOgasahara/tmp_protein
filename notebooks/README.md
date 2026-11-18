# 노트북

Colab T4에서 실행한다. 로컬 PC에 모델이나 가중치를 설치하지 않는다.

각 노트북은 셀 3개 구조다.

1. GitHub `main`에서 이 저장소를 clone하고 커밋 해시를 출력한다.
2. `src/` 아래 워크플로를 서브프로세스로 실행하고 로그를 실시간 출력한다.
   결과 ZIP 경로를 받아 지표 표를 표시한다.
3. ZIP을 다운로드한다.

**노트북은 clone한 코드를 실행한다.** 즉 변경사항을 push하지 않으면 노트북에 반영되지
않는다. 코드를 고친 뒤에는 push 후 노트북을 다시 실행한다.

## 목록

| 노트북 | 하는 일 | 코드 | 소요 |
| --- | --- | --- | --- |
| [01_af2_filter_T4.ipynb](01_af2_filter_T4.ipynb) | TrkA_88 한 건을 채점 (재현 확인) | [workflow.py](../src/af2_filter/workflow.py) | 설치 포함 약 7분 |
| [02_calibrate_filter_T4.ipynb](02_calibrate_filter_T4.ipynb) | 실험 라벨이 붙은 설계 20개를 채점 (지표 교정) | [calibration_workflow.py](../src/af2_filter/calibration_workflow.py) | AF2 20회, 약 40분 |
| [03_design_trka_T4.ipynb](03_design_trka_T4.ipynb) | TrkA에 새 결합여 40개를 설계하고 채점 | [trka_workflow.py](../src/rfd3_design/trka_workflow.py) | RFD3 + MPNN + AF2 41회 |

진단용 노트북은 [diagnostics/](../diagnostics/)에 있다.

01은 파이프라인이 정상인지, 02는 그 점수가 실제 결합 여부를 가르는지, 03은 그 교정된
필터로 직접 설계한 후보가 어디에 놓이는지 본다. 서로 다른 질문이다.
단계 정의는 [취지 문서](../docs/00-purpose.md) 참조.

03은 환경을 둘 띄운다. RFdiffusion3·MPNN은 Python 3.12 foundry 스택, AF2는 Python 3.11
JAX·PyRosetta다. 한 프로세스에 합칠 수 없어서 노트북이 각각 서브프로세스로 돌린다.
채점 배치에 공개 결합여 TrkA_88을 양성 대조군으로 함께 넣는다.

02는 공개 자료 아카이브(251.7 MB)를 Colab에서 받아 TrkA 부분만 풀고, 같은 세션에서
재사용한다. 로컬 디스크는 쓰지 않는다.

## 실행 후

받은 ZIP은 [results/](../results/)의 규칙에 따라 날짜 폴더로 풀어 보존한다.
