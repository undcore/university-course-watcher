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
- `data/notice_state.json`
- `data/seen_graduate_admission_urls.json`
- `data/graduate_admission_summary_state.json`
- `data/university_history.csv`
- `data/debug_results.json`

CSV/JSON 주요 필드는 `checked_at`, `university_name`, `region`, `city`, `title`, `url`, `notice_date`, `application_start_date`, `application_end_date`, `deadline_status`, `registration_score`, `external_score`, `computer_score`, `freshness_score`, `grade`, `external_applicant_status`, `computer_course_status`, `possible_departments`, `possible_computer_courses`, `attachment_urls`, `matched_keywords`, `reason`, `is_new`입니다.

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

## 키워드 수정

`config/keywords.json`에서 가점/감점 키워드와 컴퓨터 과목 후보를 수정합니다. 코드 안에 키워드를 하드코딩하지 않습니다.

## GitHub Actions

`.github/workflows/daily-check.yml`은 한국시간 월요일부터 금요일까지 오전 9시와 오후 7시에 실행됩니다. 코드 push는 감시 워크플로를 시작하지 않으며, 주말에는 사용자가 직접 요청한 수동 실행만 허용합니다.

GitHub 저장소 Settings → Secrets and variables → Actions에서 다음 Secrets를 설정합니다.

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

워크플로 실행 결과로 `data/report.html`, `data/results.csv`, `data/results.json`이 저장소에 최신 파일로 커밋되고 artifact에도 업로드됩니다.

정기 실행 후 텔레그램 일일 점검 보고의 `보고서 확인`에 바로보기 링크가 포함됩니다. 보통은 이 링크를 열면 되고, zip artifact를 직접 받을 필요는 없습니다.

`report.html`은 GitHub Actions의 정기 실행(`schedule`) 또는 수동 실행(`workflow_dispatch`, `telegram_test=none`) 결과에서 확인합니다.

artifact로 직접 확인해야 할 때의 경로:

1. GitHub 저장소의 Actions 탭을 엽니다.
2. `Daily university notice check`에서 최신 정기 실행 또는 직접 실행한 수동 실행을 클릭합니다.
3. 화면 하단 `Artifacts`에서 `university-course-watcher-results`를 다운로드합니다.
4. 압축을 풀고 `report.html`을 엽니다.

기본 실행 주기는 평일 하루 2회입니다. 예약 실행이 지연되더라도 실제 시작 시점의 한국 요일이 토요일 또는 일요일이면 감시 작업을 건너뜁니다.

- 5월~8월: 하루 2회
- 9월~11월: 하루 2회
- 12월~1월: 하루 2회

## 한계점

- JavaScript 렌더링 전용 게시판은 MVP에서 누락될 수 있습니다.
- HWP/HWPX는 텍스트 추출 대신 링크만 저장합니다.
- 날짜 표현이 복잡한 공고는 `날짜확인필요`로 남길 수 있습니다.
- 자동 분류는 최종 지원 가능 여부를 확정하지 않습니다.

## 중요 고지

결과는 자동 검색 후보이며, 최종 지원 가능 여부는 대학 공식 모집요강 원문과 입학처 문의로 확인해야 합니다.

## 일반대학원 모집요강 감시

일반대학원 모집요강/신입생 모집/입학전형 공고(전기·후기·1차/2차/추가모집 포함)는 별도 모드로 감시합니다. 대학 게시판 크롤링과 함께 유웨이어플라이/진학사어플라이 원서접수 포털에서 접수중인 일반대학원 목록도 수집합니다(포털 항목은 다이제스트 한 통으로 알림).

```bash
python main.py --once --watch graduate-admission --region seoul
python main.py --once --watch graduate-admission --region seoul --dry-run
python main.py --telegram-test-success
python main.py --telegram-test-empty
python validate_graduate_admission_boards.py
```

감시 대상 게시판은 `config/graduate_admission_boards.json`에서 관리합니다. 제목에 학년도(2026/2027)와 모집 신호(모집요강, 원서접수, 전형, 차수 등)가 함께 있고, 본문 또는 첨부에서 `일반대학원` 관련 신호가 확인될 때만 텔레그램 알림을 보냅니다. 전기/후기/1차/2차/추가모집 차수는 알림의 확인 키워드로 표시됩니다. 학부, 편입, 특수대학원, 전문대학원, 그리고 제목에 `외국인`이 있는 전형은 제외합니다.

일부 학교는 공지 게시판이 아니라 상시 입학안내 페이지에 모집요강 PDF를 직접 게시합니다. 이런 경우 `graduate_admission_boards.json`에 `"scan_page": true`를 추가하면 해당 페이지 본문과 첨부 링크까지 직접 검사합니다. URL 상태는 `validate_graduate_admission_boards.py`로 확인하며, `status`가 200이어도 `keyword_hits`가 0이거나 `final_url`이 error/login/SSO 페이지면 설정 보정이 필요합니다.

GitHub Actions는 한국시간 월요일부터 금요일까지 오전 9시와 오후 7시에 실행되도록 `0 0 * * 1-5`, `0 10 * * 1-5` UTC cron을 사용합니다. 알림 이력과 fingerprint 상태는 결과 보고서와 함께 저장소에 커밋하므로 Actions cache가 만료되어도 같은 공고를 반복 알림하지 않습니다. HTTP 조건부 요청 상태만 재생성 가능한 Actions cache로 관리합니다.
