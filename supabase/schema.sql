-- Beat SIRA and Investigate live. Paste into the Supabase SQL editor; running it again changes nothing.
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

-- Investigate live: a visitor sends the lab after one object and a GitHub Actions run does the work, outside the ledger.
-- The token that starts the run lives in Vault: select vault.create_secret('<token>', 'github_dispatch');
create extension if not exists pg_net;

create table if not exists public.investigations (
  id bigint generated always as identity primary key,
  object text not null check (object ~ '^ZTF[0-9]{2}[a-z]{7}$'),
  user_id uuid not null default auth.uid(),
  status text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed')),
  steps jsonb not null default '[]',
  result jsonb,
  error text,
  cost_usd numeric(8, 4) not null default 0,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);

alter table public.investigations enable row level security;
revoke all on public.investigations from anon, authenticated;
-- everyone can watch every investigation, but not see who asked for it
grant select (id, object, status, steps, result, error, cost_usd, created_at, started_at, finished_at)
  on public.investigations to anon, authenticated;
grant select, insert, update on public.investigations to service_role;

drop policy if exists "investigations are public" on public.investigations;
create policy "investigations are public" on public.investigations
  for select to anon, authenticated using (true);

-- the only way in: it checks the caps, writes the row and asks GitHub to start the run
create or replace function public.investigate(target text) returns bigint
language plpgsql security definer set search_path = '' as $$
declare
  token text;
  made bigint;
begin
  if auth.uid() is null then raise exception 'sign_in'; end if;
  if target !~ '^ZTF[0-9]{2}[a-z]{7}$' then raise exception 'bad_object'; end if;
  select decrypted_secret into token from vault.decrypted_secrets where name = 'github_dispatch';
  if token is null then raise exception 'not_connected'; end if;
  perform pg_advisory_xact_lock(hashtext('investigations'));  -- one request at a time counts the day
  if exists (select 1 from public.questions where object = target and closes_at > now()) then
    raise exception 'in_round';
  end if;
  if exists (select 1 from public.investigations where user_id = auth.uid() and status in ('queued', 'running')
             and created_at > now() - interval '15 minutes') then
    raise exception 'busy';
  end if;
  if (select count(*) from public.investigations where created_at >= date_trunc('day', now())) >= 10 then
    raise exception 'daily_limit';
  end if;
  if (select coalesce(sum(cost_usd), 0) from public.investigations where created_at >= date_trunc('day', now())) >= 2 then
    raise exception 'budget';
  end if;
  insert into public.investigations (object, user_id) values (target, auth.uid()) returning id into made;
  perform net.http_post(
    url := 'https://api.github.com/repos/Alehcs/sira/actions/workflows/investigate.yml/dispatches',
    body := jsonb_build_object('ref', 'main', 'inputs', jsonb_build_object('object', target, 'id', made::text)),
    headers := jsonb_build_object('Authorization', 'Bearer ' || token, 'Accept', 'application/vnd.github+json',
                                  'X-GitHub-Api-Version', '2022-11-28', 'User-Agent', 'sira-lab',
                                  'Content-Type', 'application/json'));
  return made;
end $$;

revoke all on function public.investigate(text) from public, anon;
grant execute on function public.investigate(text) to authenticated;
