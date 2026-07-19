"""
컴공 공지 알리미 - 공지 제목 카테고리 분류 함수 (최종 버전)

모델: klue/bert-base 파인튜닝
- title(제목)만 사용, max_length=64
- 클래스 가중치 적용 (불균형 카테고리 보정)
- 데이터 증강: 취업/인턴(크롤링 50개), 대회/공모전(합성 30개), 대학원/연구(합성 25개)

분류 방식: confidence threshold 기반
- 확신도(top-1 확률)가 threshold 이상이면 카테고리 1개 확정
- threshold 미만이면 상위 2개 카테고리를 함께 반환 (애매한 경우 놓치지 않기 위함)
- "전체 공지" 화면에는 분류 결과와 무관하게 항상 모든 공지가 노출되어야 함
  (이 분류 결과는 카테고리별 알림 발송에만 사용, 완전한 필터링 근거로 쓰지 않을 것)

사용법:
    from notice_classifier import load_classifier, predict_category

    classifier = load_classifier("model_final_v3")
    categories = predict_category(classifier, "2026학년도 장학금 신청 안내")
    # -> ["장학/근로"]  (확신 있는 경우, 리스트 안에 1개)
    # -> ["학생활동", "취업/인턴"]  (애매한 경우, 리스트 안에 2개)
"""

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MAX_LENGTH = 64
DEFAULT_THRESHOLD = 0.6


def load_classifier(model_path: str):
    """
    모델과 토크나이저를 로드합니다. 서버 시작 시 한 번만 호출하세요.

    Args:
        model_path: 로컬 모델 폴더 경로 (예: "model_final_v3")

    Returns:
        dict: {"model": ..., "tokenizer": ..., "device": ...}
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model.to(device)
    model.eval()

    return {"model": model, "tokenizer": tokenizer, "device": device}


def predict_category(classifier: dict, title: str, threshold: float = DEFAULT_THRESHOLD) -> list:
    """
    공지 제목을 받아 카테고리를 예측합니다.

    Args:
        classifier: load_classifier()의 반환값
        title: 공지 제목 텍스트
        threshold: 확신도 기준값 (기본 0.6). 이 값 이상이면 카테고리 1개,
                   미만이면 상위 2개를 반환합니다.

    Returns:
        list[str]: 카테고리 이름 리스트 (1개 또는 2개)
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
        return [id2label[top2_ids[0].item()]]
    else:
        return [id2label[top2_ids[0].item()], id2label[top2_ids[1].item()]]


# ---- 사용 예시 ----
if __name__ == "__main__":
    classifier = load_classifier("model_final_v3")

    test_titles = [
        "2026학년도 2학기 장학금 신청 안내",
        "[특강] Apple Engineer 초청 특강",
        "2026 전국 대학생 AI 챌린지 참가팀 모집",
    ]

    for title in test_titles:
        result = predict_category(classifier, title)
        print(f"{title} -> {result}")