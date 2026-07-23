"""
컴공과 취업인턴 게시판(0402.do) - 제목만 빠르게 크롤링 (본문/OCR 생략)

이유: 제목만으로 학습한 모델이 제목+본문 모델보다 성능이 더 좋았고,
소수 카테고리(취업/인턴 등)는 본문 추가로도 개선되지 않았음이 실험으로 확인됨.
따라서 이 게시판 데이터는 제목만 수집해도 충분함 -> OCR 없이 몇 초 안에 끝남.

이 게시판은 성격상 전부 '취업/인턴' 카테고리이므로 category를 자동으로 채움.
결과: data/job_board_titles.csv

crawler 폴더 안에서 실행: python crawl_job_board_titles.py
"""

import time
import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE_LIST_URL = "https://wwwce.hongik.ac.kr/wwwce/0402.do"
TARGET_COUNT = 50
OUTPUT_PATH = "../data/job_board_titles.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def get_article_list(target_count):
    articles = []
    offset = 0
    while len(articles) < target_count:
        params = {"mode": "list", "articleLimit": 10, "article.offset": offset}
        resp = requests.get(BASE_LIST_URL, params=params, headers=HEADERS)
        soup = BeautifulSoup(resp.text, "html.parser")

        rows = soup.select("table tbody tr")
        if not rows:
            print(f"[경고] offset={offset}에서 목록을 찾지 못함. HTML 구조 확인 필요.")
            break

        for row in rows:
            link = row.select_one("a[href*='articleNo=']")
            if not link:
                continue
            href = link.get("href", "")
            article_no = None
            for part in href.split("&"):
                if part.startswith("articleNo="):
                    article_no = part.split("=")[1]
            if not article_no:
                continue

            title = link.get_text(strip=True)
            cells = row.select("td")
            date_cell = cells[-2].get_text(strip=True) if len(cells) >= 2 else ""
            url = BASE_LIST_URL + f"?mode=view&articleNo={article_no}&article.offset=0&articleLimit=10"

            articles.append({
                "article_no": article_no,
                "title": title,
                "url": url,
                "date": date_cell,
            })

            if len(articles) >= target_count:
                break

        offset += 10
        time.sleep(0.3)

    return articles[:target_count]


def main():
    print(f"목록 수집 중 (목표 {TARGET_COUNT}개)...")
    articles = get_article_list(TARGET_COUNT)
    print(f"수집 완료: {len(articles)}개")

    df = pd.DataFrame(articles)

    if len(df) == 0:
        print("수집된 데이터가 없습니다. HTML 구조를 다시 확인해야 합니다.")
        return

    # date 형식 통일
    df["date"] = df["date"].astype(str).str.strip().str.replace(".", "-", regex=False).str.rstrip("-")

    # 자동 라벨링
    df["category"] = "취업/인턴"

    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n저장 완료: {OUTPUT_PATH}")
    print(df.head(10).to_string())


if __name__ == "__main__":
    main()