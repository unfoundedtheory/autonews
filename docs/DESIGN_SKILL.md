# Unfounded Theory — Design Skill v1.0

This guide implements the user's four supplied design modules as **production acceptance criteria**. The six reference covers are the source of truth for the visual identity. Never let an AI generative-art placeholder masquerade as a scientific image.

## 1. Editorial Photo Selection — Mandatory Before Typography

- The **hero is a specific verified image** of the scientific subject named in the story. The image must depict the actual subject, not a generic matching category. For cosmic-hand coverage, use verified photography/composites of the pulsar wind nebula MSH 15-52, e.g., original credited releases from Chandra/NASA; explicitly retain processing and composite disclosures.
- Download high-resolution images from the primary institution's asset/library links. Record URL, media owner/creator, caption, original publication date, image type, and permission/terms. The editor must approve image identity, crop, and reuse rights. Never claim that a search match alone clears rights.
- Use original visual data, not AI reconstructions, as the default. A genuine published observatory composite is acceptable as scientific imagery but must be described as a color-mapped/composite image when appropriate. Generated images must be clearly labeled `ILUSTRASI • BUKAN FOTO OBSERVASI` and never be passed off as evidence.
- No blurred circles, flat gradients, irrelevant stock photos, low-quality upscales, logos from another account, or watermarks. Never digitally alter the object itself to change evidence. No accidental reuse of an old image for an unrelated story.
- The photo must show a strong **unambiguous focal object** in the upper ~65% of the 4:5 cover. Subject-aware crop metadata uses `photo_focus=(x,y)` on normalized 0..1 coordinates. Request a replacement if safe crop cannot keep the scientific subject visible.

## 2. Visual Hierarchy — L.I.F.T + Gestalt

- Leverage: photo is the visual hero; headline is the secondary high-contrast hook; brand label tertiary. Avoid competing hero elements.
- Internal Rhythm: margins follow 4-point units (56px outer safe area, bottom ≥60px); center-aligned title; consistent line separation and badge spacing.
- Friction & Flow: tightly set **only key words** in #95F21E, the remainder pure white. All-caps visual headline is allowed while stored editorial text remains in Title Case. Avoid gratuitous visual effects.
- Transferability: headline readable when downscaled on Instagram; never make single-word orphan last lines or sacrifice legibility.
- Gestalt/Common Region: the title and logo are grouped by one shared photographic black-gradient area rather than nested UI boxes.

## 3. Type + Grid

- Canvas 1080 × 1350 pixels, 4:5 portrait. One bold condensed sans-serif family; replace with official licensed brand font when supplied.
- Headlines use approximately 54–92px auto-fit according to copy and weight. Target 3–6 balanced lines, leading ~107% and tracking approx -2%. Keep a robust bottom safety margin, no clipping or image/logo overlap.
- Use dynamic programming balanced text wrap (avoid lonely `NASA` on a final line). If headline won't fit gracefully, send it to Telegram for revision instead of shrinking to an unreadable footnote.
- Outline badge logo remains centered and compact above headline. Use the user's real transparent logo when provided; built-in badge is a staging stand-in.

## 4. Overlay and Color

- Keep the hero photo clean at the top. Apply a **progressive black gradient** to its lower part; start nearly transparent above the middle, reaching black behind the headline. Never darken the whole image uniformly and never blur the full image.
- Use only white, #95F21E, and black over the selected photograph. Aim for readable, consistent optical margins and a single strong visual focus. The thematic science photo supplies all secondary colors naturally.

## 5. Automatic Visual QA + Telegram Approval

For every candidate, check: photo source and subject identity; licensing/credit; original resolution; safe crop; whether the title's claim matches verified research; 4:5 dimensions; balanced line count; legibility; text margins; brand badge/logo; green emphasis frequency. Present low-resolution preview plus source and credit in Telegram. The editor can request a different image, focus point, highlight, or caption. A revision invalidates any previous approval. Publish ONLY the final preview accepted for that approved content version.

## 6. UI/UX Principles Used on the Operator Interfaces

Apply the shared four-module user skill: LIFT visual focus, 4-point grid, Gestalt proximity and common region, Hick's and Miller's laws to reduce approval menu choices, Fitts's Law for approval buttons, Doherty threshold for immediate acknowledgement, and differentiated default/hover/active/disabled states. Telegram buttons should be minimal: Approve, Revise, Replace Photo, Reject. Reveal extra controls only when needed, to lower cognitive load.

## 7. Readable Headlines and Scroll-Stop Hooks (v0.4 mandatory)

- **Words must not collide**: never simulate negative *letter tracking* by subtracting pixels from the inter-word progression. The old renderer moved words together by subtracting ~2% of the letter count, causing `MEMBINGUNGKANNASA` in the preview. Word spacing uses the exact shared measure+draw logic and is **at least 0.38 × font size** (typically 28–31 px) for a 1080 px cover.
- Preserve quoted editorial concepts as atomic wrap units: `“Tangan Tuhan”` must not split across separate lines even when the font could fit an isolated word.
- Hook is the **single reading priority**. Prefer 3–5 editorially coherent lines. A legitimate 6-line exception must remain readable at thumbnail size; otherwise return for shortening.
- Keep optical margins >=56px, bottom >=60px and badge gap >=30px. Don't stretch text horizontally, overlap words, fake bold with excessive strokes, or sacrifice the science image.
- Use neon green only for meaningful keywords, with enough surrounding white text to guide scan order; do not randomly highlight individual letters.
- The source of truth is the **approved editorial headline**. Alternate more curiosity-driven hooks may be offered to the operator, but must be rechecked for accuracy and explicitly approved before replacing it. Never overstate that NASA/scientists are "confused" unless a source directly supports the claim.
- Every typography adjustment must run layout/unit tests and generate a 1080×1350 preview plus a 270×338 thumbnail visual review.

## 8. Owner-approved reference: B hook with A-width (v0.5)

- Combine **B headline/hook** + **A headline width**. Design uses a real provided scientific image and never re-generates its contents.
- Shared readable width exactly **968 px on a 1080 px canvas**, margin 56 px each side. Dynamic auto-fit size is allowed, never pixel-stretch text to fit.
- Reference supplied by the owner: `assets/reference_B_wide_original_photo.jpg`, **internal design comparison only**, not a cleared source asset for publication.
- No artificially added flares, neon shadows, painted cosmic particles, glow around text, fake depth or AI art. Accent green `#95F21E`, otherwise clean white text.
- The **approved text** is the single source of truth. A provocative B-style alternative that changes a scientific claim is a draft until fact-checked and approved.

## 9. Locked reference grid (v0.6; source of truth = SIX original covers)

Measured from the original 1080×1350 owner examples, not guessed from the v0.5 preview:

- Badge is **identical in all six originals**: x=402…678, y=900…948, center=(540, 924). Hard-anchor it. Never use `text_y - dynamic_gap` for the badge.
- First headline ink begins approximately y=977…982 across all examples. Lock `HEADLINE_TOP=981`, irrespective of line count.
- All headline text fits within a fixed area y=981…1307 and safe side bounds x=56…1024. Font size and pitch adapt **within** that box (typically four or five lines), never move the box. If the text won't fit, request a shorter hook rather than shift the badge or title box.
- Compact uppercase type tracking is `-0.025em` **within words only**, with a separately enforced word gap around `0.20em` (floor 12px); measurement and drawing share exactly the same advance logic. Do not return to excessive ~`0.38em` gaps, nor shrink inter-word spacing with letter tracking.
- Four-line titles use approximately `0.985em` pitch (dense but filled to the original lower line), while five-line titles use approximately `0.89em`; actual cap-height is included in max-height validation.
- The logo is reused from the uploaded owner reference as an **extracted staging bitmap** at `utbot/assets/reference_badge.png`; replace it with the owner's original transparent vector/PNG when supplied, but do not change the bounding box. The bitmap is bundled as package data so installed-wheel rendering keeps the correct visual identity.
- All previews use the reference image's actual pixels, cropped to remove previously baked-in text. **Never regenerate scientific-looking image content using AI**. That owner-reference preview is a layout-only asset and is not cleared for publication.
- Regression tests must verify the fixed badge area for 4- and 5-line posts, fixed headline top, visual-safe width, and distinct word spacing.
