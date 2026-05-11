# 🎬 YouTube AI Subtitle Generator

YouTube 동영상에서 자동으로 자막을 생성하고 번역하는 Chrome 확장 프로그램입니다.

**기술 스택:**
- 🎵 **yt-dlp**: YouTube 오디오 추출
- 🎤 **ElevenLabs Scribe**: 음성 인식 (STT)
- 🤖 **Google Gemini**: AI 번역

## 📁 프로젝트 구조

```
youtube-subtitle-generator/
├── chrome-extension/          # Chrome 확장 프로그램
│   ├── manifest.json          # Extension manifest (V3)
│   ├── popup.html             # 팝업 UI
│   ├── popup.css              # 팝업 스타일
│   ├── popup.js               # 팝업 로직
│   ├── content.js             # YouTube 페이지 스크립트
│   ├── content.css            # 자막 오버레이 스타일
│   ├── background.js          # Service Worker (Manifest V3 필수 구성요소)
│   └── icons/                 # 확장 프로그램 아이콘
│
├── backend/                   # Python 백엔드 서버
│   ├── main.py                # FastAPI 진입점 (app, CORS, 라우터 등록)
│   ├── config.py              # 환경 변수 및 의존성 검사
│   ├── schemas.py             # Pydantic 모델
│   ├── helpers.py             # 공용 헬퍼 (Gemini 호출, 경로 검증, 언어 매핑)
│   ├── state.py               # Job 상태/큐/TTL
│   ├── pipeline.py            # 파이프라인 + Job worker
│   ├── routers/               # APIRouter 모듈
│   │   ├── health.py          # /health
│   │   ├── extract.py         # /extract
│   │   ├── transcribe.py      # /transcribe
│   │   ├── translate.py       # /translate
│   │   ├── jobs.py            # /generate, /jobs/{id}
│   │   └── subtitles.py       # /subtitles/{id}, /cleanup/{id}
│   ├── requirements.txt       # Python 의존성
│   └── .env.example           # 환경 변수 템플릿
│
└── README.md
```

## 🚀 설치 방법

### 1. 백엔드 서버 설정

#### 사전 요구사항
- Python 3.10+
- Node.js (yt-dlp의 YouTube JS 챌린지 해결에 필요)
- ffmpeg (오디오를 mp3로 변환, 필수)

#### 설치 및 실행

```bash
# 1. backend 디렉토리로 이동
cd backend

# 2. 가상환경 생성 (권장)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. yt-dlp 설치 (EJS 포함)
pip install "yt-dlp[default]"

# 5. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 API 키를 입력하세요

# 6. 서버 실행
python main.py
```

서버가 `http://localhost:8000`에서 실행됩니다.

### 2. Chrome 확장 프로그램 설치

1. Chrome 브라우저에서 `chrome://extensions/` 열기
2. 우측 상단의 "개발자 모드" 활성화
3. "압축해제된 확장 프로그램을 로드합니다" 클릭
4. `chrome-extension` 폴더 선택

## 🔑 API 키 설정

### ElevenLabs API 키
1. [ElevenLabs](https://elevenlabs.io) 계정 생성
2. [API Settings](https://elevenlabs.io/app/settings/api-keys)에서 API 키 생성
3. `.env` 파일에 `ELEVENLABS_API_KEY` 설정

### Google Gemini API 키
1. [Google AI Studio](https://aistudio.google.com) 접속
2. [API Keys](https://aistudio.google.com/apikey)에서 API 키 생성
3. `.env` 파일에 `GEMINI_API_KEY` 설정

## 📖 사용 방법

1. 백엔드 서버가 실행 중인지 확인
2. YouTube 동영상 페이지로 이동
3. 확장 프로그램 아이콘 클릭
4. 소스/타겟 언어 선택
5. 저장 경로 설정 (결과 JSON이 저장될 디렉토리)
6. "Generate Subtitles" 버튼 클릭
7. 완료 후 "Show" 버튼으로 영상 위에 자막 표시

### 이미 생성된 자막 파일 불러오기 (오프라인)

백엔드 서버 없이도 이전에 저장된 자막 JSON 파일을 사용할 수 있습니다:

1. "Load from File" 버튼 클릭
2. 저장된 `{video_id}_translation_{lang}.json` 파일 선택
3. 자막이 바로 로드되며 Show 버튼으로 영상 위에 표시

## 🔧 API 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/health` | GET | 서버 상태 확인 |
| `/generate` | POST | 자막 생성 파이프라인 시작 (큐 순차 처리) |
| `/jobs/{job_id}` | GET | Job 진행 상태 조회 |
| `/jobs/{job_id}` | DELETE | Job 삭제/취소 |
| `/extract` | POST | YouTube 오디오 추출 |
| `/transcribe` | POST | 음성 인식 (ElevenLabs) |
| `/translate` | POST | 번역 (Gemini) |
| `/subtitles/{video_id}` | GET | 저장된 자막 조회 (사용자 경로 우선) |
| `/cleanup/{video_id}` | DELETE | 임시 파일 정리 |

## 🌐 지원 언어

**음성 인식**: 99개 언어 (ElevenLabs Scribe v1)
- 영어, 한국어, 일본어, 중국어, 스페인어, 프랑스어, 독일어 등

**번역**: Gemini AI로 모든 주요 언어 간 번역 지원

## ⚠️ 주의사항

- 긴 동영상은 처리 시간이 오래 걸릴 수 있습니다
- ElevenLabs API는 사용량에 따라 요금이 부과됩니다
- Google Gemini API도 사용량에 따라 요금이 부과됩니다
- 저작권이 있는 콘텐츠 사용 시 해당 법률을 준수하세요

## 🐛 문제 해결

### 서버 연결 실패
```bash
# 서버가 실행 중인지 확인
curl http://localhost:8000/health
```

### yt-dlp 오류

**HTTP 403 Forbidden:**
- yt-dlp와 EJS를 최신으로 업데이트: `pip install -U "yt-dlp[default]"`
- Node.js가 설치되어 있는지 확인: `node --version`
- YouTube 로그인된 브라우저의 쿠키가 필요 (서버에서 `--cookies-from-browser chrome` 사용 중)

```bash
# yt-dlp 업데이트
pip install -U "yt-dlp[default]"

# ffmpeg 설치 확인
ffmpeg -version

# ffmpeg 설치 (macOS)
brew install ffmpeg
```

### API 키 오류
- `.env` 파일에 API 키가 올바르게 설정되어 있는지 확인
- API 키에 공백이나 따옴표가 없는지 확인

## 📝 라이선스

MIT License
