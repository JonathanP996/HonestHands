# HonestHands cloud (Supabase)

What is stored, and who can see it, is defined in `schema.sql` (read the comments at the top).

## One-time setup (about 5 minutes)
1. Create a free project at https://supabase.com (name it `honesthands`; pick the closest region).
2. **SQL Editor > New query**, paste all of `schema.sql`, press **Run**.
3. **Authentication > Sign In / Providers > Email**: keep it enabled and turn **off** "Confirm email". The app signs people in with
   an email and password, so no emails are needed (Supabase's built-in email sender is limited to about 2 per hour, and its
   default confirmation link points at `localhost`, which doesn't work for a desktop app). If "Confirm email" stays on, a new
   account must click the emailed link once before it can sign in.
4. **Project Settings > API**: copy the **Project URL** and the **anon public** key.
   The anon key is meant to be public (the access rules in `schema.sql` protect the data).
   **Never** put the `service_role` key in the app or this repo.

## What the app uploads
- Overridden prompts, with their text (`events`).
- Counts only for clean and flagged messages (`sessions`, `daily`).
- A check-in signal (`profiles.last_seen`) so a partner can see a gap.
- Never: syllabi, assignment text, or the text of clean or flagged messages.
