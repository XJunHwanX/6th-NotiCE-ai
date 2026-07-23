"""
컴공 공지 알리미 - 공지 제목 카테고리 분류 함수 (최종 버전)

모델: klue/bert-base 파인튜닝 (model_final_v5)
- title(제목)만 사용, max_length=64
- 클래스 가중치 적용 (불균형 카테고리 보정, 기타 카테고리는 0.7로 별도 캡)
- 데이터 증강 + 취업/인턴 ↔ 학생활동 경계 라벨 재정리 완료

분류 방식: confidence threshold 기반 + 키워드 안전망
- 확신도(top-1 확률)가 threshold 이상이면 카테고리 1개 확정
- threshold 미만이면 상위 2개 카테고리를 함께 반환 (애매한 경우 놓치지 않기 위함)
- 제목에 대회/공모전 관련 키워드가 있는데 결과에 빠져 있으면 안전망으로 추가
- "전체 공지" 화면에는 분류 결과와 무관하게 항상 모든 공지가 노출되어야 함
  (이 분류 결과는 카테고리별 알림 발송에만 사용, 완전한 필터링 근거로 쓰지 않을 것)

사용법:
    from notice_classifier import load_classifier, predict_category

    classifier = load_classifier("pipeline/model_final_v5")
    categories = predict_category(classifier, "2026학년도 장학금 신청 안내")
    # -> ["장학/근로"]  (확신 있는 경우, 리스트 안에 1개)
    # -> ["학생활동", "취업/인턴"]  (애매한 경우, 리스트 안에 2개)
"""

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MAX_LENGTH = 64
DEFAULT_THRESHOLD = 0.7

# 대회/공모전 안전망용 키워드
# 주의: "공모전"이 들어가도 실제로는 참가지원/박람회 성격인 경우가 있어
# 강제 확정이 아니라 "후보에 추가"하는 보수적인 방식으로만 사용
CONTEST_KEYWORDS = ['공모전', '경진대회', '해커톤', '챌린지']


def load_classifier(model_path: str):
    """
    모델과 토크나이저를 로드합니다. 서버 시작 시 한 번만 호출하세요.

    Args:
        model_path: 로컬 모델 폴더 경로 (예: "pipeline/model_final_v5")

    Returns:
        dict: {"model": ..., "tokenizer": ..., "device": ...}
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model.to(device)
    model.eval()

    return {"model": model, "tokenizer": tokenizer, "device": device}


def apply_safety_net(title: str, categories: list, probs_by_category: dict) -> list:
    """
    모델 예측 결과에 키워드 기반 안전망을 적용합니다.
    최대 2개 카테고리로 제한하며, 안전망으로 카테고리가 추가될 경우
    기존 후보 중 확률이 더 낮은 것을 대신 탈락시킵니다.

    Args:
        title: 공지 제목 텍스트
        categories: 모델이 반환한 카테고리 리스트 (1개 또는 2개), 확률 높은 순 정렬됨
        probs_by_category: {카테고리명: 확률} 딕셔너리 (정렬 기준용)

    Returns:
        list[str]: 안전망 적용 후 카테고리 리스트 (최대 2개)
    """
    result = list(categories)

    if any(kw in title for kw in CONTEST_KEYWORDS) and "대회/공모전" not in result:
        if len(result) < 2:
            # 아직 자리가 남으면 그냥 추가
            result.append("대회/공모전")
        else:
            # 이미 2개 꽉 찼으면 확률 더 낮은 것을 대회/공모전으로 교체
            lowest = min(result, key=lambda c: probs_by_category[c])
            result.remove(lowest)
            result.append("대회/공모전")

    return result


def predict_category(classifier: dict, title: str, threshold: float = DEFAULT_THRESHOLD) -> list:
    """
    공지 제목을 받아 카테고리를 예측합니다. 최대 2개까지만 반환합니다.
    """
    model = classifier["model"]
    tokenizer = classifier["tokenizer"]
    device = classifier["device"]

    inputs = tokenizer(
        title,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
        max_length=MAX_LENGTH,
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    probs = F.softmax(outputs.logits, dim=1)[0]
    top2_probs, top2_ids = torch.topk(probs, 2)

    top1_conf = top2_probs[0].item()
    id2label = model.config.id2label

    if top1_conf >= threshold:
        result = [id2label[top2_ids[0].item()]]
        probs_by_category = {id2label[top2_ids[0].item()]: top2_probs[0].item()}
    else:
        cat1, cat2 = id2label[top2_ids[0].item()], id2label[top2_ids[1].item()]
        result = [cat1, cat2]
        probs_by_category = {cat1: top2_probs[0].item(), cat2: top2_probs[1].item()}

    result = apply_safety_net(title, result, probs_by_category)

    return result


# ---- 사용 예시 ----
if __name__ == "__main__":
    classifier = load_classifier("pipeline/model_final_v5")

    test_titles = [
        "2026학년도 2학기 장학금 신청 안내",
        "[특강] Apple Engineer 초청 특강",
        "2026 전국 대학생 AI 챌린지 참가팀 모집",
        "[대학교육혁신사업단] 해외공모전, 박람회, 전시회 참가지원 계획 공고",
    ]

    for title in test_titles:
        result = predict_category(classifier, title)
        print(f"{title} -> {result}")