# 1028FALL Studio POST SET Edition 검증 결과

검증일: 2026-10-14 (한국 시간)

## 자동 테스트: 65개 PASS

실행: `.venv/bin/python -m unittest discover -s tests -v`

Linux / Python 3.12.14 / Flask 3.1.2 / Pillow 11.3.0에서 기존 테스트 26개와 신규 테스트 39개가 통과했습니다.

- A/B/C 독립 구조, SOURCE 10장 제한, 추가·삭제·순서, 기존 SOURCE 덮어쓰기 거부.
- 언어 버전의 SOURCE·문구 분리, KO/JA 보존, SOURCE 변경 시 이전 버전 참조 유지.
- 공동 이미지 입력·텍스트 분석 프롬프트, HOOK 5개, 정확한 Carousel 개수·순서, 1/3/5/10장 구성.
- SOURCE 기반 현지화 프롬프트와 미검증 주장 취급. 외부 사실 확인 완료로 표시하지 않음.
- HOOK/Caption/이미지 문구의 개별 재생성, 오류 때 기존 버전 보존.
- Variation 범위·언어별 값 차이, 실제 합성 픽셀 차이, OFF의 동일 출력, 원본 파일 해시 보존.
- 1:1·4:5·9:16 × Crop/Fit/Background Blur, 한글·일본어·긴 제목, Gradient 네 방향.
- 글자 색·폰트·행간·자간·Shadow·Outline·텍스트 배경, SET 로고와 출력 크기.
- SOURCE 순서와 다른 언어에 영향을 주지 않는 Carousel 순서 편집.
- ZIP 범위와 계층, JPEG·Caption, SOURCE·모든 언어·스타일·Variation 복원.
- v1 ZIP 이관, 기존 긴 Caption 보존, 30장 초과 거부, 악성 경로·손상/누락 파일 거부.
- 프로젝트 실패 시 기존 작업 보존, 공유하는 ZIP 용량 제한, 새 프로젝트 정리.
- 서버 프로세스를 실제 종료하고 재실행한 뒤 같은 클라이언트 세션의 작업 보존.
- 한글·공백 경로에서 실제 서버 실행, 사용 중인 포트 회피, HTML/웹 API 응답.
- 기존 API의 데모 모드·단일 합성·ZIP·100장 순차 업로드·CSRF·세션 분리·키 비노출 회귀 테스트.

`pip check`: No broken requirements found.

## 실제 Chromium 브라우저: PASS

`tests/browser/post-smoke.cjs`:

A/B/C SOURCE 관리, 세 형식 업로드, KO/JA 수동 버전 보존, SOURCE Drag & Drop, 텍스트 위치 드래그, 스타일·로고 편집, 개별 PNG와 네 ZIP 범위 다운로드, 전체 프로젝트 복원, 새로고침, 모바일 가로 넘침 검사. JavaScript 실행 오류 없음.

`tests/browser/post-ai-smoke.cjs` + `fixture_server.py`:

외부 호출을 모의 응답으로 대체한 서버에서 전체 AI 화면 흐름을 검증했습니다. SOURCE 재분석, HOOK 후보 선택, 스토리 순서, KO/JA/EN 동시 보존, Caption·현재 문구의 개별 재생성, 실패 시 이전 버전 유지, Variation ON/OFF. 실제 OpenAI 요청·비용 발생 없음.

Node/Playwright는 개발 검증에만 사용하며 앱 실행에는 필요하지 않습니다. 브라우저 스크립트의 `STUDIO_TEST_URL`, `STUDIO_FIXTURES`, `PLAYWRIGHT_MODULE`, `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 설정과 테스트 fixture 파일을 준비해야 합니다. AI fixture 서버는 8781 포트를 사용합니다.

## 미검증 및 제한

- 실제 Windows 10/11 더블클릭, 한글 사용자 계정·바탕화면 경로, Python 설치 감지, 브라우저 자동 열기.
- 실제 OpenAI 모델 접근·인증·요금·이미지 OCR 정확도·다국어 콘텐츠 품질.
- AI Image Variation API와 Web Fact Check는 연결하지 않았습니다. 현재 이미지 Variation은 로컬 처리입니다.
- 선택한 Font/Weight가 설치되지 않으면 가장 가까운 시스템 CJK 폰트를 사용합니다.
- 최대 용량(2GB) 프로젝트를 실제 생성/복원하는 장시간 성능은 미검증입니다. 용량 한계의 거부 로직은 작은 테스트 임계값으로 검증했습니다.

Windows 배치파일은 기존 UTF-8/CRLF·따옴표·자체 폴더·가상환경·오류 pause 동작을 유지했습니다. Linux의 Unicode 경로 테스트와 코드 검토는 Windows 실기 검증을 대신하지 않습니다. 모의 AI 테스트를 실제 API 호출이나 자연스러운 콘텐츠 품질 보증으로 해석하지 마세요.
