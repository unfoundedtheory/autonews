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
- Friction & Flow: tightly set **only key words** in #8FFF00, the remainder pure white. All-caps visual headline is allowed while stored editorial text remains in Title Case. Avoid gratuitous visual effects.
- Transferability: headline readable when downscaled on Instagram; never make single-word orphan last lines or sacrifice legibility.
- Gestalt/Common Region: the title and logo are grouped by one shared photographic black-gradient area rather than nested UI boxes.

## 3. Type + Grid

- Canvas 1080 × 1350 pixels, 4:5 portrait. One bold condensed sans-serif family; replace with official licensed brand font when supplied.
- Headlines use approximately 54–92px auto-fit according to copy and weight. Target 3–6 balanced lines, leading ~107% and tracking approx -2%. Keep a robust bottom safety margin, no clipping or image/logo overlap.
- Use dynamic programming balanced text wrap (avoid lonely `NASA` on a final line). If headline won't fit gracefully, send it to Telegram for revision instead of shrinking to an unreadable footnote.
- Outline badge logo remains centered and compact above headline. Use the user's real transparent logo when provided; built-in badge is a staging stand-in.

## 4. Overlay and Color

- Keep the hero photo clean at the top. Apply a **progressive black gradient** to its lower part; start nearly transparent above the middle, reaching black behind the headline. Never darken the whole image uniformly and never blur the full image.
- Use only white, #8FFF00, and black over the selected photograph. Aim for readable, consistent optical margins and a single strong visual focus. The thematic science photo supplies all secondary colors naturally.

## 5. Automatic Visual QA + Telegram Approval

For every candidate, check: photo source and subject identity; licensing/credit; original resolution; safe crop; whether the title's claim matches verified research; 4:5 dimensions; balanced line count; legibility; text margins; brand badge/logo; green emphasis frequency. Present low-resolution preview plus source and credit in Telegram. The editor can request a different image, focus point, highlight, or caption. A revision invalidates any previous approval. Publish ONLY the final preview accepted for that approved content version.

AI visual review must compare the actual source image with the final news/caption and the primary source's image description, following §9 of `docs/editorial-guide.md`. Record matched, mismatched, or uncertain with a specific reason and identity evidence; inspect the cropped cover again. A URL, filename, keyword or metadata match alone is not a pixel-level AI review. If image access or vision is unavailable, record uncertainty and require editor visual review. Replace mismatched images and resolve uncertain identity before publication. Repeat when the image or news changes; never present archives, composites, simulations or illustrations as direct documentary evidence of a different event.

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
- No artificially added flares, neon shadows, painted cosmic particles, glow around text, fake depth or AI art. Accent green `#8FFF00`, otherwise clean white text.
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

## 10. Koreksi pemilik — League Spartan Bold 700 dan aksen tersebar

- Headline menggunakan font Google Fonts **League Spartan Bold 700** (bukan Black 900 dan bukan Anton), tracking **-47** atau `-0.047em`, leading **1.05**. Jangan biarkan environment override mengganti famili font.
- **Aturan historis (sekarang digantikan §15):** dulu aksen hingga tiga kelompok berdasarkan subjek/tindakan/fenomena. Sejak koreksi terbaru, kualitas ringkasan **hijau-saja** lebih penting daripada jumlah kata, posisi, atau kategori lexicon.
- Jangan mengubah kata `AURORAL` menjadi `AURORA` hanya demi aksen visual. Teks editorial, fakta, dan aturan approval tetap tidak berubah.
- Render cover lama harus memperbarui aksen usang otomatis dan membatalkan approval versi sebelumnya.

## 11. Aturan terbaru — empat baris dengan ukuran font responsif

- **Headline wajib tepat empat baris**, termasuk cerita panjang. Tidak ada mode fallback otomatis menjadi lima baris.
- Ukuran **League Spartan Bold 700** dipilih otomatis sebesar mungkin yang masih muat di area headline tetap (x=56–1024, y=981–1307), sambil menjaga tracking `-47` dan line spacing `1.05`.
- Jika teks bahkan tidak muat pada ukuran minimum yang masih terbaca, bot wajib meminta revisi hook, **bukan** mengecilkan font sampai tak terbaca, mengubah kata, atau membuat baris kelima.
- Referensi visual Mars/piramida adalah panduan bentuk glyph dan ritme; jumlah barisnya tidak mengubah persyaratan empat baris terbaru.

## 12. Ergonomi cover — grup logo/teks dinaikkan (Oktober 2026)

- **Aturan terkini mengungguli koordinat historis pada §9–11**: badge bergeser ke `(402,876,678,924)`, headline pertama mulai pada y=`957`; kedua elemen bergerak bersama **24px ke atas**, dengan celah tetap **33px**.
- Margin aman seragam **56px** untuk kiri, kanan, dan bawah. Ukur batas berdasarkan glyph yang benar-benar tergambar, bukan hanya bounding box tipografi; area kosong optis dapat lebih besar ketika headline pendek.
- League Spartan **Bold 700**, tracking **−47** (`-0.047em`), line spacing **1.08**. Ukuran font tetap otomatis sebesar mungkin selama headline empat baris aman di bidang gambar 1080×1350.
- Batas bawah tinta teks adalah y ≤ `1294`; margin visual kiri/kanan minimal 56px. Tidak boleh mengecilkan font melebihi batas keterbacaan demi mengejar kesamaan optis yang mustahil untuk semua panjang judul.
- Aksen hijau tetap menyoroti subjek, aksi, dan fenomena terpenting secara terpisah. Setelah Render Ulang Desain Cover dari Telegram, editor wajib memeriksa dan approve ulang versi baru.

## 13. Pembaruan editorial 15 Oktober 2026 — prioritas relevansi foto dan aksen hijau

Bagian ini **mengungguli panduan lama tentang batas resolusi sumber dan jumlah kelompok aksen** jika bertentangan. Tetap pertahankan grid, posisi, ukuran kanvas, font, crop, dan batas keterbacaan terbaru pada §12.

### Gambar: relevansi adalah gerbang pertama

- **Visual relevance sebelum ukuran**: kandidat hanya lolos bila gambarnya menggambarkan objek atau peristiwa ilmiah yang benar, sesuai sumber primer. Dokumen sensus atau arsip acak tidak boleh digunakan untuk berita tabrakan gugus galaksi sekalipun resolusinya bagus.
- Pemilihan bertahap: (1) hero resmi artikel sumber dengan subjek terverifikasi; (2) visual terkait dari institusi yang sama; (3) arsip ilmiah atau Commons yang cocok persis dan berhak digunakan. Bila tak ada yang relevan, **hold for manual photo replacement**, jangan render/publish dengan foto pengganti yang menyesatkan.
- Batas kualitas gambar **sumber**: sisi terpendek ≥1080 px **preferred**, ≥720 px **acceptable**, ≥600 px **conditional exception** jika sangat relevan dan masih jelas sesudah crop/upscale ringan. Gambar <600 px perlu penggantian/tinjauan manual. Tidak ada resolusi yang menutupi salah subjek atau pelanggaran lisensi.
- **Kanvas final tetap 1080×1350 px** dengan subjek aman dalam crop. Citra komposit/warna semu harus digambarkan sesuai kenyataan, bukan disebut foto warna alami; hak pakai, atribusi dan akurasi harus lulus peninjauan.
- QC visual wajib menolak mismatch subjek, gambar generik yang tidak mewakili penemuan, dan dokumen/tabel tak terkait. Kesalahan visual menahan berita sebelum publikasi; jangan menganggap meta-tag atau resolusi cukup sebagai bukti cocok.

### Hijau `#8FFF00`: 2–4 frasa bermakna

- **Pedoman historis; lihat §15:** umumnya 2–4 kelompok. Pemilihan kelompok sekarang ditentukan terlebih dahulu oleh uji keterbacaan makna hijau-saja.
- **Aturan historis; lihat §15:** persentase hijau sebelumnya sekitar 25–35% kata. Aturan terbaru memakai keseimbangan **visual** dengan putih dominan, bukan kuota berdasarkan jumlah kata.
- Prioritaskan objek, tindakan/fenomena, dan unsur unik/kontras. Contoh tema radioastronomi: `STRUKTUR RADIO` / `SIMBOL MUSIK` / `GUGUS GALAKSI`; `TUMBUKAN` opsional bila bermakna.
- Jangan mewarnai preposisi atau kata acak untuk mengejar kuota, mengubah kata demi accent, atau merusak empat baris, fon, layout, dan keterbacaan. Re-render desain butuh tinjauan ulang cover dan approval versi baru.

## 14. Koreksi margin optis dan ukuran headline (15 Oktober 2026)

- **Aturan terbaru untuk produksi ini menggantikan posisi Y headline/badge yang dikunci pada §9–13 jika konflik.** Safe margin kanan, kiri, dan tepi bawah cover final masing-masing ~56 px.
- Prioritaskan League Spartan Bold 700 dengan **ukuran font terbesar yang masih muat empat baris** pada area horizontal x=56–1024 px. Jangan melebar/menarik glyph, mengorbankan spasi antarkata, atau mengecilkan font hanya demi koordinat lama.
- Jika pembatas lebar menghalangi pembesaran font, **geser grup badge + teks turun bersama-sama** hingga tinta huruf pada baris terakhir berakhir di sekitar y=1294 (margin bawah ~56 px), sambil menjaga jarak badge ke tinta baris pertama tetap 33 px. Hindari ruang kosong bawah yang jauh lebih besar dari margin kiri/kanan.
- Ukur batas sebenarnya dari pixel tinta glyph, bukan ketinggian font nominal. Font besar bukan izin untuk keluar batas 56 px atau membuat baris kelima.
- QA wajib membandingkan margin kiri, kanan, dan bawah serta memastikan tidak ada cropping, tabrakan logo, font tak terbaca, atau gambar tak relevan. Periksa render 1080×1350 dan thumbnail.

## 15. Aturan final warna headline — *Green-Only Story Skeleton* (15 Oktober 2026)

**Bagian ini adalah acuan terbaru** dan menggantikan aturan penempatan/proporsi aksen historis pada §2, §7, §10, dan §13 jika tidak sesuai. Referensi visual yang disetujui pemilik adalah cover **“MALAM INI ... JEJAK KOMET ... RATUSAN METEOR PER JAM”**: putih solid dominan, hijau terang pada inti berita, bukan sembarang kata.

### Uji editorial wajib sebelum rendering

- **Green-only reading test:** ketika hanya segmen hijau dibaca secara berurutan, rangkaiannya harus mengisahkan peristiwa utama secara singkat, terverifikasi, dan koheren. Hindari frasa menggantung seperti `KOTA BERPENDUDUK DUA`.
- Susun *story skeleton* dari unsur **subjek → peristiwa/dampak → sebab/fenomena**, serta **waktu/angka** apabila sangat relevan. Semua segmen harus merupakan potongan utuh dari headline yang disetujui.
- **Contoh asap:** `KOTA` / `LUMPUH` / `ASAP PEKAT`; alternatif skala `KOTA` / `DUA JUTA JIWA` / `LUMPUH` / `ASAP PEKAT`.
- **Contoh meteor:** `MALAM INI` / `JEJAK KOMET` / `RATUSAN METEOR PER JAM` (frasa terakhir boleh memanjang dua baris).
- Biasanya **2–4 kelompok**, tetapi kelompok boleh lebih dari dua kata. Jangan memilih berdasarkan posisi, panjang token, jumlah aksen, atau persentase saja. Aksi/dampak spesifik (`LUMPUH`) mengungguli pembuka generik (`BERPENDUDUK`).
- Periksa tingkat kepastian: kata hijau **tidak boleh menyatakan klaim yang lebih kuat** daripada headline dan bukti sumber; jangan menambah kata yang tidak ada di naskah.
- Jika otomatisasi belum dapat memastikan *story skeleton*, izinkan perbaikan pilihan aksen oleh editor dan render ulang; jangan menyetujui pewarnaan yang salah hanya karena layout lulus.

### Dominasi putih dan layering

- Tujuan optis: kira-kira **70–80% putih, 20–30% hijau**, **bukan rasio wajib per kata**. Referensi dan akurasi isi lebih penting dari angka; hindari hijau meluas sehingga kehilangan fokus.
- Warna **putih `#FFFFFF` tanpa opacity** dan hijau **`#8FFF00` tanpa opacity**. Keduanya harus tetap tajam, terang, dan tidak tertutup foto, overlay, gradient, atau filter.
- Urutan komposit final: **foto → crop → gradient hitam untuk keterbacaan → logo/badge → seluruh teks putih/hijau di paling atas**. Jangan menaruh overlay setelah teks. Rendering boleh memakai layer teks transparan lalu melakukan compositing terakhir.
- Pertahankan JPEG berkualitas tinggi, tanpa chroma subsampling jika tersedia; PNG lossless dianjurkan sebagai preview evaluasi warna. Anti-aliasing di pinggir huruf dapat menghasilkan pixel abu-abu, **tetapi bagian tengah glyph putih harus mendekati putih murni**.
- Validasi hasil nyata pada 1080×1350 dan thumbnail; semua ini tidak mengubah aturan empat baris, grid, margin optis 56px, atau gambar asli yang relevan (§14).

## 16. Warna hijau dikalibrasi dari referensi visual asli (15 Oktober 2026)

- **Warna hijau resmi final adalah `#8FFF00` (RGB 143, 255, 0)**, diambil dari bagian tengah glyph pada gambar referensi meteor yang diberikan pemilik. Ini menggantikan **seluruh** nilai hijau lama; jangan kembali ke `#95F21E`.
- Putih tetap **`#FFFFFF`**, keduanya 100% opaque, dirender **setelah** crop/gradient foto. Gradien tidak boleh dimunculkan lagi di atas layer teks.
- Simpan JPEG dengan `quality=95`, `subsampling=0`; periksa PNG/lossless bila perlu untuk mengisolasi efek kompresi. Sedikit variasi RGB di JPG dapat terjadi, tetapi warna inti glyph hijau harus mendekati `(143,255,0)`.
- Uji warna secara terpisah dari pemilihan frasa hijau. Foto sumber, tata letak, 56px optical margins, empat baris headline dan story-skeleton tetap mengikuti ketentuan sebelumnya.

## 17. Auto-crop URL gambar dan batas bawah tanpa garis foto (15 Oktober 2026)

- **Sumber foto bebas rasio**: 16:9 landscape, 3:2, 1:1, 4:3, 9:16 portrait, dan lainnya boleh; **jangan pernah mensyaratkan 4:5 dari URL sumber**. Yang harus 4:5 hanya cover hasil akhir 1080×1350 px.
- Setelah intake HTTPS, normalisasikan orientasi EXIF, kemudian gunakan crop **cover/fill** proporsional (tanpa stretch, letterbox, padding, atau bidang kosong). Utamakan titik fokus subjek; jika crop berpotensi menghilangkan objek ilmiah utama, tawarkan perbaikan fokus/gambar pengganti alih-alih menyalahartikan subjek.
- Lapisan dari belakang: **foto hasil crop → gradient black dengan alpha dari 0 sampai 255 menuju bawah → badge → headline**. Gradient tidak memudarkan seluruh gambar dari tepi atas; di y=1350 wajib hitam penuh sehingga **batas bawah foto tidak boleh tampak sebagai garis/potongan**.
- Warna teks putih #FFFFFF dan hijau #8FFF00 100% opacity; jangan lapiskan gradient lagi setelah teks. Periksa bagian bawah di preview final dan thumbnail termasuk untuk input landscape, portrait, serta square.
- Tetap gunakan pemeriksaan relevansi/lisensi dan batas kualitas sumber ≥600px yang dapat dibaca setelah crop. Tidak mengurangi editorial/Telegram approval.


## 16. Koreksi pemilik 17 Oktober 2026 — logo absolut, teks responsif

**Mengungguli §12 untuk posisi vertikal.** Berdasarkan contoh cover baru
1080×1350 yang diberikan pemilik, logo tidak boleh lagi bergerak mengikuti
panjang headline atau ruang kosong di bawahnya.

- **Logo terkunci**: kotak (402, 900, 678, 948), pusat (540, 924).
  Koordinat ini sama untuk setiap berita dan ukuran font.
- **Headline selalu mulai di y=981** dengan jarak 33px dari batas kotak logo.
  Font League Spartan Bold 700 dan pitch disesuaikan otomatis agar seluruh
  headline masuk ke area di bawah logo hingga batas bawah y=1294.
- **Margin aman minimal 56px** di kiri, kanan, dan bawah. Lebar maksimal
  headline 968px; jangan memindahkan logo, mengecilkan margin, menabrakkan
  teks dengan logo, atau menggeser blok teks berdasarkan sisa ruang.
- Bila copy tidak dapat dirender dengan ukuran font terbaca dalam batas ini,
  minta revisi headline di Telegram; jangan menggeser elemen identitas.
- Foto referensi pemilik dipakai sebagai **panduan koordinat saja**,
  bukan sebagai sumber berita atau aset publikasi.
