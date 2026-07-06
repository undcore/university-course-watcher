# University Course Watcher

수도권 대학 공식 게시판을 직접 크롤링해 시간제등록, 청강, 특별수강, 비학위, 평생교육원, 학점은행제, 컴퓨터 관련 과목 수강 가능성이 있는 공고 후보를 찾는 Python 프로젝트입니다.

검색 API는 사용하지 않습니다. Tavily, SerpAPI, Google Custom Search API, Bing Search API 같은 외부 검색 API 의존성이 없고, `config/board_urls.json`에 등록된 대학 공식 게시판 URL만 순회합니다.

## 검색 대상

- 서울, 경기, 인천 소재 오프라인 4년제 일반대학
- 대학 공식 도메인 게시판의 입학처, 학사, 일반, 미래융합대학, 평생교육원, 학점은행제, 컴퓨터 관련 학과 공지
- 시간제등록생 모집, 청강, 특별수강, 일반인/타교생/비학위 수강, 컴퓨터 관련 개설 과목 후보

## 제외 대상

사이버대, 방송통신대, 전문대, 대학원 전용 공고, 본교 재학생 전용 계절학기, 교류대학 전용, 협정대학 전용, 고등학생/중학생/초등학생 캠프, 단순 입시설명회, 취업박람회, 자격증 홍보만 있는 글은 낮은 등급 또는 제외 후보로 분류합니다.

## 설치

```bash
cd university-course-watcher
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

macOS/Linux:

```bash
cd university-course-watcher
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## .env 설정

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
DEBUG=false
TIMEZONE=Asia/Seoul
```

검색 API 관련 환경변수는 넣지 않습니다.

## 텔레그램 봇 만들기

1. 텔레그램에서 `@BotFather`를 엽니다.
2. `/newbot`으로 봇을 만들고 토큰을 발급받습니다.
3. 생성한 봇에게 아무 메시지나 보냅니다.
4. `https://api.telegram.org/bot<토큰>/getUpdates`를 브라우저에서 열어 `chat.id` 값을 확인합니다.
5. `.env` 또는 GitHub Secrets에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 저장합니다.

텔레그램 봇 토큰은 비밀번호와 같습니다.
절대 코드, README, 공개 GitHub 저장소, 채팅창에 직접 올리지 말고 `.env` 또는 GitHub Secrets에만 저장해야 합니다.
토큰이 노출되면 BotFather에서 즉시 Revoke 한 뒤 새 토큰을 발급받아야 합니다.

## 로컬 실행

```bash
python main.py --once
python main.py --region seoul
python main.py --region gyeonggi
python main.py --region incheon
python main.py --grade A
python main.py --keyword 시간제등록생
python main.py --dry-run
python main.py --debug
```

`--dry-run`은 저장과 텔레그램 알림 없이 콘솔 출력만 합니다. `--debug`는 D등급 후보를 `data/debug_results.json`에 저장합니다.

## 결과 파일

실행 후 다음 파일이 생성 또는 갱신됩니다.

- `data/results.csv`
- `data/results.json`
- `data/report.html`
- `data/seen_urls.json`
- `data/university_history.csv`
- `data/debug_results.json`

CSV/JSON 주요 필드는 `checked_at`, `university_name`, `region`, `city`, `title`, `url`, `notice_date`, `application_start_date`, `application_end_date`, `deadline_status`, `registration_score`, `external_score`, `computer_score`, `freshness_score`, `grade`, `external_applicant_status`, `computer_course_status`, `possible_departments`, `possible_computer_courses`, `attachment_urls`, `matched_keywords`, `reason`, `is_new`입니다.

`data/university_history.csv`는 매 실행마다 덮어쓰지 않고 누적됩니다. 같은 공고(`url`+`title`)는 `last_seen_at`과 변동 필드(접수일 등)만 갱신하고, 새 공고는 `first_seen_at`/`last_seen_at`과 함께 추가하여 장기 이력을 유지합니다.

## HTML 리포트

`data/report.html`을 브라우저로 열면 A/B/C 후보를 우선순위와 마감 상태 기준으로 확인할 수 있습니다. 리포트와 알림 하단에는 자동 검색 후보이며 최종 지원 가능 여부는 대학 공식 모집요강과 입학처 문의로 확인해야 한다는 문구가 포함됩니다.

## 대학 목록 수정

`config/universities.json`에서 대학을 추가, 삭제, 수정합니다.

```json
{
  "name": "아주대학교",
  "region": "gyeonggi",
  "region_name": "경기",
  "city": "수원",
  "domains": ["ajou.ac.kr"],
  "priority": 1,
  "notes": "시간제등록생 공고 이력 확인 우선"
}
```

## 게시판 URL 추가

`config/board_urls.json`에 대학 공식 게시판만 추가합니다.

```json
{
  "university_name": "아주대학교",
  "board_type": "입학처 공지",
  "url": "https://www.ajou.ac.kr/kr/ajou/notice.do",
  "enabled": true
}
```

게시판 구조가 대학마다 다르므로 MVP는 `requests + BeautifulSoup` 기반 범용 파서로 제목, URL, 날짜, 본문, 첨부 링크를 최대한 추출합니다.

### 게시판별 탐색 설정 (선택)

기본 탐색 깊이·선택자로 부족한 게시판은 board 항목에 다음 키를 추가해 개별 보정할 수 있습니다. 모든 키는 선택 사항이며, 없으면 기존 기본값을 사용합니다.

```json
{
  "university_name": "아주대학교",
  "board_type": "학사 공지",
  "url": "https://www.ajou.ac.kr/kr/ajou/notice.do?bbsNo=1000",
  "enabled": true,
  "max_links": 25,
  "pagination": {"param": "pageIndex", "start": 1, "count": 3, "step": 1},
  "list_pages": ["https://www.ajou.ac.kr/kr/ajou/notice.do?bbsNo=1000&pageIndex=4"],
  "selectors": {"list": "table.board-list tr", "body": ".view-content"}
}
```

- `max_links`: 이 게시판에서 열어볼 상세 공고 수 상한(기본값 대신 사용).
- `pagination`: 목록 URL의 `param` 값을 `start`에서 `step`씩 늘려 `count`개의 페이지를 순회합니다. 오프셋 방식은 `{"param": "article.offset", "start": 0, "step": 10, "count": 3}`처럼 지정합니다.
- `list_pages`: 규칙으로 표현하기 어려운 추가 목록 URL을 직접 나열합니다.
- `selectors`: 목록 컨테이너(`list`)와 상세 본문(`body`) CSS 선택자를 개별 지정합니다.

smoke-test(`--smoke-test`) 실행에서는 속도를 위해 `max_links`/`pagination`/`list_pages` 보정을 건너뛰고, `selectors`만 적용합니다.

## 키워드 수정

`config/keywords.json`에서 가점/감점 키워드와 컴퓨터 과목 후보를 수정합니다. 코드 안에 키워드를 하드코딩하지 않습니다.

## GitHub Actions

`.github/workflows/daily-check.yml`은 매일 00:00 UTC에 실행됩니다. 이는 한국시간 오전 9시입니다.

GitHub 저장소 Settings → Secrets and variables → Actions에서 다음 Secrets를 설정합니다.

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

워크플로 실행 결과로 `data/report.html`, `data/results.csv`, `data/results.json`이 artifact에 업로드됩니다.

기본 실행 주기는 하루 1회입니다. 모집철에는 수동으로 cron을 늘릴 수 있습니다.

- 5월~8월: 하루 2회
- 9월~11월: 하루 2회
- 12월~1월: 하루 2회

## 한계점

- JavaScript 렌더링 전용 게시판은 MVP에서 누락될 수 있습니다.
- HWP/HWPX 첨부는 본문 텍스트를 추출해 분류에 사용합니다. HWPX는 OWPML(zip+XML)에서 직접 추출하고, HWP 5.x는 `BodyText` 레코드 또는 `PrvText` 미리보기 스트림에서 추출합니다. 스캔 이미지 기반 문서나 비표준 구조는 부분 추출에 그칠 수 있습니다.
- 날짜 표현이 복잡한 공고는 `날짜확인필요`로 남길 수 있습니다.
- 자동 분류는 최종 지원 가능 여부를 확정하지 않습니다.

## 중요 고지

결과는 자동 검색 후보이며, 최종 지원 가능 여부는 대학 공식 모집요강 원문과 입학처 문의로 확인해야 합니다.

## 2026 후기 일반대학원 모집요강 감시

인서울 일반대학원 2026학년도 후기 모집요강/신입생 모집/입학전형 공고는 별도 모드로 감시합니다.

```bash
python main.py --once --watch graduate-admission --region seoul
python main.py --once --watch graduate-admission --region seoul --dry-run
python main.py --telegram-test-success
python main.py --telegram-test-empty
python validate_graduate_admission_boards.py
```

감시 대상 게시판은 `config/graduate_admission_boards.json`에서 관리합니다. 제목에 `2026`과 `후기`가 함께 있고, 본문 또는 첨부에서 `일반대학원`, `모집요강`, `신입생 모집`, `입학전형`, `전형일정`, `원서접수`, `2차`, `특별전형` 같은 신호가 확인될 때만 텔레그램 알림을 보냅니다. 학부, 편입, 특수대학원, 전문대학원 등으로 판단되는 공고는 제외합니다.

일부 학교는 공지 게시판이 아니라 상시 입학안내 페이지에 모집요강 PDF를 직접 게시합니다. 이런 경우 `graduate_admission_boards.json`에 `"scan_page": true`를 추가하면 해당 페이지 본문과 첨부 링크까지 직접 검사합니다. URL 상태는 `validate_graduate_admission_boards.py`로 확인하며, `status`가 200이어도 `keyword_hits`가 0이거나 `final_url`이 error/login/SSO 페이지면 설정 보정이 필요합니다.

GitHub Actions는 한국시간 오전 9시와 오후 7시에 실행되도록 `0 0 * * *`, `0 10 * * *` UTC cron을 사용합니다.

### 상태 저장 (state branch)

`seen_graduate_admission_urls.json`과 빈 요약 상태(`graduate_admission_summary_state.json`)는 `run_id` 기반 Actions cache 대신 전용 `watcher-state` 브랜치에 저장합니다. Actions cache는 키가 불변이고 약 7일간 접근이 없으면 제거되어 장기 상태가 유실될 수 있기 때문입니다.

- 잡 시작 시 `scripts/state_branch.sh restore`로 이전 상태를 내려받습니다(읽기 전용).
- 정기 실행 종료 시 `scripts/state_branch.sh save`로 상태를 오펀 커밋 1개로 강제 푸시합니다. 브랜치 히스토리는 항상 커밋 1개로 유지되어 비대해지지 않습니다.
- 워크플로 상단 `concurrency` 그룹으로 동일 ref의 실행을 직렬화하여 저장 경합을 막습니다.

### 게시판 URL 검증 자동화

`validate-boards` 잡이 정기 실행마다 `validate_graduate_admission_boards.py`를 돌려 대학원 입학 게시판 URL 상태를 점검하고, 결과를 GitHub Step Summary 표와 `data/board_validation.json`(artifact)로 남깁니다. `status`가 200이 아니거나, error/login/SSO로 리다이렉트되거나, 대학원 키워드가 검출되지 않는 게시판은 `⚠️`로 표시됩니다.

```bash
python validate_graduate_admission_boards.py                 # TSV (기존 호환)
python validate_graduate_admission_boards.py --json           # JSON 출력
python validate_graduate_admission_boards.py --report data/board_validation.json --summary
python validate_graduate_admission_boards.py --fail-on-error  # 문제 발견 시 종료 코드 1
```
