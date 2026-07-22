# 6th-NotiCE-ai
# 컴공 공지 알리미 (NotiCE)

홍익대학교 컴퓨터공학과 공지사항을 크롤링하고, AI로 카테고리를 자동 분류해
학생들에게 필요한 공지를 웹 푸시로 알려주는 서비스입니다.

## 프로젝트 구조
6th-NotiCE-ai/
├── crawler/ # 공지 크롤링 스크립트
│ ├── crawl_cse.py # 컴공과 게시판 크롤링
│ ├── crawl_hongik.py # 홍익대 전체 게시판 크롤링
│ ├── crawl_hongik_general.py
│ ├── crawl_content.py # 본문 크롤링
│ ├── crawl_job_board_titles.py
│ ├── merge_labels.py # 라벨 병합
│ └── upload_supabase.py # Supabase 업로드
├── data/ # 크롤링/전처리 데이터
│ └── preprocess.py # 중복 제거, 결측치 확인
├── backend/
│ └── notice_classifier.py # 분류 모델 로드 및 예측 함수
├── pipeline/
│ ├── pipeline.py # 크롤링 → 분류 → DB저장 파이프라인
│ ├── model_final_v5/ # 최종 학습된 분류 모델 (git 미포함, 아래 참고)
│ └── .env # Supabase 등 환경변수 (git 미포함)
└── model/ # 모델 백업용 폴더

## ⚠️ 모델 파일 다운로드 (필수)

용량 문제로 `model_final_v5` 폴더는 git에 포함되어 있지 않습니다.
아래 구글드라이브 링크에서 다운로드한 뒤 `pipeline/model_final_v5/` 경로에 넣어주세요.

## 모델 경로
📁 [(https://drive.google.com/drive/folders/1cj32IOJXgLEPJz7RZRkU6_H5g5FNsPQ-?usp=drive_link)]

폴더 안에는 다음 파일들이 있어야 합니다:
`config.json`, `model.safetensors`, `tokenizer.json`, `tokenizer_config.json`, `label_mapping.json`

## 분류 모델 (model_final_v5)

- **베이스 모델**: `klue/bert-base` 파인튜닝
- **입력**: 공지 제목만 사용 (max_length=64)
- **카테고리 (8개)**: 학사, 졸업, 대학원/연구, 학생활동, 장학/근로, 기타, 대회/공모전, 취업/인턴
- **학습 데이터**: 804개 (컴공과 220개 + 홍익대 전체 게시판에서 사람이 검토·재분류한 데이터)
- **불균형 보정**: 클래스 가중치 적용 (단, `기타` 카테고리는 0.7로 별도 캡 — 소수 표본에 과도한 가중치가 걸리는 것을 방지)
- **성능**: accuracy 약 94%, macro F1 약 0.81 (val 161개 기준)

### 분류 방식

1. 모델이 8개 카테고리에 대한 확률을 계산합니다.
2. 최고 확률이 **threshold(0.7) 이상**이면 → 카테고리 1개 확정
3. threshold 미만이면 → 확신이 낮다고 판단해 **상위 2개 카테고리**를 함께 반환 (공지를 놓치지 않기 위한 안전장치)
4. **키워드 안전망**: 제목에 "공모전", "경진대회", "해커톤", "챌린지" 등이 포함돼 있는데 예측 결과에 `대회/공모전`이 빠져 있으면, 확률이 더 낮은 카테고리를 대신 빼고 `대회/공모전`을 추가합니다. (최종 결과는 항상 최대 2개로 제한)

> 이 분류 결과는 **알림 발송 대상 선정**에만 쓰입니다. "전체 공지" 화면에는 분류 결과와 무관하게 모든 공지가 항상 노출되어야 합니다.

## 사용법

```python
from backend.notice_classifier import load_classifier, predict_category

classifier = load_classifier("pipeline/model_final_v5")
categories = predict_category(classifier, "2026학년도 장학금 신청 안내")
# -> ["장학/근로"]
```

## 파이프라인 실행

```bash
python pipeline/pipeline.py
```

`pipeline/.env`에 아래 값이 필요합니다:
SUPABASE_URL=...
SUPABASE_KEY=...

## 다음 작업 (TODO)

- [x] GitHub Actions 파이프라인 자동화 워크플로우 작성 완료
      (dev 브랜치 머지 후 실제 실행 테스트 필요 — 현재 feature 브랜치에만 있어 Actions 탭에서 수동 실행 확인 불가)
- [ ] 크롤링 시점에 청크 분할 + 임베딩까지 통합 (현재는 별도 프로세스)
- [ ] 소수 카테고리(대학원/연구, 대회/공모전) 데이터 추가 확보