# Codebase Review

검토일: 2026-07-02

업데이트: 우선순위가 높은 반복 알림/보고서 문제 일부를 같은 PR에서 해결했다. 일반대학원 감시는 fingerprint 기반 중복 방지, 변경 없는 신규 없음 요약 억제, HTML 리포트 생성을 지원한다. 실행되지 않는 하위 workflow 파일도 제거했다.

## PR 필요 여부

현재 로컬 `main`과 `origin/main`은 동기화되어 있으며, 최근 변경 커밋 `948e495 Improve notice filtering and report deduping`은 이미 원격 `main`에 푸시되어 있다. 따라서 같은 변경분에 대한 별도 Pull Request는 현재 필요하지 않다.

다만 기본 브랜치 직접 푸시는 검토 이력과 롤백 지점이 약해진다. 이후 변경부터는 `cdx/...` 작업 브랜치에서 수정하고 PR로 검토, CI 확인 후 병합하는 방식이 적합하다.

## 검증 결과

- `python -m compileall university-course-watcher` 통과.
- `main` 브랜치는 `origin/main`과 동기화 상태로 확인됨.
- 루트 워크플로 `.github/workflows/daily-check.yml`은 일반대학원 감시를 실행하도록 구성되어 있음.
- 하위 폴더 `university-course-watcher/.github/workflows/daily-check.yml`에는 구버전 시간제등록 감시 워크플로가 남아 있어 실제 운영 설정과 혼동될 수 있음.

## 주요 발견 사항

### 1. 일반대학원 감시 중복 방지가 URL 단일 기준에 머문다

위치: `src/storage.py`의 `GraduateAdmissionStorage`

상태: 해결됨. URL, 정규화 제목, 게시판, 게시일, 확인 키워드, 첨부 URL을 조합한 fingerprint 기준으로 신규 여부와 중복 제거를 판단하도록 변경했다.

시간제등록 감시는 최근 수정으로 URL, 정규화 제목, 접수기간, 첨부 기반 지문을 함께 사용한다. 반면 일반대학원 감시는 `seen_graduate_admission_urls.json`에 URL만 저장한다. 게시판 URL이 상세 글마다 안정적으로 유지되지 않거나 상시 모집요강 페이지가 같은 URL로 갱신되는 경우 다음 문제가 생긴다.

- 같은 공고가 다른 URL로 잡히면 반복 알림 가능.
- 같은 상시 페이지 URL에서 실제 모집요강 PDF가 바뀌어도 이미 본 URL로 처리되어 신규 공고를 놓칠 가능성.

개선안: `GraduateAdmissionStorage`에도 제목 정규화, 첨부 URL, 핵심 키워드, notice date 기반 fingerprint를 도입한다. 상시 페이지는 페이지 URL이 아니라 첨부 파일 URL 또는 PDF 파일명/텍스트 일부를 주요 지문으로 삼아야 한다.

### 2. 일반대학원 신규 없음 요약 알림이 매 실행마다 전송된다

위치: `src/notifier.py`의 `GraduateAdmissionNotifier.send_candidates`

상태: 해결됨. 신규 후보가 없을 때는 후보 구성, 활성 대상 수, 비활성 대상 수가 바뀐 경우에만 요약 알림을 전송하도록 변경했다.

신규 대상이 없을 때도 매번 텔레그램 요약 메시지를 전송한다. 사용자가 지적한 "맨날 똑같은 보고서/똑같은 결과" 문제는 일반대학원 감시에서 여전히 남아 있다. 하루 2회 cron이면 신규가 없어도 매일 2번 같은 성격의 메시지를 받을 수 있다.

개선안: 신규 없음 요약도 이전 요약과 비교해 의미 있는 변화가 있을 때만 전송한다. 예를 들면 활성 대상 수 변경, 후보 수 변경, 오류/비활성 대상 변경, 마지막 성공 이후 N일 경과 같은 조건을 둔다.

### 3. GitHub Actions cache key가 실행마다 새로 만들어진다

위치: `.github/workflows/daily-check.yml`

`key: graduate-admission-seen-${{ github.run_id }}`는 매 실행마다 고유한 키를 만든다. `restore-keys`로 이전 캐시를 복원할 수는 있지만, 매번 새 캐시가 쌓이는 구조다. 장기적으로 캐시가 불필요하게 누적되고, 최신 seen 파일 선택이 GitHub cache 동작에 의존한다.

개선안: 고정 키를 쓸 수 없는 GitHub Actions cache 특성을 고려해 artifacts, repository variable, 별도 state branch, gist, 또는 GitHub Actions cache의 주기적 정리 전략 중 하나로 상태 저장 방식을 명확히 정한다. 단순 운영이면 `seen` 파일을 artifact로만 남기지 말고 state branch에 커밋하는 방식이 더 예측 가능하다.

### 4. 실제 워크플로가 루트와 하위 폴더에 중복 존재한다

위치:

- 실제 사용: `.github/workflows/daily-check.yml`
- 혼동 유발: `university-course-watcher/.github/workflows/daily-check.yml`

GitHub Actions는 루트 `.github/workflows`만 인식한다. 하위 폴더 워크플로는 실행되지 않지만, README나 유지보수자가 잘못된 파일을 수정할 위험이 있다.

상태: 해결됨. 하위 폴더의 실행되지 않는 workflow 파일을 제거했다.

### 5. 탐색 범위가 설정 파일에 고정되어 있고 URL 검증 자동화가 운영 흐름에 연결되지 않았다

위치:

- `config/graduate_admission_boards.json`
- `validate_graduate_admission_boards.py`
- `check_candidate_urls.py`

일반대학원 감시 대상은 서울권 일부 대학 중심이며, 여러 대학이 비활성화되어 있다. 검증 스크립트는 존재하지만 정기 워크플로에서 실행되지 않아 URL이 깨져도 감시 품질 저하가 늦게 발견될 수 있다.

개선안: 정기 실행 전에 URL 상태와 키워드 hit 수를 검사하고, 접근 실패/키워드 0건/SSO redirect를 별도 리포트에 포함한다. 비활성 대학도 "탐색 제외"가 아니라 "보류 사유"로 보고서에 명확히 남긴다.

### 6. 첨부 HWP/HWPX 텍스트를 읽지 못한다

위치: `src/attachment_parser.py`

대학 모집요강은 HWP/HWPX로 올라오는 경우가 많다. 현재 HWP/HWPX/ZIP은 텍스트 추출 없이 빈 문자열을 반환한다. 이 때문에 제목만 애매한 공고나 모집요강 첨부 중심 공고는 신뢰도 낮게 분류되거나 누락될 수 있다.

개선안: HWPX는 ZIP/XML 구조 파싱으로 텍스트 추출을 추가한다. HWP는 가능한 환경에서 `pyhwp`, LibreOffice 변환, 또는 Windows COM/Hancom 자동화 중 하나를 선택하되 CI 환경 호환성을 따로 고려한다.

### 7. 범용 게시판 크롤러가 최신 글 일부만 본다

위치: `src/board_crawler.py`

기본 `max_links_per_board`는 15이고 일반대학원 감시는 12개만 상세 조회한다. 게시판이 상단 고정 공지, 배너 링크, 카테고리 혼합 구조를 쓰면 실제 모집요강 글이 12~15개 밖으로 밀릴 수 있다.

개선안: 게시판별 `max_links`, 카테고리 필터, 페이지네이션 2~3페이지 탐색 옵션을 설정 파일로 분리한다. 모집철에는 대학별 공지 구조에 맞춘 selector override도 필요하다.

### 8. 시간제등록 history 저장이 누적이 아니라 덮어쓰기다

위치: `src/storage.py`의 `_save_history`

`university_history.csv`는 이름상 이력 파일이지만 현재 실행 결과에서 조건에 맞는 row만 새로 쓰는 구조다. 장기 이력을 보려는 목적이라면 과거 데이터가 보존되지 않는다.

개선안: 기존 CSV를 읽어 합친 뒤 key 기준으로 병합 저장하거나, 실행별 snapshot 파일을 분리한다.

## 우선순위 개선 계획

1. 일반대학원 감시의 중복 방지와 신규 없음 요약 억제부터 수정한다.
2. 루트 워크플로만 남기고 하위 `.github/workflows` 중복 파일을 제거한다.
3. 일반대학원 결과 HTML 리포트를 별도로 생성해 후보, 제외 사유, 비활성/오류 대학을 한 번에 볼 수 있게 한다.
4. URL 검증 스크립트를 CI 또는 정기 리포트에 연결한다.
5. HWPX 텍스트 추출을 추가하고, HWP는 운영 환경에서 가능한 변환 경로를 결정한다.
6. 게시판별 탐색 깊이와 selector override를 설정화한다.

## 다음 작업 제안

가장 직접적인 개선 PR 범위는 다음 4개다.

- `GraduateAdmissionStorage`에 fingerprint 기반 중복 방지 추가
- 신규 없음 요약 메시지 변경 감지 추가
- 일반대학원 HTML 리포트 생성
- 하위 `.github/workflows/daily-check.yml` 제거

이 범위는 사용자가 지적한 반복 알림, 낮은 보고서 완성도, 검증 부족 문제를 가장 빠르게 줄인다.
