"""Image-first Instagram carousels: independently sourced photographs, per-slide copy.

Instagram's app supports up to 20 slides with multiple captions. Its publishing
API is limited to 10 child containers and one post-wide caption; never claim
the API can deliver app-only per-slide captions or silently discard slides.
"""
from datetime import timezone
from pathlib import Path
from sqlalchemy import select
from .models import Draft
from .scheduler import WIB

API_MAX_SLIDES = 10
NATIVE_MAX_SLIDES = 20


def slides_for(draft):
    if getattr(draft, "post_format", "single") != "carousel":
        return []
    return list(getattr(draft, "carousel_slides", None) or [])


def require_slide_set(draft, *, for_api=False):
    slides = slides_for(draft)
    if not 2 <= len(slides) <= NATIVE_MAX_SLIDES:
        raise ValueError("Carousel membutuhkan 2–20 foto valid.")
    if for_api and len(slides) > API_MAX_SLIDES:
        raise ValueError("API Instagram hanya mendukung maksimal 10 foto; gunakan paket posting manual.")
    for item in slides:
        if not isinstance(item, dict) or not str(item.get("image_url") or "").startswith("https://"):
            raise ValueError("Semua slide harus berupa gambar HTTPS yang dapat diakses publik.")
        if not str(item.get("caption") or "").strip():
            raise ValueError("Setiap slide memerlukan caption yang sesuai sumber.")
    return slides


def validate_daily_limit(db, draft, at):
    """One scheduled or published carousel per WIB day, across all drafts.

    Do not count the draft itself. A previously published draft retains its
    scheduled_at; publishing manually must not clear its reserved day.
    """
    if getattr(draft, "post_format", "single") != "carousel":
        return
    when = at.replace(tzinfo=timezone.utc) if at.tzinfo is None else at
    day = when.astimezone(WIB).date()
    rows = db.execute(select(Draft).where(
        Draft.id != draft.id, Draft.post_format == "carousel",
        Draft.scheduled_at.is_not(None),
        Draft.status.in_(["approved", "published"]),
        Draft.publish_state.in_(["unpublished", "publishing",
            "awaiting_container", "uncertain", "published", "manual_music_pending"])
    )).scalars().all()
    for other in rows:
        scheduled = other.scheduled_at.replace(tzinfo=timezone.utc) if other.scheduled_at.tzinfo is None else other.scheduled_at
        if scheduled.astimezone(WIB).date() == day:
            raise ValueError("Sudah ada carousel terjadwal/terbit pada tanggal WIB ini. Pilih hari lain.")


def compose_api_caption(draft):
    """Preserve slide-specific editorial text in a clearly indexed fallback."""
    from .instagram import caption_text
    slides = require_slide_set(draft, for_api=True)
    parts = []
    for i, slide in enumerate(slides, 1):
        summary = " ".join(str(slide["caption"]).split())
        parts.append(f"{i}/{len(slides)} • {summary}")
    suffix = "\n\n".join(parts)
    # Use a single factual summary if per-slide copy would exceed Meta's cap.
    if len(suffix) > 1500:
        return caption_text(draft, allow_missing_credit=True)
    hashtags = " ".join(draft.hashtags or [])
    caption = suffix + ("\n\n" + hashtags if hashtags else "")
    return caption[:2200]


def _slide_caption(photo, story, claim=None):
    """Describe the actual media; quote only claims in verified source evidence."""
    title = " ".join(str(photo.get("title") or "Dokumentasi terkait berita").split())
    credit = " ".join(str(photo.get("credit") or "").split())
    source = str(photo.get("page_url") or story.source_url)
    parts = [title[:200]]
    if claim:
        parts.append(str(claim)[:320])
    if credit:
        parts.append("Foto: " + credit[:150])
    parts.append("Sumber: " + source)
    return "\n\n".join(parts)


def build_carousel(db, draft, story, *, limit=API_MAX_SLIDES):
    """Explicit owner action. Build cover once, reuse verified Commons photo URLs.

    No fabricated images, no repeated image filler, no multiple photos made
    by cropping a single photograph. Images retain their attribution metadata.
    """
    from .media import find_photos, intake_image, upload_public_jpeg
    from .photo_relevance import photo_subject_match
    from .renderer import render_carousel_cover
    if limit not in (API_MAX_SLIDES, NATIVE_MAX_SLIDES):
        raise ValueError("Pilihan jumlah carousel tidak valid.")
    if draft.status == "published" or draft.publish_state != "unpublished":
        raise ValueError("Carousel hanya bisa dibuat sebelum publikasi.")
    if not (draft.source_image_url or draft.source_image_path):
        raise ValueError("Foto sumber cover tidak tersedia. Pilih foto utama dahulu.")
    candidates = list(draft.photo_candidates or [])
    if len(candidates) < 2:
        candidates.extend(find_photos(story.title, limit=20))
    selected = []
    used = {str(draft.source_image_url or "").split("?")[0]}
    evidence = [x.get("claim") for x in (story.evidence or [])
                if isinstance(x, dict) and x.get("evidence_checked") is True and x.get("claim")]
    for candidate in candidates:
        if len(selected) >= limit - 1:
            break
        url = str(candidate.get("image_url") or "")
        key = str(candidate.get("original_url") or url).split("?")[0]
        if not url.startswith("https://") or not key or key in used:
            continue
        if not (candidate.get("credit") and candidate.get("license") and candidate.get("page_url")):
            continue
        if not photo_subject_match(story.title, candidate, story.title):
            continue
        used.add(key)
        selected.append(candidate)
    if not selected:
        raise ValueError("Belum ada foto pendukung berbeda yang relevan dan berkredit; tetap gunakan single post.")
    src = draft.source_image_path
    if not src or not Path(src).is_file():
        src = str(Path(__import__("tempfile").gettempdir()) / "autonews" / draft.id / "carousel_source.jpg")
        if not str(draft.source_image_url or "").startswith("https://"):
            raise ValueError("Cover asli perlu diunggah ulang sebelum membuat carousel.")
        intake_image(draft.source_image_url, src)
    out = Path(__import__("tempfile").gettempdir()) / "autonews" / draft.id / f"carousel_cover_v{draft.version + 1}.jpg"
    render_carousel_cover(src, draft.highlight, out)
    cover_url = upload_public_jpeg(out, f"{draft.id}/carousel/v{draft.version + 1}/slide_01.jpg")
    slides = [{
        "image_url": cover_url,
        "caption": draft.highlight + "\n\n" + (evidence[0] if evidence else story.title)
                   + "\n\nSumber: " + story.source_url,
        "title": "Cover",
        "source_url": story.source_url,
        "credit": draft.image_credit or "",
        "license": draft.photo_license or "",
    }]
    for index, candidate in enumerate(selected):
        slides.append({
            "image_url": candidate["image_url"],
            "caption": _slide_caption(candidate, story,
                     evidence[index + 1] if index + 1 < len(evidence) else None),
            "title": str(candidate.get("title") or "")[:160],
            "source_url": candidate["page_url"],
            "credit": candidate["credit"],
            "license": candidate["license"],
        })
    return slides


def send_carousel_preview(bot, chat_id, draft):
    """Telegram's media-group limit is ten; send successive groups if needed."""
    slides = require_slide_set(draft)
    if not bot:
        return
    for offset in range(0, len(slides), 10):
        items = slides[offset:offset + 10]
        bot.call("sendMediaGroup", {"chat_id": chat_id, "media": [
            {"type": "photo", "media": s["image_url"],
             "caption": f"Slide {offset + i + 1}/{len(slides)} • " + str(s["caption"])[:850]}
            for i, s in enumerate(items)
        ]})
    bot.message(chat_id,
        f"📚 Carousel {len(slides)} slide. "
        + ("Posting API: caption gabungan bernomor (Meta belum menyediakan multiple captions per slide via API)."
           if len(slides) <= API_MAX_SLIDES
           else "11–20 slide: posting manual di aplikasi Instagram dengan Multiple Captions."),
    )
