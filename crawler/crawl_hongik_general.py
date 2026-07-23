"""
홍익대학교 "대학공지" 게시판 크롤러 (학사/장학/학생활동 보강용)

- www.hongik.ac.kr/kr/education/notice-undergrad.do 게시판 크롤링
- 목록에 이미 붙어있는 카테고리 태그(학사/장학/학생활동/세종캠퍼스/교수학습지원/학생상담/대학혁신지원사업)를 그대로 읽어서
  우리가 필요한 3개(학사, 장학, 학생활동)만 골라냄
- 카테고리 매핑: 학사->학사, 장학->장학/근로, 학생활동->학생활동
- "교류" 단어가 제목에 포함된 공지는 제외 (컴공과 도메인과 무관, 학습에 방해될 수 있음)
- 제목만 수집 (OCR 없음, 빠르게)

결과: data/hongik_general_notices.csv

사용법 (crawler 폴더 안에서 실행): python crawl_hongik_general.py
"""

import re
import time
import requests
from bs4 import BeautifulSoup
import pandas as pd

BASE_LIST_URL = "https://www.hongik.ac.kr/kr/education/notice-undergrad.do"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
OUTPUT_PATH = "../data/hongik_general_notices.csv"

# 목록에 붙은 태그 -> 우리 카테고리로 매핑 (이 3개만 수집, 나머지는 무시)
CATEGORY_MAP = {
    "학사": "학사",
    "장학": "장학/근로",
    "학생활동": "학생활동",
}

EXCLUDE_KEYWORD = "교류"  # 학점교류 등 컴공과 도메인과 무관한 공지 제외

MAX_PAGES = 60  # 페이지당 10개, 60페이지 = 최대 600개 확인 (필요시 조정)


def parse_row(row):
    """한 행(tr)에서 카테고리 태그, 제목, article_no, url, 날짜를 추출"""
    link_tag = row.find("a", href=re.compile(r"articleNo="))
    if not link_tag:
        return None

    td = link_tag.find_parent("td")
    if td is None:
        return None

    # td 안의 텍스트 조각들 중, <a> 태그 이전에 나오는 텍스트가 카테고리 태그
    texts = list(td.stripped_strings)
    if not texts:
        return None

    category_tag = texts[0]
    title = link_tag.get_text(strip=True)

    href = link_tag.get("href", "")
    article_no_match = re.search(r"articleNo=(\d+)", href)
    if not article_no_match:
        return None
    article_no = article_no_match.group(1)

    url = href if href.startswith("http") else "https://www.hongik.ac.kr" + href

    # 같은 행(tr) 안에서 날짜 형식(YYYY.MM.DD) 문자열 찾기
    row_text = row.get_text(" ", strip=True)
    date_match = re.search(r"\d{4}\.\d{2}\.\d{2}", row_text)
    date = date_match.group(0) if date_match else ""

    return {
        "category_tag": category_tag,
        "title": title,
        "article_no": article_no,
        "url": url,
        "date": date,
    }


def crawl():
    collected = []
    offset = 0

    for page in range(MAX_PAGES):
        params = {"mode": "list", "article.offset": offset, "articleLimit": 10}
        res = requests.get(BASE_LIST_URL, headers=HEADERS, params=params, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        table = soup.find("table")
        if table is None:
            print(f"[경고] offset={offset}에서 테이블을 못 찾음, 중단")
            break

        rows = table.find_all("tr")
        found_this_page = 0

        for row in rows:
            parsed = parse_row(row)
            if parsed is None:
                continue

            # 필요한 카테고리 태그가 아니면 건너뜀
            if parsed["category_tag"] not in CATEGORY_MAP:
                continue

            # 제외 키워드가 제목에 있으면 건너뜀
            if EXCLUDE_KEYWORD in parsed["title"]:
                continue

            parsed["category"] = CATEGORY_MAP[parsed["category_tag"]]
            collected.append(parsed)
            found_this_page += 1

        print(f"offset={offset}: 이번 페이지에서 {found_this_page}개 수집, 누적 {len(collected)}개")

        offset += 10
        time.sleep(0.3)

    return collected


def main():
    print("크롤링 시작...")
    results = crawl()

    df = pd.DataFrame(results)
    if len(df) == 0:
        print("수집된 데이터가 없습니다. HTML 구조를 확인해야 합니다.")
        return

    # date 형식 통일 (2026.07.21 -> 2026-07-21)
    df["date"] = df["date"].str.replace(".", "-", regex=False).str.rstrip("-")

    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print(f"\n=== 완료 ===")
    print(f"총 {len(df)}개 수집")
    print(df["category"].value_counts())
    print(f"\n저장 위치: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()