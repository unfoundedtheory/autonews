# Acceptance plan before going live

1. Source ingestion catches NASA official stories, rejects broken RSS feed independently, and records errors.
2. Same URL with different UTM query produces a single story; semantically duplicated studies across two news outlets are also suppressed.
3. Automated verifier provides claim-level URLs and exact source quotes; externally disputed claims remain in review.
4. NASA Image library metadata licensing and any third-party copyright are checked, then a real 1080x1350 render is stored publicly over HTTPS.
5. Raw highlight is Title Case; image text uppercase. Correct font, logo, neon, safe crop and legible small-screen output for 3/5/8 lines.
6. Telegram approvals validate *draft ID and version*; change headline/caption/photo → new version, previous approval revoked.
7. Telegram bot rejects unauthorized users, callbacks from old previews, and unsigned webhooks; handles photo uploads and text rewrite instructions.
8. Five approved stories scheduled from midnight WIB produce 2, 2, 1 backlog. 18:00 used if earlier slots missed, and quota includes those already posted today.
9. Bad or expired time-sensitive news is held and requires revised wording before an evening/tomorrow slot.
10. Posting dry-run saves zero media; live staging posts exactly once to a dedicated test Professional account.
11. Simulate API timeouts after container creation and after media_publish. Unknown outcome MUST NOT cause duplicate posts.
12. Meta access-token expiration, denied permissions, image URL 403 and outage cause clear Telegram alerts and safe holds.
13. No security keys in logs, chat messages, repository or source comments; RLS enabled and role scope minimal.
14. All stages pass in staging before production.
