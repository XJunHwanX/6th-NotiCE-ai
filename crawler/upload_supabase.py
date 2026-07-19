"""
cse_notices_final.csv -> Supabase notices 테이블에 삽입

테이블 컬럼: id(자동), source_notice_id, title, url, category, content, published_at

- source_notice_id = 내 CSV의 article_no
- content = 내 CSV의 body_text
- category = 없으면(NaN) None으로 들어감 (라벨 안 된 4개 공지)
- upsert 사용: source_notice_id가 이미 있으면 덮어쓰고, 없으면 새로 삽입
  (스크립트를 여러 번 실행해도 중복 삽입되지 않게 하기 위함)
  ** upsert가 동작하려면 Supabase에서 source_notice_id 컬럼에 UNIQUE 제약이 걸려 있어야 함 **
  없다면 Supabase SQL Editor에서 먼저 실행:
      alter table notices add constraint notices_source_notice_id_key unique (source_notice_id);

사용법 (crawler 폴더 안에서 실행):
    python upload_supabase.py
"""

import os
import math
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(".env")  # .env가 crawler 폴더 안에 있음

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("SUPABASE_URL / SUPABASE_KEY가 .env에서 로드되지 않았습니다. .env 경로와 변수명을 확인하세요.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

CSV_PATH = "../data/cse_notices_final.csv"
BATCH_SIZE = 50  # 한 번에 너무 많이 보내면 실패할 수 있어 나눠서 전송

df = pd.read_csv(CSV_PATH)

def clean_value(v):
    """NaN을 None으로 변환 (Supabase는 NaN을 못 받고 None/null만 허용)"""
    if isinstance(v, float) and math.isnan(v):
        return None
    return v

records = []
for _, row in df.iterrows():
    records.append({
        "source_notice_id": int(row["article_no"]),
        "title": clean_value(row["title"]),
        "url": clean_value(row["url"]),
        "category": clean_value(row["category"]),
        "content": clean_value(row["body_text"]),
        "published_at": clean_value(row["published_at"]),
    })

print(f"총 {len(records)}개 레코드 준비 완료")

success_count = 0
fail_batches = []

for i in range(0, len(records), BATCH_SIZE):
    batch = records[i:i + BATCH_SIZE]
    try:
        supabase.table("notices").upsert(batch, on_conflict="source_notice_id").execute()
        success_count += len(batch)
        print(f"  {i}~{i+len(batch)}번째 배치 업로드 성공")
    except Exception as e:
        print(f"  [실패] {i}~{i+len(batch)}번째 배치: {e}")
        fail_batches.append((i, i + len(batch)))

print(f"\n총 {success_count}/{len(records)}개 업로드 완료")
if fail_batches:
    print(f"실패한 배치 구간: {fail_batches}")
    print("실패 원인(컬럼명 불일치, 타입 에러, UNIQUE 제약 없음 등)을 에러 메시지에서 확인하세요.")