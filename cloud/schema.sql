-- HonestHands cloud schema (Supabase / Postgres).
-- Paste this whole file into Supabase > SQL Editor > New query > Run. Safe to read first; it only creates things.
--
-- Privacy model (decided with the owner):
--   * Only OVERRIDDEN prompts are uploaded with their text.
--   * Flagged and clean messages are uploaded as COUNTS only (inside sessions / daily).
--   * Syllabi and assignment text never leave the user's Mac.
--   * A "watcher" sees a "subject's" sessions, daily stats, overridden prompts and last check-in, only while an
--     ACTIVE partnership exists. One-way = one row. Mutual = two rows (one each way).
--   * Groups come later; nothing here blocks them.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- profiles
create table if not exists public.profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  handle       text unique check (handle ~ '^[a-z0-9_]{3,24}$'),
  display_name text not null,
  last_seen    timestamptz,                       -- the "I'm alive" signal partners can see
  created_at   timestamptz not null default now()
);

-- a profile is created automatically when someone signs up
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(nullif(split_part(new.email, '@', 1), ''), 'Friend'))
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ------------------------------------------------------------ partnerships
-- subject = the person being held accountable; watcher = the person who can see.
create table if not exists public.partnerships (
  id           uuid primary key default gen_random_uuid(),
  subject      uuid not null references public.profiles(id) on delete cascade,
  watcher      uuid not null references public.profiles(id) on delete cascade,
  requested_by uuid not null references public.profiles(id) on delete cascade,
  status       text not null default 'pending' check (status in ('pending', 'active', 'declined', 'revoked')),
  created_at   timestamptz not null default now(),
  unique (subject, watcher),
  check (subject <> watcher),
  check (requested_by in (subject, watcher))
);

-- true when the signed-in user may see `subject`'s shared data
create or replace function public.can_see(subject uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select auth.uid() = subject or exists (
    select 1 from public.partnerships p
    where p.subject = can_see.subject and p.watcher = auth.uid() and p.status = 'active');
$$;

-- --------------------------------------------------------------- sessions
-- ids are generated on the Mac, so re-sending the same row never duplicates it.
create table if not exists public.sessions (
  id               uuid primary key,
  user_id          uuid not null references public.profiles(id) on delete cascade,
  class_label      text not null,                 -- the class NAME only
  assignment_label text,
  started_at       timestamptz not null,
  ended_at         timestamptz,
  seconds          integer not null default 0,
  clean            integer not null default 0,    -- counts only
  flagged          integer not null default 0,
  overridden       integer not null default 0,
  updated_at       timestamptz not null default now()
);
create index if not exists sessions_user_started on public.sessions (user_id, started_at desc);

-- ----------------------------------------------------------------- events
-- ONLY overridden prompts. The check below makes the database refuse anything else.
create table if not exists public.events (
  id               uuid primary key,
  user_id          uuid not null references public.profiles(id) on delete cascade,
  session_id       uuid references public.sessions(id) on delete set null,
  kind             text not null default 'overridden' check (kind = 'overridden'),
  at               timestamptz not null,
  site             text,
  class_label      text,
  assignment_label text,
  prompt_text      text not null,
  reason           text,
  rule             text
);
create index if not exists events_user_at on public.events (user_id, at desc);

-- ------------------------------------------------------------ daily stats
-- counts per day, for streaks and Insights on a friend's profile
create table if not exists public.daily (
  user_id    uuid not null references public.profiles(id) on delete cascade,
  day        date not null,
  checked    integer not null default 0,
  clean      integer not null default 0,
  flagged    integer not null default 0,
  overridden integer not null default 0,
  seconds    integer not null default 0,
  sessions   integer not null default 0,
  primary key (user_id, day)
);

-- --------------------------------------------------------------- security
alter table public.profiles     enable row level security;
alter table public.partnerships enable row level security;
alter table public.sessions     enable row level security;
alter table public.events       enable row level security;
alter table public.daily        enable row level security;

-- profiles: you, and anyone you share a partnership row with (so invites can show a name)
create policy profiles_read on public.profiles for select using (
  id = auth.uid() or exists (select 1 from public.partnerships p
    where (p.subject = auth.uid() and p.watcher = profiles.id) or (p.watcher = auth.uid() and p.subject = profiles.id)));
create policy profiles_update_own on public.profiles for update using (id = auth.uid()) with check (id = auth.uid());

-- partnerships: either side can see it; you can only start one you are part of;
-- only the OTHER person can accept or decline; either side can end it.
create policy partnerships_read on public.partnerships for select using (auth.uid() in (subject, watcher));
create policy partnerships_start on public.partnerships for insert
  with check (requested_by = auth.uid() and auth.uid() in (subject, watcher) and status = 'pending');
create policy partnerships_respond on public.partnerships for update
  using (auth.uid() in (subject, watcher))
  with check (auth.uid() in (subject, watcher)
              and (status in ('revoked') or (status in ('active', 'declined') and requested_by <> auth.uid())));
create policy partnerships_delete on public.partnerships for delete using (auth.uid() in (subject, watcher));

-- data tables: you write only your own rows; you and your active watchers can read them
create policy sessions_read on public.sessions for select using (public.can_see(user_id));
create policy sessions_write on public.sessions for insert with check (user_id = auth.uid());
create policy sessions_update on public.sessions for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy sessions_delete on public.sessions for delete using (user_id = auth.uid());

create policy events_read on public.events for select using (public.can_see(user_id));
create policy events_write on public.events for insert with check (user_id = auth.uid());
create policy events_delete on public.events for delete using (user_id = auth.uid());   -- no update: a logged override can't be edited

create policy daily_read on public.daily for select using (public.can_see(user_id));
create policy daily_write on public.daily for insert with check (user_id = auth.uid());
create policy daily_update on public.daily for update using (user_id = auth.uid()) with check (user_id = auth.uid());

-- -------------------------------------------------------------- functions
-- "I'm alive": called every few minutes by the app while it runs
create or replace function public.heartbeat() returns void
language sql security definer set search_path = public as $$
  update public.profiles set last_seen = now() where id = auth.uid();
$$;

-- look someone up by their exact handle to invite them (no browsing of all users)
create or replace function public.find_profile(h text) returns table (id uuid, display_name text)
language sql stable security definer set search_path = public as $$
  select id, display_name from public.profiles where handle = lower(h) and id <> auth.uid();
$$;

-- live updates for the Community feed
alter publication supabase_realtime add table public.events;
alter publication supabase_realtime add table public.partnerships;
