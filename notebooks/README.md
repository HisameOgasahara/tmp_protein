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

| 노트북 | 코드 | 소요 |
| --- | --- | --- |
| [01_af2_filter_T4.ipynb](01_af2_filter_T4.ipynb) | [src/af2_filter/workflow.py](../src/af2_filter/workflow.py) | 설치 포함 약 7분 |

진단용 노트북은 [diagnostics/](../diagnostics/)에 있다.

## 실행 후

받은 ZIP은 [results/](../results/)의 규칙에 따라 날짜 폴더로 풀어 보존한다.
