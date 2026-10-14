# POST SET Edition 구현 기록

## 기존 구조와 유지한 기능

기존 버전은 `items.json`의 이미지별 제목·Caption·스타일과 v1 API를 사용했습니다. Windows 실행기, `.env` 키 설정, 로컬 업로드/검증, Pillow 합성, 기존 ZIP 생성·복원, 오류 격리와 테스트 26개를 유지했습니다. 구형 화면은 `/legacy`에 보존했습니다.

새 UI는 `/api/v2`와 `post_project.json`을 사용합니다. 기존 v1 문서는 `CODEX_PROMPT_1028FALL_STUDIO.md`에 그대로 보관합니다. 현재 동작은 `README_KO.md`를 기준으로 합니다.

## 단계별 구현

| PHASE | 구현 | 검증 |
|---|---|---|
| 1 | A/B/C 독립 POST SET 모델 | 빈 구조·SET 간 독립성 |
| 2 | SOURCE 1–10장, 유효 형식, 삭제·Drag & Drop 순서 | 11번째 이미지 거부, 손상 파일, SOURCE 불변 |
| 3 | 언어별 VERSION과 SOURCE 분리 | KO/JA 보존, 디자인 객체 독립, SOURCE 변경 시 이전 버전 보존 |
| 4 | 공동 이미지·텍스트 분석, HOOK 5개, Story·Caption | 전체 입력·슬라이드 수/순서, 1/3/5/10장, 부분 재생성 |
| 5 | 대상 언어 SOURCE 기반 재구성 | 다른 언어 문구 입력 없이 현지화, 재분석, 사실성 정책 |
| 6 | 로컬 언어 Variation | ON 픽셀 차이, OFF 동일 출력, 원본 해시 유지, 작은 변형 범위 |
| 7 | A/B/C Workspace, 비율·맞춤·디자인·로고 | 렌더링·편집 API·실제 Chromium 조작 |
| 8 | v2 프로젝트 복원, v1 ZIP 마이그레이션, 세션 유지 | 모든 언어/스타일/원본 보존, 손상 ZIP·경로 거부, 재시작/복원 |
| 9 | PNG, 버전/SET/전체/프로젝트 ZIP | JPEG 크기, Caption, 범위 필터와 전체 복원 |

## 주요 파일

- `services/config.py`: `LANGUAGES`, SET ID, SOURCE 제한.
- `services/design_config.py`: 디자인·비율·맞춤 기본값과 검증.
- `services/post_model.py`: SET·SOURCE·VERSION 모델과 구형 데이터 이관.
- `services/post_api.py`: 새 REST API. 기존 `app.py`의 로컬 접근·CSRF·세션 잠금을 공유.
- `services/ai_service.py`: 기존 단일 이미지 AI 기능 + 여러 SOURCE 분석·Carousel 생성·부분 재생성.
- `services/fact_policy.py`: 미검증 주장 취급과 미래 FactCheck 제공자 경계.
- `services/variation_service.py`: 저장 가능한 로컬 변형과 선택적 AI 제공자 확장점.
- `services/image_service.py`: 기존 정사각형 합성 + 새 비율·Fit/Blur·문구 디자인 렌더링.
- `services/post_archive.py`: 다운로드 범위, 휴대 가능한 JSON, ZIP 검증·원본 복원.
- `ui/static/post-app.js`, `post.css`, `ui/templates/index.html`: 새 SET 화면.
- `tests/test_post_*.py`, `tests/browser/`: 단계별 회귀·브라우저 검증.

## 데이터 구조

```text
PROJECT (schema_version: 2)
  assets: {source_id: {id, name, file}}
  settings: language, style_sample, default_style,
            aspect_ratio, fit_mode, variation_enabled
  logo: mode, asset, size, position
  sets:
    A / B / C:
      source_ids: 현재 원본 순서
      source_revision: 원본 구성 변경 이력
      logo: 프로젝트 상속 / 자체 로고 / 없음
      versions:
        ko / ja / en / ...:
          language, hook_candidates[5], hook, caption
          source_revision, analysis, options
          slides[]:
            id, source_id, role, text, style, variation
```

원본 정보는 언어별 문구와 분리합니다. 버전의 슬라이드는 생성 시 SOURCE를 참조하며 순서를 독립적으로 보관합니다. SOURCE 순서/목록이 달라져도 이전 버전을 암묵적으로 변경하지 않습니다. 삭제된 SOURCE도 기존 버전이 참조하면 보존합니다.

새 언어 생성은 원본들을 다시 분석하며 기존 언어 결과를 번역 입력으로 사용하지 않습니다. 같은 언어의 전체 재생성만 성공 후 교체합니다. 분석/생성 오류 때 이전 버전은 그대로 유지하고 SET 오류만 기록합니다. 개별 재생성은 해당 필드·슬라이드만 변경합니다.

## Variation과 사실성

언어와 SOURCE ID 기반의 로컬 seed로 미세 zoom·crop 위치·톤·배경 blur 값을 생성합니다. 재생성은 새 seed를 사용하며 원본 파일을 수정하지 않습니다. OFF는 이 값을 적용하지 않습니다. AI 이미지를 합성하거나 피사체를 바꾸는 기능은 연결하지 않았습니다.

SOURCE 속 뉴스·연구 주장은 미검증 자료로 취급합니다. 분석의 `fact_check.verified`는 항상 false이며 외부 검증이 수행되었다고 표시하지 않습니다. OCR은 별도 로컬 엔진이 아니라 OpenAI의 이미지 입력에서 읽을 수 있는 문구를 분석하도록 요청합니다. 읽기 어려운 문구는 추정하지 않도록 지시합니다.

AI 응답의 언어적 자연스러움과 사실성은 프롬프트만으로 보증할 수 없습니다. 실제 OpenAI 호출과 콘텐츠 품질의 실기 검토는 미검증입니다.

## 저장·복원 경계

ZIP의 경로를 그대로 추출하지 않습니다. 메타데이터와 참조를 검증하고 이미지 파일을 임시 폴더에서 확인한 뒤 새 파일명으로 배치합니다. 검증 실패는 현재 프로젝트를 교체하지 않습니다. 프로젝트 ZIP은 원본·로고·모든 편집 설정을 포함합니다. 단독 JSON은 원본 바이트가 없으므로 휴대 가능한 완전 백업이 아닙니다.

프로젝트 ZIP의 업로드 및 압축 해제 용량은 2GB, 메타데이터는 2MB입니다. 배포 ZIP에는 `.env`, 세션 서명 키, 작업 사진, 가상환경을 포함하지 않습니다. 기존 v1 30장 초과 ZIP은 원본을 보존하며 분할 필요를 안내합니다. 긴 기존 Caption도 메타데이터에서 잘라내지 않습니다.
