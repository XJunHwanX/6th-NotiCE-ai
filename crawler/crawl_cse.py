import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re

BASE_URL = "https://wwwce.hongik.ac.kr/wwwce/0401.do"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def crawl_cse_notices(max_offset=220):
    all_notices = []

    for offset in range(0, max_offset, 10):
        params = {"mode": "list", "article.offset": offset, "articleLimit": 10}
        res = requests.get(BASE_URL, headers=HEADERS, params=params)
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.find("table").find("tbody").find_all("tr")
        if not rows:
            break  # 더 이상 글이 없으면 종료

        for row in rows:
            title_tag = row.find("span", class_="b-title")
            link_tag = row.find("div", class_="b-title-box").find("a")
            date_tag = row.find("span", class_="b-date")

            title = title_tag.get_text(strip=True)
            href = link_tag.get("href")
            url = "https://wwwce.hongik.ac.kr/wwwce/0401.do" + href
            date = date_tag.get_text(strip=True)
            article_no = re.search(r"articleNo=(\d+)", href).group(1)

            all_notices.append({
                "article_no": article_no,
                "title": title,
                "url": url,
                "date": date
            })

        print(f"offset {offset} 완료, 누적 {len(all_notices)}개")
        time.sleep(0.5)

    return all_notices

if __name__ == "__main__":
    notices = crawl_cse_notices()
    df = pd.DataFrame(notices)
    df.to_csv("data/cse_notices.csv", index=False, encoding="utf-8-sig")
    print(f"총 {len(df)}개 저장 완료")