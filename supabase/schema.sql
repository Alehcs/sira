-- Beat SIRA. Paste into the Supabase SQL editor; running it again changes nothing.
-- The lab writes questions with the service key; players bet through anonymous sign-in.

create table if not exists public.questions (
  id text primary key,
  round text not null,
  object text not null,
  text text not null,
  band text not null,
  mjd double precision not null,
  direction text not null,
  reference double precision not null,
  seen jsonb not null,
  commit text not null,
  opens_at timestamptz not null,
  closes_at timestamptz not null
);

create table if not exists public.bets (
  id bigint generated always as identity primary key,
  question_id text not null references public.questions (id),
  user_id uuid not null default auth.uid(),
  handle text not null check (handle ~ '^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{2,24}$'),
  p_yes numeric(3, 2) not null check (p_yes between 0.01 and 0.99),
  created_at timestamptz not null default now(),
  unique (question_id, user_id)
);

alter table public.questions enable row level security;
alter table public.bets enable row level security;

-- new tables are not exposed automatically in this project, so every grant is explicit
revoke all on public.questions, public.bets from anon, authenticated;
grant select on public.questions to anon, authenticated;
grant select on public.bets to anon, authenticated;
-- a player names only the question, a handle and a probability; who and when are set by the database
grant insert (question_id, handle, p_yes) on public.bets to authenticated;
grant select, insert, update, delete on public.questions, public.bets to service_role;

drop policy if exists "questions are public" on public.questions;
create policy "questions are public" on public.questions
  for select to anon, authenticated using (true);

drop policy if exists "one bet per question while it is open" on public.bets;
create policy "one bet per question while it is open" on public.bets
  for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (select 1 from public.questions q
                where q.id = question_id and now() >= q.opens_at and now() < q.closes_at)
  );

drop policy if exists "your own bet, and everyone's once closed" on public.bets;
create policy "your own bet, and everyone's once closed" on public.bets
  for select to anon, authenticated
  using (
    user_id = (select auth.uid())
    or exists (select 1 from public.questions q where q.id = question_id and q.closes_at <= now())
  );

-- a table made by an earlier run of this file gets the same rule on aliases
alter table public.bets drop constraint if exists bets_handle_check;
alter table public.bets add constraint bets_handle_check check (handle ~ '^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{2,24}$');
