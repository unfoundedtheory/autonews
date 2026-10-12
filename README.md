## Vercel serverless deployment (v0.8 staging)

- Vercel serves `api/index.py` at `/api/*`; no always-on worker.
- `vercel.json` schedules research ~01:00 WIB, publishing checks ~06:00, 12:00, 18:00 WIB (expressions in UTC). Four distinct daily cron entries comply with current Vercel Hobby rules, but may run up to 59 minutes late.
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
| `utbot/research.py` | Feed resmi NASA, ESA dan MIT → kandidat baru tanpa duplikasi URL |
| `utbot/pipeline.py` | HTML primer → draft berbasis kutipan dengan pemeriksaan literal lewat gateway AI |
| `utbot/media.py` | Wikimedia Commons + metadata lisensi → download aman → upload JPEG final ke Supabase Storage |
| `utbot/renderer.py` | Desain deterministik 1080×1350: gradien hitam, logo, putih dan neon `#95F21E` |
| `utbot/telegram.py` | Preview, tombol approve/tolak, lihat sumber, perintah revisi, pilih foto |
| `utbot/scheduler.py` | WIB 06.00 / 12.00 / 18.00; default maksimum 2 posting harian; sisanya besok |
| `utbot/instagram.py` | Instagram Graph API: buat container → status → publish |
| `utbot/web.py` | API webhook, cron job dan status |

## Instalasi lokal dan tes

```bash
python -m venv .venv
source .venv/bin/activate
pip install '.[test]'
pytest -q
# export env vars or use `docker run --env-file .env`.
uvicorn utbot.web:app --host 127.0.0.1 --port 8000
```

Untuk mode lokal boleh `DATABASE_URL=sqlite:///./ut_local.db`. Supabase Postgres lebih cocok untuk staging dan production. `.env.example` hanya template; simpan token asli di **secrets manager**, tidak di repository.

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

Parameter `DAILY_PUBLISH_LIMIT=2` mengikuti batas dua berita per hari, meskipun ada tiga kesempatan jam 06.00, 12.00, 18.00 WIB. Jika dua slot awal terisi, jam 18.00 kosong. Jika persetujuan datang terlambat, slot 18.00 menjadi cadangan. Jika ada lima berita yang disetujui, antreannya 2 hari pertama, 2 hari kedua, 1 hari ketiga. Tidak ada posting sebelum waktunya; berita kedaluwarsa ditahan.

Untuk tiga posting per hari, ubah batas ke `3` setelah konfirmasi redaksi.

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
- Telegram accepts a **direct photo upload** in addition to HTTPS links and Commons search. Uploaded photos require credit, license and a separate rights confirmation.
- Telegram admin commands: `/help`, `/pending`, `/queue`, `/status`.
- `/internal/readiness` (worker-secret protected) shows missing live settings without printing keys.
- Image credit/license is automatically included before hashtags in Instagram captions.
- CI runs unit tests **before** building a distribution; it does not deploy automatically.

**Deployment walkthrough:** [`docs/GO_LIVE.md`](docs/GO_LIVE.md). This archive is not an active service; official accounts and secrets still need connection and E2E verification.
