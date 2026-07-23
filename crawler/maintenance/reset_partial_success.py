# -*- coding: utf-8 -*-
"""
컴공 공지 알리미 - 부분 성공 공지 리셋 스크립트

터미널 로그를 보고 수작업으로 확인한, "이미지 여러 개 중 일부만 OCR 성공한" 공지들을
ocr_applied=False로 리셋해서 retry_failed_ocr.py가 다시 처리하도록 만든다.

주의: 이 스크립트를 실행한 뒤에는 반드시 retry_failed_ocr.py를 실행해서
      실제 재시도를 진행해야 함. 이 스크립트는 "표시만 리셋"하는 역할.
"""

import pandas as pd

RESULT_CSV = "cse_notices_with_content.csv"

# 터미널 로그에서 확인한 "일부만 성공한" 공지 제목들
# 다른 학기의 비슷한 제목 공지와 헷갈리지 않도록, 최대한 구체적인 문구로 매칭
PARTIAL_SUCCESS_KEYWORDS = [
    "2024-2학기 교내 신용카드수수료장학금",   # 이미지 2개 중 저작권 오탐으로 1개만 실패했던 공지
]


def main():
    df = pd.read_csv(RESULT_CSV)

    # 제목에 위 키워드 중 하나라도 포함되면 대상으로 선정
    mask = df["title"].astype(str).apply(
        lambda title: any(keyword in title for keyword in PARTIAL_SUCCESS_KEYWORDS)
    )

    matched = df[mask]

    print(f"찾은 공지: {len(matched)}개")
    for _, row in matched.iterrows():
        print(f"  - {row['title']}  (현재 ocr_applied={row['ocr_applied']})")

    if len(matched) == 0:
        print("\n일치하는 공지를 찾지 못했어요. 제목이 정확한지 확인해주세요.")
        return

    if len(matched) != len(PARTIAL_SUCCESS_KEYWORDS):
        print(f"\n[주의] 키워드는 {len(PARTIAL_SUCCESS_KEYWORDS)}개인데 찾은 공지는 {len(matched)}개예요.")
        print("혹시 중복으로 찾혔거나, 못 찾은 키워드가 있는지 위 목록을 확인해주세요.")

    # 확인 후 진행 여부 묻기
    answer = input("\n위 공지들을 재시도 대상으로 리셋할까요? (y/n): ")
    if answer.strip().lower() != "y":
        print("취소했어요. 아무것도 변경되지 않았어요.")
        return

    # ocr_applied를 False로 리셋 -> retry_failed_ocr.py가 다시 대상으로 인식함
    df.loc[mask, "ocr_applied"] = False

    df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n완료! {len(matched)}개 공지를 재시도 대상으로 리셋했어요.")
    print("이제 python retry_failed_ocr.py 를 실행하면 이 공지들부터(및 기존 미완료분과 함께) 다시 처리돼요.")


if __name__ == "__main__":
    main()