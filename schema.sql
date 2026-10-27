-- 2026-10-27 16:05 KST
-- 팀 편성 앱의 tf_ 테이블. 공고 5장 최소 참고안을 바탕으로 한다.
-- 스키마 이름을 붙이지 않는다(테스트가 search_path로 임시 스키마에 만들 수 있게).

-- 학생과 관리자. 관리자는 main_role이 null이다.
create table tf_students (
    id serial primary key,
    student_no text not null unique,
    name text not null,
    main_role text check (main_role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    password_hash text not null,
    is_admin boolean not null default false
);

-- 보조 역할. 학생 1명에 0~2행.
create table tf_student_sub_roles (
    student_id int not null references tf_students (id) on delete cascade,
    role text not null check (role in ('기획자', '웹 프로그래머', '프론트엔드 디자이너', '테스터', '보고서 작성자', '발표자')),
    primary key (student_id, role)
);

-- 팀. id는 팀 번호(1, 2, ...)이며 앱이 직접 넣는다.
create table tf_teams (
    id int primary key,
    name text not null unique
);

-- 팀원. (team_id, slot_no) 기본 키와 student_id 유일성으로
-- "먼저 도착한 학생만 기록"과 "한 학생은 한 팀에 소속"을 DB에서 지킨다.
create table tf_members (
    team_id int not null references tf_teams (id) on delete cascade,
    slot_no int not null check (slot_no between 1 and 4),
    student_id int not null unique references tf_students (id) on delete cascade,
    primary key (team_id, slot_no)
);

-- 지원. created_at은 지원 시각, reason은 거절 이유, decided_at은 결과가 나온 시각이다.
create table tf_applications (
    id serial primary key,
    team_id int not null references tf_teams (id) on delete cascade,
    student_id int not null references tf_students (id) on delete cascade,
    status text not null check (status in ('대기', '승인', '거절')),
    reason text,
    created_at timestamptz not null default now(),
    decided_at timestamptz
);

-- 한 학생은 결과를 기다리는 지원을 하나만 가질 수 있다.
create unique index tf_applications_one_pending on tf_applications (student_id) where status = '대기';

-- 투표. (application_id, voter_id) 기본 키로 한 번 투표하면 바꿀 수 없다.
create table tf_votes (
    application_id int not null references tf_applications (id) on delete cascade,
    voter_id int not null references tf_students (id) on delete cascade,
    vote text not null check (vote in ('찬성', '거부')),
    created_at timestamptz not null default now(),
    primary key (application_id, voter_id)
);

-- 마감 여부 등. key 'closed'의 value는 'true' 또는 'false'.
create table tf_settings (
    key text primary key,
    value text not null
);

-- AI 호출 기록.
create table tf_ai_logs (
    id serial primary key,
    created_at timestamptz not null default now(),
    round_no int not null check (round_no between 1 and 3),
    model text not null,
    ok boolean not null,
    elapsed_sec numeric(6, 1) not null,
    error text
);

-- Supabase는 public 스키마의 테이블을 웹 API(Publishable key)로 열어 둔다.
-- 정책 없이 RLS만 켜서 웹 API로는 읽고 쓰지 못하게 한다. 앱은 DB 주소로 직접 접속하는
-- 테이블 소유자(postgres)이므로 RLS의 영향을 받지 않는다.
alter table tf_students enable row level security;
alter table tf_student_sub_roles enable row level security;
alter table tf_teams enable row level security;
alter table tf_members enable row level security;
alter table tf_applications enable row level security;
alter table tf_votes enable row level security;
alter table tf_settings enable row level security;
alter table tf_ai_logs enable row level security;
