-- 003: notes and thumbs on overridden prompts.
-- Paste this whole file into Supabase > SQL Editor > New query > Run. Safe to run more than once.
--
--   * event_notes: the person who overrode a prompt can explain it ("the AI got this wrong because..."). One note per
--     prompt. Everyone who can see that person's activity can read it; only the author can write or delete it.
--   * reactions: a person who actively watches someone can give one of their overridden prompts a thumbs up or down.
--     The watcher can change or remove their own reaction; the person who overrode the prompt can read the reactions.

create table if not exists public.event_notes (
  event_id   uuid primary key references public.events(id) on delete cascade,
  user_id    uuid not null references public.profiles(id) on delete cascade,
  body       text not null check (char_length(body) between 1 and 1000),
  updated_at timestamptz not null default now()
);
alter table public.event_notes enable row level security;
drop policy if exists notes_read   on public.event_notes;
drop policy if exists notes_write  on public.event_notes;
drop policy if exists notes_update on public.event_notes;
drop policy if exists notes_delete on public.event_notes;
create policy notes_read   on public.event_notes for select using (public.can_see(user_id));
create policy notes_write  on public.event_notes for insert with check (
  user_id = auth.uid() and exists (select 1 from public.events e where e.id = event_id and e.user_id = auth.uid()));
create policy notes_update on public.event_notes for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy notes_delete on public.event_notes for delete using (user_id = auth.uid());

create table if not exists public.reactions (
  event_id   uuid not null references public.events(id) on delete cascade,
  reviewer   uuid not null references public.profiles(id) on delete cascade,
  verdict    text not null check (verdict in ('up', 'down')),
  updated_at timestamptz not null default now(),
  primary key (event_id, reviewer)
);
alter table public.reactions enable row level security;
drop policy if exists reactions_read   on public.reactions;
drop policy if exists reactions_write  on public.reactions;
drop policy if exists reactions_update on public.reactions;
drop policy if exists reactions_delete on public.reactions;
create policy reactions_read on public.reactions for select using (
  reviewer = auth.uid() or exists (select 1 from public.events e where e.id = event_id and e.user_id = auth.uid()));
create policy reactions_write on public.reactions for insert with check (
  reviewer = auth.uid() and exists (select 1 from public.events e where e.id = event_id and public.is_watcher(e.user_id, auth.uid())));
create policy reactions_update on public.reactions for update using (reviewer = auth.uid()) with check (reviewer = auth.uid());
create policy reactions_delete on public.reactions for delete using (reviewer = auth.uid());
