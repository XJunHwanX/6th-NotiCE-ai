# -*- coding: utf-8 -*-
"""
컴공 공지 알리미 - 마지막 남은 공지 1건 수동 처리

자동 OCR이 계속 실패한 "2024-2학기 교내 신용카드수수료장학금" 공지의
이미지 내용을 수동으로 확인해서 body_text에 직접 추가한다.
"""

import pandas as pd

RESULT_CSV = "cse_notices_with_content.csv"
TARGET_TITLE_KEYWORD = "2024-2학기 교내 신용카드수수료장학금"

MANUAL_TEXT = """장학금명: 신용카드수수료장학금
신청대상: 본인 및 생계를 같이 하는 가족이 2024년 6월 1일 이후에 신용회복/개인회생/파산/면책이 진행중이거나 결정을 받은 경우, 운영사업체가 부도/파산된 경우, 중증질병(암 등)이나 지속적인 치료를 요하는 질병 또는 상해(교통/일반)를 입은 경우, 화재 등의 재해를 입은 경우 중 하나에 해당하고 그 사실을 입증하는 서류를 제출한 학부 재학생 (신용카드수수료장학금은 재학중 3회까지만 수혜 가능함). 직전학기 이수학점이 15학점 이상이고 성적경고가 아닌 자.
장학금액: 수업료 60% 이내 차등지급 (단, 수업료 범위 내에서 이중수혜 허용). 장학금 지급시 한국장학재단 중복지원 심사후 대출이 있는 경우에는 우선 대출 상환 처리함.
접수기간: 2024년 11월 15일(금) ~ 11월 29일(금)
접수방법: 방문 또는 등기우편 제출. 우편제출: 04066 서울 마포구 와우산로 94(상수동) 홍익대학교 학생회관 2층 학생처 장학팀
수혜자 선정 및 발표: 소정의 절차에 의한 심사 후 개별 통지
제출서류: 신용카드수수료장학금 신청서(소정양식) 1부, 신청 사유서(소정양식) 1부, 가족관계증명서 1부, 일시적 가계곤란 입증서류(채무변제 상환내역 확인서, 법원판결/결정문 사본, 부도사실 확인원, 중증진료 등록확인증, 진단서 등). 추가로 확인할 내용이 있을 경우 별도 서류를 요청할 수 있음."""


def main():
    df = pd.read_csv(RESULT_CSV)
    mask = df["title"].astype(str).str.contains(TARGET_TITLE_KEYWORD, na=False)

    if mask.sum() == 0:
        print("공지를 못 찾았어요. 제목을 확인해주세요.")
        return

    print(f"찾은 공지: {mask.sum()}개")
    for _, row in df[mask].iterrows():
        print(f"  - {row['title']}")

    answer = input("\n이 공지에 이미지 내용을 수동으로 추가할까요? (y/n): ")
    if answer.strip().lower() != "y":
        print("취소했어요.")
        return

    df.loc[mask, "body_text"] = (
        df.loc[mask, "body_text"].astype(str) + "\n\n[이미지 내용 - 수동 입력]\n" + MANUAL_TEXT
    )
    df.loc[mask, "ocr_applied"] = True
    df.loc[mask, "text_length"] = df.loc[mask, "body_text"].str.len()

    df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
    print("\n완료! body_text에 이미지 내용이 추가되고 ocr_applied가 True로 표시됐어요.")
    print("이제 전체 크롤링 데이터가 완성됐어요.")


if __name__ == "__main__":
    main()