-- 002: messages between connected friends, and release requests for timed lock-ins.
-- Paste this whole file into Supabase > SQL Editor > New query > Run. Safe to run more than once.
--
--   * messages: a friend you are connected to (an ACTIVE partnership, either direction) can message you.
--   * unlock_requests: while you are locked in for a set time, you can ask a friend who watches you to release you.
--     Only that friend can approve or deny; you can only cancel your own request. Decisions are final.

-- are these two people connected by an active partnership, in either direction?
create or replace function public.are_connected(a uuid, b uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.partnerships p
                 where p.status = 'active' and ((p.subject = a and p.watcher = b) or (p.subject = b and p.watcher = a)));
$$;

-- does `w` actively watch `s`?
create or replace function public.is_watcher(s uuid, w uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.partnerships p where p.status = 'active' and p.subject = s and p.watcher = w);
$$;

-- ---------------------------------------------------------------- messages
create table if not exists public.messages (
  id         uuid primary key default gen_random_uuid(),
  from_user  uuid not null references public.profiles(id) on delete cascade,
  to_user    uuid not null references public.profiles(id) on delete cascade,
  body       text not null check (char_length(body) between 1 and 2000),
  kind       text not null default 'text' check (kind in ('text', 'system')),
  created_at timestamptz not null default now(),
  read_at    timestamptz,
  check (from_user <> to_user)
);
create index if not exists messages_to_idx   on public.messages (to_user, created_at desc);
create index if not exists messages_from_idx on public.messages (from_user, created_at desc);

alter table public.messages enable row level security;
drop policy if exists messages_read   on public.messages;
drop policy if exists messages_send   on public.messages;
drop policy if exists messages_mark   on public.messages;
drop policy if exists messages_delete on public.messages;
create policy messages_read   on public.messages for select using (auth.uid() in (from_user, to_user));
create policy messages_send   on public.messages for insert with check (from_user = auth.uid() and public.are_connected(from_user, to_user));
create policy messages_mark   on public.messages for update using (to_user = auth.uid()) with check (to_user = auth.uid());
create policy messages_delete on public.messages for delete using (from_user = auth.uid());

-- the only thing that may change on a message is read_at
create or replace function public.messages_immutable() returns trigger language plpgsql as $$
begin
  if new.from_user <> old.from_user or new.to_user <> old.to_user or new.body <> old.body
     or new.kind <> old.kind or new.created_at <> old.created_at then
    raise exception 'A sent message cannot be changed';
  end if;
  return new;
end $$;
drop trigger if exists messages_immutable_trg on public.messages;
create trigger messages_immutable_trg before update on public.messages for each row execute function public.messages_immutable();

-- ----------------------------------------------------------- unlock requests
create table if not exists public.unlock_requests (
  id           uuid primary key default gen_random_uuid(),
  subject      uuid not null references public.profiles(id) on delete cascade,   -- the person asking to be released
  watcher      uuid not null references public.profiles(id) on delete cascade,   -- the friend being asked
  note         text check (note is null or char_length(note) <= 500),
  class_label  text,
  minutes_left integer,
  status       text not null default 'pending' check (status in ('pending', 'approved', 'denied', 'cancelled')),
  created_at   timestamptz not null default now(),
  decided_at   timestamptz,
  check (subject <> watcher)
);
create index if not exists unlock_watcher_idx on public.unlock_requests (watcher, status, created_at desc);
create index if not exists unlock_subject_idx on public.unlock_requests (subject, created_at desc);

alter table public.unlock_requests enable row level security;
drop policy if exists unlock_read   on public.unlock_requests;
drop policy if exists unlock_ask    on public.unlock_requests;
drop policy if exists unlock_decide on public.unlock_requests;
create policy unlock_read   on public.unlock_requests for select using (auth.uid() in (subject, watcher));
create policy unlock_ask    on public.unlock_requests for insert with check (subject = auth.uid() and status = 'pending' and public.is_watcher(subject, watcher));
create policy unlock_decide on public.unlock_requests for update using (auth.uid() in (subject, watcher)) with check (auth.uid() in (subject, watcher));

-- who may change what: only the friend decides (approve / deny), only the requester cancels, and a decision is final
create or replace function public.unlock_guard() returns trigger language plpgsql as $$
begin
  if new.subject <> old.subject or new.watcher <> old.watcher or new.created_at <> old.created_at
     or new.note is distinct from old.note or new.class_label is distinct from old.class_label then
    raise exception 'Only the status of a release request can change';
  end if;
  if old.status <> 'pending' then
    raise exception 'This release request has already been decided';
  end if;
  if new.status in ('approved', 'denied') then
    if auth.uid() is distinct from old.watcher then raise exception 'Only the friend who was asked can decide'; end if;
  elsif new.status = 'cancelled' then
    if auth.uid() is distinct from old.subject then raise exception 'Only the person who asked can cancel'; end if;
  else
    raise exception 'Invalid status';
  end if;
  new.decided_at := now();
  return new;
end $$;
drop trigger if exists unlock_guard_trg on public.unlock_requests;
create trigger unlock_guard_trg before update on public.unlock_requests for each row execute function public.unlock_guard();

-- live updates (ignored if already added)
do $$
begin
  begin alter publication supabase_realtime add table public.messages; exception when duplicate_object then null; end;
  begin alter publication supabase_realtime add table public.unlock_requests; exception when duplicate_object then null; end;
end $$;
