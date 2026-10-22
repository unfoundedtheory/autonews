# Carousel Visual-First — AutoNews

- One scheduled **or published** carousel per WIB calendar day.
- Slide count is determined by the material: 2 to 20, never padded with invented filler.
- The **first slide** uses a special cover: logo in upper-left and headline above the lower menu/controls; the single-image cover stays unchanged.
- Later slides focus on factual, subject-relevant photos. Never turn a single photo into multiple filler slides.
- Each slide stores its own editorial caption, verified image source, attribution, and license metadata.
- Instagram Graph publishing accepts **2–10 carousel children** and a **single post-level caption**. The API caption is a numbered fallback, not per-image captions.
- An 11–20 slide carousel must be prepared for native manual posting. Never silently truncate.
- Owner creates a carousel from Telegram, previews slides as a Telegram media group, approves the current version, then the schedule/publisher handles the post.
- A published carousel consumes the day's quota even after status changes.
- Existing single-image publication and fixed cover remain untouched.
- Deployment order: run `deploy/002_carousel_posts.sql` in Supabase, then merge/redeploy. Validate Graph API against a test IG account before enabling unattended carousel publishing.
