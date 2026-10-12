# Blueprint Sistem: Unfounded Theory News Automation

Versi: rancangan awal. Implementasi staging v0.2 ada di repository ini; status aktual, pengujian, dan keterbatasannya dijelaskan di README.md.
Zona waktu operasional: Asia/Jakarta (WIB, UTC+7).
Dokumen acuan editorial: `Panduan Penulisan Berita Unfounded Theory.md` (unggahan pengguna, 10 Oktober 2026).
Dokumen acuan desain: enam gambar referensi pengguna, masing-masing berukuran 1080 × 1350 px.

## 1. Tujuan

Membangun alur redaksi otomatis: temukan berita → verifikasi → pilih foto yang boleh dipakai → tulis naskah → render desain → kirim ke Telegram → terima revisi atau approval → masuk antrean → terbit ke Instagram secara otomatis pada slot yang tersedia. Semua penulisan, pemeriksaan, rendering, dan pengiriman dilakukan oleh sistem. **Tidak ada publikasi tanpa persetujuan eksplisit pemilik melalui Telegram**.

## 2. Ruang Lingkup Editorial

Prioritas: astronomi, kosmologi, antariksa, penemuan observasional, misi antariksa, dampak fenomena langit pada pengamat Indonesia. Pendukung: sains yang terkait asal-usul dan kehidupan manusia, biologi/evolusi, arkeologi dengan dukungan ilmiah, serta AI dan konsekuensi nyata terhadap manusia. Tolak konten rumor tak terverifikasi, pseudoscience, klaim supernatural sebagai fakta, berita lama yang disamarkan sebagai berita hari ini, dan duplikat dari berita yang telah terbit.

Sistem menilai tiap kandidat dengan aspek: relevansi topik, kesegaran, dampak bagi audiens, kekuatan bukti, orisinalitas, peluang visual, dan kesesuaian waktu publikasi. Astronomy memperoleh prioritas utama. Score hanya untuk **ranking**, bukan untuk menggantikan verifikasi faktual.

## 3. Perolehan dan Validasi Berita

- Sumber awal: feed resmi NASA, ESA, observatorium, universitas, jurnal, lembaga riset, arXiv untuk tahap kandidat, dan kantor berita sains tepercaya. Jangan menganggap semua gambar NASA APOD bebas hak cipta.
- Rekam URL sumber asli, URL berita penjelas, penerbit, penulis, waktu peristiwa, waktu publikasi, tanggal pembaruan, DOI/tautan paper bila ada, dan status paper (peer-reviewed / preprint / siaran pers).
- Ekstraksi klaim dalam format `claim → evidence URL → tanggal → konteks → confidence`.
- Bandingkan setiap klaim inti dengan sumber primer; jika meragukan, gunakan sumber independen tambahan dan beri status `needs_manual_fact_check` (tidak boleh publish).
- Cek pembaruan, ralat, bantahan, salah tafsir angka dan kesalahan lokasi. Contoh: peristiwa langit yang terlihat pada belahan bumi lain belum tentu terlihat dari Indonesia.
- Kurangi duplikasi berbasis canonical URL, DOI, nama peneliti/studi, dan kesamaan semantik headline.
- Status berita: `discovered`, `researching`, `verified`, `rejected`, `expired`. Jangan menyebut berita `verified` jika fakta utamanya tidak memiliki bukti yang bisa ditelusuri.
- Jika artikel memakai kata `diduga`, `belum terbukti`, atau `preprint`, nuansa ini harus tetap ada di highlight/caption ketika relevan.

## 4. Penulisan

Gunakan seluruh ketentuan dokumen editorial yang diunggah. Struktur hasil produksi:

- Highlight (Title Case sebagai string sumber; pada visual dapat **ditampilkan UPPERCASE** sesuai gambar contoh). Tidak membocorkan inti berita, tetap jujur, satu kalimat, tanpa em dash atau pengulangan tidak perlu.
- Caption dengan alur pendek 4–5 paragraf, 5W1H, pembukaan naratif, pembatasan klaim, pivot, dan pertanyaan terbuka terakhir kecuali untuk tragedi nyata.
- Tepat lima hashtag relevan, dengan `#UnfoundedTheory` sebagai hashtag terakhir.
- Kredit foto (bila diwajibkan) sebelum blok hashtag agar hashtag terakhir tetap sesuai pedoman.
- Simpan `fact_sheet` serta daftar sumber terpisah agar pemilik dapat meminta `lihat sumber` lewat Telegram.
- Lint otomatis: typo, repetisi, frasa sensasional yang melampaui bukti, tanggal/jam, 5W1H, jumlah paragraf, hashtag, em dash, dan klaim tanpa sumber.

## 5. Photo Research dan Hak Cipta

Prioritas media: foto/visual resmi dari penerbit riset, NASA, ESA jika lisensi memungkinkan, lembaga ilmiah, atau stock dengan lisensi yang mengizinkan penggunaan editorial di Instagram. Setiap foto harus memiliki `photo_url`, `creator`, `credit_line`, `license`, `usage_restrictions`, `source_url`, dan `verified_rights_at`.

- Sumber foto yang tidak jelas lisensinya **tidak** otomatis layak pakai. APOD sering memuat foto berhak cipta milik pihak ketiga.
- Jangan mengunduh lalu memublikasikan ulang foto berita dari media massa tanpa izin/hak yang sesuai.
- Gunakan gambar astronomi ilmiah yang relevan, bukan visual acak atau manipulasi foto sebagai bukti temuan.
- Jika memilih ilustrasi atau gambar AI, labeli sebagai ilustrasi pada desain/caption bila dapat membingungkan audiens.
- Jika tidak ada media yang memenuhi syarat, konten tetap menjadi draf menunggu foto yang aman secara legal.

## 6. Mesin Desain (Deterministik dari Template)

Format: JPEG 1080×1350 (rasio 4:5) dengan profil warna sRGB. Template terinspirasi enam foto referensi, tetapi memiliki layout yang dapat dihitung ulang agar tetap konsisten.

- Foto sebagai latar full-bleed, crop menjaga fokus objek, tidak merusak konteks ilmiah.
- Overlay gradien hitam ke arah bawah; bukan persegi hitam keras jika merusak foto.
- Aksen: `#95F21E`, putih `#FFFFFF`, latar/overlay hitam.
- Font bold-condensed yang berlisensi sesuai distribusi proyek, uppercase untuk output visual; teks sumber dalam Title Case.
- Logo `unfounded theory` menggunakan aset resmi, bukan font yang ditebak; posisinya di atas headline dengan jarak yang konsisten.
- Baris judul fleksibel, highlight kata kunci berwarna hijau, sisanya putih. Pilihan kata hijau tidak boleh mengaburkan fakta.
- Text layout: panjang maksimum, wrapping baris dan ukuran adaptif, batas area aman Instagram, pengukuran kontras, dan larangan overflow/teks tertutup.
- Render preview berkualitas tinggi → Telegram; hasil akhir baru diunggah ke storage untuk API Instagram.
- Media yang cocok dengan headline adalah wajib: jangan memakai foto yang menimbulkan kesan palsu seolah visual tersebut merekam kejadian padahal berbeda.

## 7. Antarmuka Bot Telegram

Bot menerima pesan hanya dari Telegram `user_id` yang ada di allowlist admin. Setiap draft diberi UUID dan versi render.

Contoh pesan:

> **Draft #UT-20261010-003** | Astronomy | Berhasil diverifikasi
>
> Sumber: NASA + sumber primer terkait
>
> Highlight: ...
>
> Caption: ...
>
> Foto: [preview desain]
>
> Kredit foto: ...
>
> Status: Menunggu Persetujuan
>
> Jadwal usulan: 12 Oktober, 12.00 WIB
>
> [Approve] [Revisi Highlight] [Revisi Caption] [Ganti Foto] [Tolak] [Lihat Sumber]

Percakapan revisi yang didukung:

- `Ganti highlight, lebih misterius tapi tetap faktual` → rewrite highlight saja; render ulang dan kirim preview.
- `Caption kepanjangan, pangkas jadi empat paragraf` → rewrite caption saja, pertahankan sumber/fakta.
- `Foto kurang relevan, carikan foto resmi lainnya` → sajikan beberapa opsi lengkap dengan kredit dan lisensi; pilih opsi; render ulang.
- Mengirim foto sebagai balasan ke draft → tinjau hak penggunaan gambar milik pengguna dan render ulang.
- `Jadwalkan besok jam 18.00` → ubah slot, tetap wajib approval.
- Tombol `Approve` selalu menyetujui **versi tertentu**. Mengubah foto, caption, atau headline setelah approval membatalkan approval sebelumnya dan memerlukan approval ulang.
- Tombol `Tolak` dapat menyertakan alasan; tidak akan terbit otomatis.
- Tombol `Lihat Sumber` membuka ringkasan klaim dan tautan sumber.
- Bot mengonfirmasi berhasil/failed setelah menerima callback; perubahan disimpan di database, bukan hanya di chat.

## 8. Antrean dan Penjadwalan

Slot yang diminta: 06.00, 12.00, 18.00 **WIB**, setiap hari. WIB = UTC+7, maka 06.00 WIB = 23.00 UTC hari sebelumnya; 12.00 WIB = 05.00 UTC; 18.00 WIB = 11.00 UTC.

**Ketentuan yang masih perlu diputuskan**: permintaan menyebut tiga slot per hari, tetapi juga menyebut bahwa berita lebih dari dua harus pindah ke besok. Implementasikan parameter independen `daily_publish_limit` (usulan default 2, menunggu konfirmasi), `publish_slots` (3 slot), sehingga 1 slot dapat menjadi cadangan/kosong. Jika diputuskan 3 unggahan harian, ubah limit menjadi 3.

- Draft boleh diantrikan sejak awal, tetapi hanya status `approved` yang memenuhi syarat diterbitkan.
- Urutan: prioritas editorial dan waktu berita, dengan pembatas aging; jangan menunda artikel hingga kedaluwarsa.
- Pada tiap slot, ambil satu `approved` yang belum kedaluwarsa dan belum pernah dipublikasikan, dengan transaction lock dan idempotency key.
- Jika batas harian habis, pindahkan kandidat layak terbit ke hari berikutnya dan pertahankan urutan relatif yang wajar.
- Berita time-sensitive mendapat `expires_at`; jika slot jatuh sesudah peristiwa berakhir, ubah status `expired_needs_review`, bukan otomatis memublikasikan dengan kata "malam ini" yang salah.
- Jika belum di-approve, **lewatkan slot** dan kirim pengingat, bukan mem-post otomatis.
- Simpan waktu upload aktual, `instagram_media_id`, URL permalink, dan hasil API. Cek status API setelah submit agar tidak mem-post ulang saat respons timeout.
- Jika API gagal, retry terbatas dengan backoff + idempotency; jika tetap gagal kirim pesan kesalahan ke Telegram; jangan pindah ke `published` tanpa bukti.

## 9. Arsitektur Usulan

| Komponen | Teknologi usulan | Tanggung jawab |
|---|---|---|
| Penyimpanan & antrian | Supabase Postgres | Berita, claim evidence, draf, approval, jadwal, log, keadaan pengiriman |
| Scheduler | Supabase Cron + Edge Functions | Penemuan berkala, reminder, publikasi WIB |
| Workflow & API bot | Supabase Edge Functions atau backend server publik | Telegram webhook, authorization, persetujuan, revisi |
| AI research/writing | Penyedia LLM melalui API dengan hasil terstruktur | Ekstraksi/klasifikasi/penulisan, tidak menjadi satu-satunya sumber kebenaran |
| Rendering | Worker Node/Python terisolasi | Deterministik dari JSON template, font & foto resmi; audit final |
| Asset storage | Supabase Storage | Foto berlisensi dan JPEG final dengan URL publik/akses yang memenuhi syarat Instagram |
| Instagram | Instagram Platform API | Publikasi akun Instagram Professional menggunakan autentikasi/izin resmi |
| Dashboard opsional | Vercel | Riwayat berita, antrean, error, filter, audit |

**Catatan hosting**: jangan menggantungkan 3+ jadwal harian pada Vercel Hobby Cron karena dokumentasi Vercel membatasi Cron Hobby menjadi sekali per hari. Gunakan Supabase Cron untuk jadwal rutin. Render berat dapat menggunakan worker khusus sesuai kapasitas tier, tanpa menjadwalkan tiap gambar sebagai Vercel cron.

Akun Instagram harus Professional (Business atau Creator) dan diberi otorisasi yang tepat. Gunakan jalur Instagram Login modern jika sesuai konfigurasi akun; jalur Facebook Login memiliki syarat hubungan dengan Facebook Page. Sistem menghindari automasi browser login atau penyimpanan kata sandi Instagram.

## 10. Skema Data Minimum

- `sources(id, domain, source_type, trust_tier, license_notes, enabled)`
- `stories(id, canonical_url, doi, published_at, event_at, topic, priority, verification_status, expires_at, created_at)`
- `claims(id, story_id, claim_text, evidence_url, supporting_status, checked_at)`
- `media_assets(id, story_id, url, storage_path, creator, attribution, license, license_checked_at, source_url, accepted)`
- `drafts(id, story_id, version, highlight, caption, hashtags, selected_media_id, rendered_path, status, created_at)`
- `approvals(id, draft_id, version, telegram_user_id, approved_at, revoked_at)`
- `publish_queue(id, draft_id, approved_version, slot_at, priority, status, expires_at, attempts, idempotency_key)`
- `publications(id, publish_queue_id, instagram_media_id, permalink, published_at, api_status)`
- `telegram_sessions(chat_id, user_id, active_draft_id, active_revision_mode, expires_at)`
- `audit_log(id, entity_type, entity_id, action, actor, metadata, at)`

Semua tabel memakai constraint UNIQUE untuk sumber dan publication key; RLS aktif, service-role tidak dikirim ke client. Transaksi dengan lock saat mengambil slot.

## 11. Keamanan

- Secrets sebagai environment secrets, bukan di Git: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_ALLOWED_USER_IDS`, `META_*` OAuth keys/tokens, `SUPABASE_SERVICE_ROLE_KEY`, kunci AI provider, signature keys.
- Batasi callback Telegram dengan allowlist user ID, signature webhook, pemeriksaan idempotensi dan pengikatan `draft_id + version`.
- Hindari `callback_data` berisi token/payload sensitif.
- Credential Meta memakai OAuth, disimpan terenkripsi; refresh token dan alert saat akan kedaluwarsa.
- Tutup akses pribadi ke fact sheets / draf; hanya gambar akhir yang perlu diakses Meta disajikan melalui URL yang sesuai.
- Audit setiap edit dan approval. Jangan kirim kunci keamanan, token, atau cookie ke chat Telegram.

## 12. Uji Penerimaan yang Harus Lulus Sebelum Production

1. Temukan 10 berita dan klasifikasikan tema; hentikan rumor tanpa bukti primer.
2. Temukan 3 kandidat yang membahas penelitian sama, sistem hanya menghasilkan satu draft.
3. Pastikan semua klaim angka/tanggal memiliki URL pendukung, status preprint dinyatakan jelas.
4. Pastikan rendering 1080×1350 untuk highlight pendek/panjang tanpa overflow, semua foto kredibel.
5. Jalankan tiga iterasi revisi Telegram beruntun dan pastikan `Approve` dari versi lama ditolak.
6. Uji `Tolak`, draf yang belum di-approve, dan pesan dari Telegram user tidak diizinkan.
7. Uji 5 berita dengan batas 2/hari; 2 terjadwal hari pertama, sisanya hari selanjutnya; tidak muncul duplicate post.
8. Simulasi berita `Malam Ini` yang kedaluwarsa sebelum slot terbit; harus tertahan otomatis.
9. Uji retry setelah API Instagram timeout dan beri konfirmasi dari media ID/permalink, tanpa duplikasi.
10. Lakukan satu post percobaan ke akun Instagram Professional yang diotorisasi, dengan approval eksplisit.
11. Periksa caption setelah publish: lima hashtag, last `#UnfoundedTheory`, sumber gambar/berita akurat.
12. Uji perubahan waktu, token kedaluwarsa, media URL inaccessible, dan restore setelah gangguan layanan.

## 13. Tahap Implementasi

- **Tahap A:** proyek Git baru, migrasi Supabase, secrets config, source discovery, de-dup, verifikasi fakta, scoring.
- **Tahap B:** template visual, pemilihan foto dengan hak penggunaan, caption/highlight rules engine, preview Telegram.
- **Tahap C:** stateful Telegram bot, perintah revisi highlight/caption/foto, approval per versi, audit.
- **Tahap D:** Supabase Cron, antrean berdasarkan slot WIB, kedaluwarsa, aman terhadap duplikasi.
- **Tahap E:** Meta OAuth/Instagram Professional API, media publish, retry, laporan berhasil/gagal.
- **Tahap F:** staging end-to-end; hanya sesudah lulus lanjut ke production.

## 14. Persyaratan Koneksi dan Keputusan yang Masih Dibutuhkan

- Apakah Instagram Unfounded Theory sudah akun Professional (Business atau Creator)?
- Telegram bot baru harus dibuat via @BotFather; admin menghubungkan `user_id` pribadinya, token dijaga dalam secret manager.
- Nama repo dan proyek Supabase yang akan digunakan.
- **Konfirmasi konflik jadwal:** 3 post per hari atau maksimum 2 post dengan 3 pilihan slot (06/12/18 WIB)?
- Aset logo asli jika tersedia (PNG/SVG transparan), agar konsisten dengan contoh.

## 15. Referensi API dan Kebijakan

- Telegram Bot API: https://core.telegram.org/bots/api
- Meta Instagram API (dokumentasi resmi): https://www.postman.com/meta/workspace/instagram/documentation/23987686-9386f468-7714-490f-9bfc-9442db5c8f00
- Supabase scheduling: https://supabase.com/docs/guides/functions/schedule-functions
- Vercel Hobby Cron limitations: https://vercel.com/docs/cron-jobs/manage-cron-jobs
- NASA media: https://www.nasa.gov/nasa-brand-center/images-and-media/
- APOD image copyright: https://science.nasa.gov/apod/apod-about/
