# 1028FALL Studio 검증 결과

검증일: 2026-10-14 (한국 시간)

## 실제 실행 결과

- Linux / Python 3.12.14 / Pillow 11.3.0 / Flask 3.1.2 환경에서 자동 테스트 **26개 PASS**.
- JPG·PNG·WEBP 중앙 crop 및 1080×1080 PNG 출력 PASS.
- 한글·일본어 제목의 실제 픽셀 합성, 긴 제목 줄바꿈/자동 축소 PASS.
- 투명 로고의 비율·위치, 그라데이션 0/100% 경계 PASS.
- ZIP의 이미지·원본·캡션 TXT/JSON·프로젝트 설정 보존 PASS.
- 프로젝트 ZIP 복원 시 제목·본문·언어·스타일·로고 유지 PASS.
- 악성 ZIP 경로, 손상된 ZIP, 위장 형식 업로드 거부 및 기존 작업 보존 PASS.
- 한글·공백 경로 파일 읽기/쓰기와 해당 경로에서 실제 서버 기동 PASS (Linux).
- 사용 중인 8765 포트를 피해 대체 포트로 실행 및 HTML/API 응답 PASS.
- 100장 순차 업로드 및 작업 메타데이터 유지 PASS.
- API 키 누락 데모 모드, 수동 편집·저장, 세션 분리, CSRF 보호 PASS.
- AI 분석/생성 실패 시 기존 문구 보존 및 다른 이미지 작업 유지 PASS (AI 응답 모의).
- Chromium 실제 브라우저에서 3개 형식 업로드, 한글 편집, 글자 크기·위치·그라데이션·로고 변경, PNG/ZIP 다운로드, 새로고침, ZIP 불러오기, 임시파일 정리 PASS. JavaScript 실행 오류 없음.
- pip check: No broken requirements found.

실행 명령: `.venv/bin/python -m unittest discover -s tests -v`

## 아직 검증하지 않은 항목

- 실제 Windows 10/11에서 START_HERE.cmd 더블클릭, Python 미설치/설치 상태, 한글 사용자 계정, 바탕화면 경로, 브라우저 자동 열기.
- 실제 OpenAI 키를 사용한 유료 이미지 분석/문구 생성, API 요금·모델 접근 권한·실제 다국어 문구 품질.
- 100장 전체에 대한 유료 AI 일괄 요청 및 대용량 ZIP의 장시간 성능.

Windows 배치파일은 UTF-8/CRLF이며 자체 폴더 이동, 인용한 경로, py/python 검사, 가상환경 생성·활성화, pip 설치, 오류 pause를 구현했습니다. 코드 검토와 Linux의 유니코드 경로 테스트는 Windows 실기 검증을 대신하지 않습니다.

AI 모의 테스트 결과를 실제 API 호출 성공으로 해석하지 마세요. 실제 키는 사용자의 로컬 setup_api_key.cmd로 설정하며 소스·배포 ZIP에 포함하지 않습니다.
