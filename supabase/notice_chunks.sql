begin;

create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;

alter table public.notices
  add column if not exists deadline timestamptz;

create index if not exists notices_deadline_idx
  on public.notices (deadline)
  where deadline is not null;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'notice_chunks'
      and column_name = 'content'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'notice_chunks'
      and column_name = 'content_text'
  ) then
    alter table public.notice_chunks rename column content to content_text;
  end if;
end
$$;

alter table public.notice_chunks
  add column if not exists chunk_text text,
  add column if not exists embedding public.vector(384),
  add column if not exists token_count integer,
  add column if not exists content_hash text,
  add column if not exists embedded_at timestamptz default now();

alter table public.notice_chunks
  alter column content_text set not null,
  alter column chunk_text set not null,
  alter column embedding set not null,
  alter column token_count set not null,
  alter column content_hash set not null,
  alter column embedded_at set default now(),
  alter column embedded_at set not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.notice_chunks'::regclass
      and conname = 'notice_chunks_chunk_index_nonnegative'
  ) then
    alter table public.notice_chunks
      add constraint notice_chunks_chunk_index_nonnegative
      check (chunk_index >= 0);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.notice_chunks'::regclass
      and conname = 'notice_chunks_token_count_positive'
  ) then
    alter table public.notice_chunks
      add constraint notice_chunks_token_count_positive
      check (token_count > 0);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conrelid = 'public.notice_chunks'::regclass
      and conname = 'notice_chunks_content_hash_sha256'
  ) then
    alter table public.notice_chunks
      add constraint notice_chunks_content_hash_sha256
      check (content_hash ~ '^[0-9a-f]{64}$');
  end if;
end
$$;

create index if not exists notice_chunks_embedding_hnsw_idx
  on public.notice_chunks
  using hnsw (embedding public.vector_cosine_ops);

create index if not exists notice_chunks_text_trgm_idx
  on public.notice_chunks
  using gin (chunk_text extensions.gin_trgm_ops);

alter table public.notice_chunks enable row level security;

-- Direct writes stay private. Chat clients search through the functions below.
revoke insert, update, delete, truncate, references, trigger
  on table public.notice_chunks
  from anon, authenticated;

create or replace function public.match_notice_chunks(
  query_embedding public.vector(384),
  match_count integer default 20,
  category_filter text default null,
  deadline_from timestamptz default null,
  exclude_notice_ids bigint[] default '{}'::bigint[]
)
returns table (
  chunk_id bigint,
  notice_id bigint,
  chunk_index integer,
  content_text text,
  semantic_score double precision,
  title text,
  category text,
  published_at date,
  deadline timestamptz,
  url text
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    c.id as chunk_id,
    c.notice_id,
    c.chunk_index,
    c.content_text,
    (1 - (c.embedding OPERATOR(public.<=>) query_embedding))::double precision
      as semantic_score,
    n.title,
    array_to_string(n.category, ', ') as category,
    n.published_at,
    n.deadline,
    n.url
  from public.notice_chunks as c
  join public.notices as n on n.id = c.notice_id
  where query_embedding is not null
    and (
      category_filter is null
      or category_filter = any(coalesce(n.category, '{}'::text[]))
    )
    and (deadline_from is null or n.deadline >= deadline_from)
    and not (
      c.notice_id = any(
        coalesce(exclude_notice_ids, '{}'::bigint[])
      )
    )
  order by c.embedding OPERATOR(public.<=>) query_embedding
  limit greatest(1, least(coalesce(match_count, 20), 100));
$$;

comment on function public.match_notice_chunks(
  public.vector,
  integer,
  text,
  timestamptz,
  bigint[]
) is
  'Cosine similarity search for notice chunks with optional category and deadline filters.';

drop function if exists public.search_notice_chunks_keyword(
  text[],
  integer,
  text,
  bigint[]
);

create or replace function public.search_notice_chunks_keyword(
  search_keywords text[],
  match_count integer default 20,
  category_filter text default null,
  deadline_from timestamptz default null,
  exclude_notice_ids bigint[] default '{}'::bigint[]
)
returns table (
  chunk_id bigint,
  notice_id bigint,
  chunk_index integer,
  content_text text,
  keyword_score double precision,
  matched_keywords text[],
  title text,
  category text,
  published_at date,
  deadline timestamptz,
  url text
)
language sql
stable
security definer
set search_path = ''
as $$
  with keywords as (
    select distinct lower(btrim(value)) as keyword
    from unnest(coalesce(search_keywords, '{}'::text[])) as keyword_value(value)
    where btrim(value) <> ''
  ),
  scored as (
    select
      c.id as chunk_id,
      c.notice_id,
      c.chunk_index,
      c.content_text,
      n.title,
      array_to_string(n.category, ', ') as category,
      n.published_at,
      n.deadline,
      n.url,
      k.keyword,
      least(
        case
          when strpos(lower(coalesce(n.title, '')), k.keyword) > 0
          then 1.0 else 0.0
        end
        + case
          when strpos(
            lower(array_to_string(coalesce(n.category, '{}'::text[]), ' ')),
            k.keyword
          ) > 0
          then 0.8 else 0.0
        end
        + case
          when strpos(lower(coalesce(c.content_text, '')), k.keyword) > 0
          then 0.6 else 0.0
        end
        + case
          when strpos(lower(coalesce(n.url, '')), k.keyword) > 0
          then 0.2 else 0.0
        end,
        1.0
      )::double precision as keyword_match_score
    from public.notice_chunks as c
    join public.notices as n on n.id = c.notice_id
    cross join keywords as k
    where (
        category_filter is null
        or category_filter = any(coalesce(n.category, '{}'::text[]))
      )
      and (deadline_from is null or n.deadline >= deadline_from)
      and not (
        c.notice_id = any(
          coalesce(exclude_notice_ids, '{}'::bigint[])
        )
      )
  ),
  matched as (
    select
      s.chunk_id,
      s.notice_id,
      s.chunk_index,
      s.content_text,
      (
        sum(s.keyword_match_score)
        / nullif((select count(*) from keywords), 0)
      )::double precision as keyword_score,
      array_agg(s.keyword order by s.keyword) as matched_keywords,
      s.title,
      s.category,
      s.published_at,
      s.deadline,
      s.url
    from scored as s
    where s.keyword_match_score > 0
    group by
      s.chunk_id,
      s.notice_id,
      s.chunk_index,
      s.content_text,
      s.title,
      s.category,
      s.published_at,
      s.deadline,
      s.url
  )
  select
    m.chunk_id,
    m.notice_id,
    m.chunk_index,
    m.content_text,
    m.keyword_score,
    m.matched_keywords,
    m.title,
    m.category,
    m.published_at,
    m.deadline,
    m.url
  from matched as m
  order by m.keyword_score desc, m.published_at desc nulls last
  limit greatest(1, least(coalesce(match_count, 20), 100));
$$;

revoke all on function public.match_notice_chunks(
  public.vector,
  integer,
  text,
  timestamptz,
  bigint[]
) from public;

revoke all on function public.search_notice_chunks_keyword(
  text[],
  integer,
  text,
  timestamptz,
  bigint[]
) from public;

grant execute on function public.match_notice_chunks(
  public.vector,
  integer,
  text,
  timestamptz,
  bigint[]
) to anon, authenticated, service_role;

grant execute on function public.search_notice_chunks_keyword(
  text[],
  integer,
  text,
  timestamptz,
  bigint[]
) to anon, authenticated, service_role;

notify pgrst, 'reload schema';

commit;
