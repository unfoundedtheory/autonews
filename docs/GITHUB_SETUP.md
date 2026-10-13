# Menaruh proyek di GitHub

Repository tujuan: `unfoundedtheory/autonews`.

Buat empty private repository di GitHub (jangan centang template README/.gitignore karena sudah tersedia di paket).
Di komputer yang sudah autentikasi GitHub CLI:

```bash
unzip Unfounded_Theory_Automation_v0.2_staging.zip
cd autonews
git init
git add .
git commit -m "chore: initial staging editorial automation"
git branch -M main
git remote add origin https://github.com/unfoundedtheory/autonews.git
git push -u origin main
```

Jangan pernah menaruh isi `.env`, kunci Instagram, token Telegram, token Supabase, atau token OpenAI ke dalam commit. GitHub Action **hanya mengetes**, tidak otomatis deploy.
