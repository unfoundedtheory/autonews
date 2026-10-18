## Vercel serverless deployment (v0.8 staging)

- Vercel serves the root `app.py` entrypoint, which mounts the newsroom under `/api/*`; no always-on worker.
- `vercel.json` defines **nine once-daily cron jobs** in UTC: discovery 01:00 WIB, draft preparation 03:00, 09:00, 15:00 and 21:00 WIB, maintenance 04:00 WIB, and publishing checks 06:00, 12:00 and 18:00 WIB. Hobby permits multiple daily jobs (each expression may run only once per day), with execution potentially delayed up to 59 minutes. Precise posting times require an always-on worker or more precise scheduling.
- Use persistent Postgres `DATABASE_URL`; Vercel rejects SQLite in scheduled jobs.
- Configure `CRON_SECRET`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ADMIN_USER_IDS`, `TELEGRAM_CHAT_ID`, provider API keys and Instagram Professional API secrets as Vercel environment variables, never in Git.
- For Vercel, images render in `/tmp`, then immediately upload to immutable Supabase Storage object paths. Sources may be fetched again when an editor revises a headline.
- Register Telegram webhook: `https://your-production-domain/api/telegram/webhook` with secret token.
- `ENABLE_LIVE_PUBLISH=false` until all APIs, database, photo-license review and approval work in a real end-to-end test. Vercel Cron is a time window, not an exact-minute SLA.

# Unfounded Theory News Automation

Sistem redaksi semi-otonom untuk mencari berita sains, memeriksa kutipan sumber primer, menulis highlight dan caption sesuai [panduan resmi](docs/editorial-guide.md), mencari kandidat foto dari Wikimedia Commons, membuat post 1080×1350, meminta persetujuan via Telegram, mengantre, lalu memublikasikan ke Instagram **hanya jika telah disetujui**.

**Status: staging / prototype fungsional, belum terhubung ke akun dan belum lulus tes live Instagram.** Jangan aktifkan publikasi langsung untuk akun produksi sebelum checklist E2E selesai.

## Aturan redaksi

- Topik prioritas astronomi. Subtema sains, kehidupan/biologi, AI dan dampaknya pada manusia.
- Highlight Title Case sumber → huruf besar pada **gambar**, tanpa em dash, rasa penasaran tetap berbasis fakta.
- Caption naratif 3–5 paragraf, menjawab 5W1H, berakhir pertanyaan terbuka kecuali tragedi nyata.
- Tepat lima hashtag, terakhir `#UnfoundedTheory`.
- Foto kandidat dengan lisensi mesin tidak otomatis dianggap legal; admin harus membaca kredit/izin lalu konfirmasi hak melalui Telegram.
- Algoritme meminta AI menyediakan kutipan **persis** dari artikel primer dan membandingkan teks. Itu **bukan** verifikasi independen; editor tetap harus membaca sumber.

## Desain final v0.6: GRID TETAP dari 6 cover asli

- Foto asli tetap menjadi hero. Tidak ada gambar buatan AI maupun neon/glow sintetis. Foto dokumenter harus diperiksa identitas objek, hak pakai, dan sumbernya sebelum publikasi.
- **Badge selalu di posisi yang sama** x402–678, y900–948, tidak bergerak saat headline makin panjang. Logo staging diambil dari contoh asli dan dibundel sebagai asset paket Python; dapat diganti dengan PNG resmi melalui `BRAND_LOGO_PATH` tanpa memindahkan posisi.
- **Area teks headline selalu tetap**: ink dimulai y981 dan harus selesai sebelum y1307, margin aman x56–1024. Jumlah baris biasanya 4 atau 5; ukuran font/leading menyesuaikan di dalam area tersebut, bukan mendorong badge ke atas.
- Huruf dibuat lebih rapat (`tracking=-2.5%`), tapi spasi antarkata tetap tampak (`word gap ~0.20em`, minimum 12px). Tidak ada kata saling bertabrakan.
- Gaya hook **B** tetap menjadi default, memakai margin kiri-kanan lebar seperti **A**. Variasi klaim berita tetap harus diverifikasi dan disetujui editorial.
- [Panduan desain lengkap](docs/DESIGN_SKILL.md) dan [preview](outputs/Preview_B_FixedGrid_v0.6.jpg) disertakan. Aset foto dari contoh asli hanya untuk evaluasi tata letak, **tidak otomatis legal digunakan ulang untuk publikasi**.

## AI multi-provider (9 pilihan)

Paket memiliki **satu gateway AI**, dengan adaptor yang dapat diganti hanya melalui secret environment. Model tiap penyedia dapat disetel manual mengikuti ketersediaan API masing-masing.

| Provider | Nilai `AI_PROVIDER` | Key environment | Model default contoh |
| --- | --- | --- | --- |
| Google Gemini | `gemini` | `GEMINI_API_KEY` | `gemini-3.5-flash-lite` |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-flash` |
| OpenAI | `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| Claude (Anthropic) | `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` | `openai/gpt-4.1-mini` |
| Groq | `groq` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Mistral | `mistral` | `MISTRAL_API_KEY` | `mistral-small-latest` |
| Together AI | `together` | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Ollama lokal | `ollama` | Tidak perlu API key | `qwen2.5:7b`, harus sudah diunduh dan berjalan **di server yang sama** |

**Catatan penting:** model dan program gratis dapat berubah kapan pun. API gratis bukan jaminan selalu tersedia, dan semua provider cloud selain Gemini dapat menimbulkan tagihan bergantung paket akun; bahkan Gemini dapat dikenai tagihan di luar Free Tier. Pengujian 9 provider sudah dilakukan dengan mock HTTP **tanpa kredensial sungguhan**, bukan bukti bahwa semua API live aktif. Jangan memasukkan model yang belum tersedia pada akun.

### Konfigurasi murah (disarankan)

```ini
AI_PROVIDER=gemini
GEMINI_API_KEY=<set in secrets manager>
GEMINI_MODEL=gemini-3.5-flash-lite
AI_ENABLE_FALLBACK=false
AI_ALLOW_PAID_FALLBACK=false
```

### Berita menggunakan Gemini, revisi Telegram menggunakan DeepSeek

```ini
AI_PROVIDER=gemini
AI_DRAFT_PROVIDER=gemini
AI_REWRITE_PROVIDER=deepseek
GEMINI_API_KEY=<set in secrets manager>
DEEPSEEK_API_KEY=<set in secrets manager>
AI_ENABLE_FALLBACK=false
```

Memilih DeepSeek secara eksplisit untuk tugas revisi bisa menimbulkan biaya meski failover nonaktif. Tetapkan budget/hard spend limits di dashboard billing provider, karena paket ini **belum menerapkan pembatas dolar lintas-provider**.

### Fallback terkontrol (opsional, NONAKTIF secara default)

```ini
AI_ENABLE_FALLBACK=true
AI_FALLBACK_PROVIDERS=deepseek,groq,openai
AI_ALLOW_PAID_FALLBACK=true
```

**Peringatan:** konfigurasi di atas mengizinkan request berbayar ketika penyedia utama mengembalikan HTTP 429/502/503/504. Jangan aktifkan bila tidak ingin biaya tambahan. Sistem **tidak** mengulang/fallback bila request timeout, validitas JSON gagal, atau hasil operasi tidak pasti, untuk mengurangi risiko tagihan dobel. Setiap panggilan baru tetap bergantung billing provider; tidak ada klaim batas biaya hard-cap di backend.

Jika `AI_ENABLE_FALLBACK=true` tapi `AI_ALLOW_PAID_FALLBACK=false`, provider yang berpotensi berbayar dilewati. Ollama dianggap provider lokal namun memerlukan model dan infrastruktur sendiri.

Untuk memeriksa nama dan status konfigurasi tanpa menghubungi AI: `python -m scripts.check_ai_config`. Untuk server, gunakan `GET /internal/ai/providers` dengan header rahasia `x-worker-secret`. Endpoint ini **tidak** menampilkan kunci API dan tidak membuktikan kuota/akses live.

Referensi gateway: [Gemini](https://ai.google.dev/gemini-api/docs), [DeepSeek](https://api-docs.deepseek.com/), [OpenAI](https://platform.openai.com/docs), [Anthropic](https://platform.claude.com/docs), [OpenRouter](https://openrouter.ai/docs), [Groq](https://console.groq.com/docs), [Mistral](https://docs.mistral.ai/), [Together](https://docs.together.ai/), [Ollama](https://docs.ollama.com/).

## Modul

| Modul | Fungsi |
|---|---|
| `utbot/research.py` | Feed resmi NASA, ESA, ESO, EMBL, dan Google DeepMind → kandidat baru tanpa duplikasi URL |
| `utbot/pipeline.py` | HTML primer → draft berbasis kutipan dengan pemeriksaan literal lewat gateway AI |
| `utbot/media.py` | Wikimedia Commons + metadata lisensi → download aman → upload JPEG final ke Supabase Storage |
| `utbot/renderer.py` | Desain deterministik 1080×1350: gradien hitam, logo, putih dan neon `#8FFF00` |
| `utbot/telegram.py` | Preview, tombol approve/tolak, lihat sumber, perintah revisi, pilih foto |
| `utbot/scheduler.py` | WIB 06.00 / 12.00 / 18.00; default maksimum 3 posting harian; sisanya besok |
| `utbot/instagram.py` | Instagram Graph API: buat container → status → publish |
| `utbot/web.py` | API webhook, cron job dan status |

## Instalasi lokal dan tes

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[test]'
pytest -q
# export env vars or use `docker run --env-file .env`.
DATABASE_URL=sqlite:///./ut_local.db uvicorn utbot.web:app --host 127.0.0.1 --port 8000
```

Untuk mode lokal boleh `DATABASE_URL=sqlite:///./ut_local.db`. Supabase Postgres lebih cocok untuk staging dan production. Docker Compose memakai `DATABASE_URL=sqlite:////app/state/ut_local.db` dari contoh `.env` sehingga state tetap di volume `ut_state`. Untuk Vercel ganti `DATABASE_URL` dengan URL PostgreSQL persisten. `docs/editorial-guide.md` wajib ikut masuk image Docker karena AI/QC membacanya setiap eksekusi. `.env.example` hanya template; simpan token asli di **secrets manager**, tidak di repository.

### Urutan staging

1. Siapkan akun Telegram bot melalui [BotFather](https://t.me/BotFather), simpan token dan `TELEGRAM_ADMIN_USER_IDS` (ID numerik, bukan username). Buat `TELEGRAM_WEBHOOK_SECRET` acak.
2. Siapkan Postgres Supabase, Storage bucket **public-read** khusus JPEG hasil akhir, Vault untuk URL API dan worker secret. Jaga service role key hanya pada backend.
3. Siapkan akun Instagram Professional dengan akses API yang sesuai; jangan bagikan sandi Instagram. Izin dan alur OAuth Instagram Login perlu diverifikasi di Meta Developer sebelum live.
4. Deploy backend pada layanan HTTP yang selalu dapat menerima webhook dan menyimpan file render sementara di volume persisten; gunakan Dockerfile, HTTPS, dan satu worker untuk SQLite. Untuk multi-instance gunakan Postgres plus locking; batasi scheduler agar tidak balapan.
5. Pasang logo resmi PNG transparan menggunakan `BRAND_LOGO_PATH` dan font berlisensi menggunakan `BRAND_FONT_PATH`. Fallback hanya untuk staging; **jangan live menggunakan logo placeholder**.
6. Atur webhook Telegram: `POST https://api.telegram.org/bot<token>/setWebhook` dengan `url=https://HOST/telegram/webhook` dan `secret_token=<TELEGRAM_WEBHOOK_SECRET>` (jalankan lokal menggunakan terminal aman, token tidak dikirim ke orang lain).
7. Terapkan `deploy/supabase_cron.sql` setelah dua nilai berikut dimasukkan ke Supabase Vault: `unfounded_api_base_url`, `unfounded_worker_secret`. Pastikan header `x-worker-secret` cocok env backend.
8. Mulai `ENABLE_LIVE_PUBLISH=false`. Jalankan `POST /jobs/discover`, `/jobs/prepare`, `/jobs/reschedule`, dan `/jobs/publish` dengan header `x-worker-secret`. Periksa hasil Telegram dan audit.
9. Setelah uji kredensial resmi Meta + preview + approval + gambar hosted + idempotensi selesai, lakukan **satu** posting uji berizin sebelum mengganti `ENABLE_LIVE_PUBLISH=true` pada instance production.

## Interaksi Telegram

Setiap draf mendapat preview foto dan teks. Tombol **Sumber** memperlihatkan URL, kutipan, kredit dan lisensi. Anda dapat klik **Highlight** atau **Caption** dan mengetik pengganti penuh atau instruksi seperti *"Persingkat jadi empat paragraf"*. Anda dapat klik **Ganti Foto**, mengirim URL HTTPS yang hak pakainya jelas atau kata kunci untuk opsi Commons. Setelah memilih foto, periksa hak penggunaan melalui tombol **Konfirmasi Lisensi Foto**, baru **Approve**.

Setiap edit mengubah versi draf, membatalkan approval terdahulu, membuang jadwal, dan merender foto ulang bila diperlukan. Callback lama ditolak. Jika tidak ada approval, tidak ada publikasi.

## Jadwal dan antrean

Pembuatan berita diperiksa empat kali per hari sekitar 03.00, 09.00, 15.00, dan 21.00 WIB. Publikasi berbeda: maksimum tiga kali pada 06.00, 12.00, dan 18.00 WIB, hanya untuk draft yang layak dan disetujui. Lima draft disetujui dijadwalkan 3 hari pertama dan 2 hari berikutnya. Kegagalan AI/QC atau stok kosong dapat mengurangi jumlah aktual yang dibuat atau terbit.

Kebijakan redaksi: empat pemeriksaan pembuatan berita dan maksimum tiga publikasi per hari.

## Keterbatasan penting

- **Tidak ada API/token pemilik yang telah terhubung dalam paket ini**. Live publish belum diuji dan masih nonaktif. Backend tidak dapat aktif sendiri tanpa di-deploy serta dikonfigurasi.
- Penelitian otomatis saat ini memakai sumber utama yang tersedia melalui RSS resmi, dan belum menuntaskan pembuktian silang independen atau deteksi plagiarisme semantik lintas penerbit.
- Foto Commons merupakan **kandidat**, bukan jaminan bahwa foto cocok dengan peristiwa; reviewer perlu memeriksa sumber dan lisensi.
- Login OAuth/rotasi token Meta, foto kiriman langsung sebagai file Telegram, upload ulang karena host downtime, dan dashboard antrean masih belum lengkap.
- Saat container Instagram sudah menerima permintaan `media_publish` dan hasilnya tidak pasti, sistem menandai `uncertain`, **bukan** mengirim ulang secara buta. Rekonsiliasi manual dibutuhkan.
- SQLite tidak cocok untuk production multi-worker. Status antrean, storage, render, dan webhook harus diuji di platform target.

## Referensi

- [Instagram API Documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api)
- [NASA Media Usage Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/)
- [Wikimedia Commons licensing metadata](https://www.mediawiki.org/wiki/Extension:CommonsMetadata)
- [Telegram Bot API](https://core.telegram.org/bots/api)

## Keamanan

Tidak ada token, cookie, kunci API, atau kredensial asli di source. Selalu gunakan secrets provider dan vault. Backend memeriksa header webhook Telegram dan allowlist `user_id`. Semua perubahan status tercatat di tabel `audit`. Upload media final dipisah dari foto sumber. Gambar yang dikirim ke Meta harus publik dan menggunakan HTTPS.

### Desain v0.6: B hook + A width + posisi elemen tetap

Renderer mempertahankan hook B serta lebar teks aman gaya A (968 piksel), **badge selalu y900–948**, area judul **y981–1307**, tracking karakter -2.5%, dan jarak antarkata sekitar 0.20em. Posisi visual tidak berpindah ketika jumlah baris berubah. Frasa hook di dalam tanda kutip tidak dipecah lintas baris; headline dengan kata yatim terakhir ditolak. Foto/claim/editorial approval tetap harus diperiksa sebelum publikasi.

Untuk preview berbasis foto milik editor: `python -m scripts.generate_demo --photo /path/foto_asli.jpg --output outputs/preview_v04.jpg`.

Preview sementara yang memakai foto dari posting referensi **hanya untuk uji visual**; jangan diterbitkan sebagai berita baru tanpa memeriksa sumber, lisensi, tanggal, dan ketepatan klaim.

## v0.7 — operational runtime and approved four-line style

- **Fixed four-line headline** enforced during rendering. If it cannot fit, the draft must be rewritten (no fifth line, no badge movement).
- **Docker Compose** runs the FastAPI webhooks and a single always-on worker. Named volumes retain local SQLite demo state and image media. Use PostgreSQL for production.
- Worker discovers and prepares every two hours WIB and checks approved posts every five minutes; publication never bypasses `ENABLE_LIVE_PUBLISH=false`.
- Telegram accepts a **direct photo upload** in addition to HTTPS links and Commons search. The **Approve** button is the only editorial confirmation; no second photo-rights button is required. Existing source/credit/license metadata stays visible to the editor.
- Telegram admin commands: `/help`, `/pending`, `/queue`, `/status`.
- `/internal/readiness` (worker-secret protected) shows missing live settings without printing keys.
- Image credit/license is automatically included before hashtags in Instagram captions.
- CI runs unit tests **before** building a distribution; it does not deploy automatically.

**Deployment walkthrough:** [`docs/GO_LIVE.md`](docs/GO_LIVE.md). This archive is not an active service; official accounts and secrets still need connection and E2E verification.

## Tipografi dan kredit foto (Oktober 2026)

- Cover memakai **League Spartan Bold** (font weight 700) dengan **letter spacing -47** (tracking `-0.047 em`) dan **line spacing 1.05** sesuai pengaturan desain asli. Font dibundel secara legal dengan lisensi SIL Open Font License 1.1 agar hasil Vercel, Docker, dan desktop seragam. Jangan gunakan Anton atau font fallback sistem.
- Semua caption Telegram dan Instagram menampilkan `Photo by : {nama fotografer}` **setelah caption utama dan tepat sebelum lima hashtag**. Contoh akun media sosial asli: `Photo by : threads/ikhsanaditya_`. Field `image_credit` menjadi satu-satunya sumber nama kredit; URL foto tidak otomatis membuktikan pemilik hak.
- Untuk mode feed + musik manual, kredit foto dapat dilengkapi bila tersedia sebelum atau saat posting tanpa memblokir tombol Approve. Bot mempertahankan atribusi kreator yang diketahui; jika tidak ada, bot mencantumkan URL sumber gambar bila tersedia dan tidak mengarang nama kreator. Editor tetap bertanggung jawab memastikan izin pemakaian yang sesuai sebelum publikasi.

## Evergreen science research (Oktober 2026)

- **Tidak ada cutoff usia 14 hari**. Riset, ilmuwan, penemuan lama, masa purba, biologi, kosmologi, dan dampak AI boleh menjadi bahan cerita jika sumbernya masih sahih.
- Jika RSS terbaru sudah habis, **Generate Test News** memeriksa APOD archive NASA (halaman bergilir), sejarah NASA dan arkeologi Nature. Semua kandidat harus lulus pembacaan sumber primer, pencocokan kutipan, QC, pemeriksaan foto/lisensi dan approval manusia.
- Daftar Pending Telegram memuat **5 draf per halaman** dengan tombol pendek dan halaman navigasi. Kandidat foto menampilkan detail pemilik dan lisensi di isi pesan serta pilihan singkat.
- Artikel sejarah tidak boleh disebut breaking news; tahun penemuan dan status ilmu mutakhir harus dijelaskan di caption.

### Aksen hijau headline (desain terkunci)

- Gunakan warna hijau **#8FFF00** hanya pada bagian yang penting secara semantik; boleh satu kata maupun frasa pendek yang **tersebar** pada awal, tengah, dan akhir headline. Bukan satu blok warna hijau yang panjang.
- Prioritas operator: **subjek ilmiah**, **aksi kunci**, **objek/fenomena**. Contoh `Kamera Robotik Berhasil Merekam Lingkaran Cahaya Auroral Utuh Dari Luar Angkasa` → `KAMERA ROBOTIK`, `MEREKAM`, `AURORAL` hijau, selain itu putih.
- Pemilihan semantik mengoreksi metadata aksen lama saat Render Ulang Cover; tidak menyunting isi headline atau mengabaikan approval/QC.
- Font harus benar-benar keluarga **League Spartan** dari Google Fonts, bobot **Bold 700**, tracking `-47` dan leading `1.05`; custom `BRAND_FONT_PATH` yang bukan League Spartan diabaikan demi konsistensi cover.

**Cover 4 baris responsif:** font League Spartan Bold 700 tidak memakai satu ukuran tetap. Renderer mencari ukuran terbesar yang muat tepat 4 baris pada grid, sambil mempertahankan tracking -47, line spacing 1.05, dan posisi logo. Jika tidak muat pada minimum yang layak dibaca, editor diminta memendekkan hook di Telegram; tidak ada fallback lima baris.

**Ergonomi cover (v0.7):** badge dan blok headline naik 24px bersama-sama; safe area kiri/kanan/bawah sama-sama 56px; line spacing proporsional 1.08. Font tetap League Spartan Bold 700, tracking -47, dan persis empat baris dengan ukuran dinamis. Pemilihan kata hijau tetap semantik. Untuk konten pendek, whitespace nyata bisa melebihi 56px; angka tersebut adalah **minimum safety margin**, bukan target merenggangkan atau men-stretch huruf.

## Semi-otomatis Feed Foto + Musik (Oktober 2026)

**Mode produksi aman:** `PHOTO_MUSIC_MODE=manual`. Tidak ada parameter resmi yang dapat menambahkan lagu native Instagram ke JPEG feed melalui API Graph yang dipakai proyek ini; jika musik diwajibkan, backend **tidak akan menerbitkan gambar tanpa musik diam-diam**.

1. AutoNews mencari cerita lama/baru, melakukan pemeriksaan editorial awal, menyiapkan foto cover 1080×1350 dan caption, mengirim preview ke Telegram.
2. Admin memeriksa sumber, identitas foto, hak penggunaan, dan QC lalu klik **Approve**. Slot diatur 06/12/18 WIB (maksimum 3 per hari).
3. Ketika slot jatuh tempo, cron mengirim **paket posting Instagram dengan musik** ke Telegram: URL cover HTTPS, caption final siap salin, rekomendasi jenis soundtrack sesuai topik. Tidak ada request `media_publish` pada mode ini.
4. Admin membuka aplikasi Instagram, memilih **Feed Post** dan menambahkan musik dari katalog yang tersedia pada akunnya (periksa izin audio), memublikasikan, kemudian klik **🎵 Konfirmasi Post Instagram** dan mengirim permalink `https://www.instagram.com/p/.../`. Ini **konfirmasi manual editor**, bukan pembuktian status live melalui Graph API.
5. Bot mencatat posting sebagai completed dan tidak menerbitkan ulang. Callback batal membatalkan handoff dan approval untuk revisi. Setelah konfirmasi, **opsional** `FACEBOOK_CROSSPOST=true` dan `ENABLE_LIVE_PUBLISH=true` memakai Facebook Page Graph API untuk satu posting foto Page terpisah; guard audit durabel mencegah retry buta saat status tidak pasti.

**Facebook:** Akun Instagram yang sudah terhubung Facebook tidak membuktikan API Page telah terotorisasi. Set `FACEBOOK_PAGE_ID` dan `FACEBOOK_PAGE_ACCESS_TOKEN` di Vercel Secret Manager setelah membuat Meta Developer App, meminta izin `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` dan Page CREATE_CONTENT; periksa koneksi via worker-authenticated `GET /api/internal/meta/connection`. Jangan mengaktifkan dua mekanisme Facebook sekaligus (native IG sharing dan Facebook API), karena bisa menimbulkan duplikat. Meta token tidak dicatat di log.

**Mode terpisah tanpa musik:** `PHOTO_MUSIC_MODE=off` memungkinkan publishing JPEG Instagram Graph API lama setelah `ENABLE_LIVE_PUBLISH=true` dan uji resmi berhasil. Ini *bukan* mode yang dipilih untuk Unfounded Theory.

**Go-live**: credentials Instagram/Facebook belum dikonfigurasi di Production (audit 14 Oktober 2026). Preview/unit test bukan tes izin API secara live. Jangan mengaktifkan `FACEBOOK_CROSSPOST` maupun API publication sampai 1 posting uji terverifikasi dan pemilik memastikan sharing native tidak menggandakan post. Vercel Hobby Cron bisa terlambat dari slot terjadwal.
