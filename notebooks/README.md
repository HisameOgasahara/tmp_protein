# 노트북

Colab T4에서 실행. 로컬 PC에 모델·가중치를 설치하지 않음.

셀 3개 구조 — ① GitHub `main`에서 clone하고 커밋 해시 출력, ② `src/` 워크플로를
서브프로세스로 실행하고 로그를 실시간 출력한 뒤 지표 표 표시, ③ 결과 ZIP 다운로드.

**clone한 코드를 실행하므로 push하지 않은 변경은 반영되지 않음.**

## 목록

| 노트북 | 하는 일 | 코드 | 소요 |
| --- | --- | --- | --- |
| [01_af2_filter_T4](01_af2_filter_T4.ipynb) | TrkA_88 1건 채점 — 재현 확인 | [workflow.py](../src/af2_filter/workflow.py) | 7분 |
| [02_calibrate_filter_T4](02_calibrate_filter_T4.ipynb) | 실험 라벨된 설계 20개 채점 — 지표 교정 | [calibration_workflow.py](../src/af2_filter/calibration_workflow.py) | 40분 |
| [03_design_trka_T4](03_design_trka_T4.ipynb) | TrkA에 새 결합여 160개 설계·채점 | [trka_workflow.py](../src/rfd3_design/trka_workflow.py) | 1.75시간 |
| [04_focus_design04_T4](04_focus_design04_T4.ipynb) | 백본 `design_04` 1개에 서열 50개 재추출·채점 | [focus_workflow.py](../src/rfd3_design/focus_workflow.py) | 30분 |

소요는 설치 포함 실측. 진단용 노트북은 [diagnostics/](../diagnostics/).

01·02·03은 서로 다른 질문 — 파이프라인이 정상인가 / 그 점수가 실제 결합을 가르는가 /
교정된 필터로 직접 설계한 후보가 어디에 놓이는가. 단계 정의는
[00-purpose](../docs/00-purpose.md).

## 실행 조건

**03·04는 환경을 둘 띄움.** RFdiffusion3·MPNN은 Python 3.12 foundry 스택, AF2는
Python 3.11 JAX·PyRosetta. 한 프로세스에 합칠 수 없어 각각 서브프로세스로 실행.

**채점 배치에 공개 결합여 TrkA_88을 양성 대조군으로 포함.**

**결합여 길이는 73·80·87·93 4종 고정.** JAX가 총 서열 길이마다 커널을 다시 컴파일하기
때문(길이당 92초, 실제 추론 10.5초). v0.1.0은 70–95 자유 추출로 17종이 나와 채점 시간의
62%를 재컴파일에 소모. 고정 후 실측 컴파일 4회(378초, 9.2%), 설계당 채점 61.7초 →
25.5초. [04-scale-run](../docs/04-scale-run.md)

**02는 공개 자료 아카이브(251.7 MB)를 Colab에서 받아 TrkA 부분만 전개**하고 같은 세션에서
재사용. 로컬 디스크 미사용.

## 실행 후

받은 ZIP은 [results/](../results/)의 규칙에 따라 날짜 폴더로 보존.
