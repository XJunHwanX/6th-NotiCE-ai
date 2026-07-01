import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

BASE_URL = "https://www.hongik.ac.kr/kr/newscenter/notice.do"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# 크롤링에서 제외할 카테고리
EXCLUDE_CATEGORIES = {"세종캠퍼스", "International Students/留学生"}

def crawl_all_notices(max_offset=2000):
    all_notices = []

    for offset in range(0, max_offset, 10):
        params = {"mode": "list", "article.offset": offset, "articleLimit": 10}
        res = requests.get(BASE_URL, headers=HEADERS, params=params)
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.find("table").find("tbody").find_all("tr")
        if not rows:
            break

        for row in rows:
            cate_tag = row.find("span", class_="b-mini-cate")
            category = cate_tag.get_text(strip=True) if cate_tag else None

            # 제외 카테고리면 건너뜀
            if category in EXCLUDE_CATEGORIES:
                continue

            title_tag = row.find("span", class_="b-title")
            link_tag = row.find("div", class_="b-title-box")
            date_tag = row.find("span", class_="b-date")

            # 필수 태그 중 하나라도 없으면 건너뜀 (특수 행 방어)
            if not title_tag or not link_tag or not date_tag:
                continue

            link_tag = link_tag.find("a")
            if not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = link_tag.get("href")
            url = "https://www.hongik.ac.kr/kr/newscenter/notice.do" + href
            date = date_tag.get_text(strip=True)
            article_no = re.search(r"articleNo=(\d+)", href).group(1)

            all_notices.append({
                "article_no": article_no,
                "title": title,
                "url": url,
                "date": date,
                "category": category
            })

        print(f"offset {offset} 완료, 누적 {len(all_notices)}개")
        time.sleep(0.5)

    return all_notices

if __name__ == "__main__":
    notices = crawl_all_notices()
    df = pd.DataFrame(notices)
    df.to_csv("data/total_notices.csv", index=False, encoding="utf-8-sig")
    print(f"총 {len(df)}개 저장 완료")