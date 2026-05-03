# SN Image Screener — User Guide

> **Buat siapa:** content creator yg upload ke microstock (Adobe Stock,
> Shutterstock, Freepik, iStock, Dreamstime, dll), terutama yg pake
> hasil **AI-generated**.

> **Goal:** screen ribuan image dengan cepat, biar yg di-submit ke
> microstock cuma yg punya peluang besar diterima — gak buang-buang
> daily upload limit di image yg pasti reject.

---

## Daftar Isi

1. [Quick Start](#1-quick-start)
2. [Workflow Rekomendasi](#2-workflow-rekomendasi)
3. [Cara Baca Verdict](#3-cara-baca-verdict)
4. [Output Folder & Auto-Sort](#4-output-folder--auto-sort-baru-di-v102)
5. [Threshold Rekomendasi per Microstock Platform](#5-threshold-rekomendasi-per-microstock-platform)
6. [Memilih Preset Tool A (Technical Quality)](#6-memilih-preset-tool-a-technical-quality)
7. [AI Inspector (Tool B) — Tips](#7-ai-inspector-tool-b--tips)
8. [Bokeh / Blur — Penjelasan](#8-bokeh--blur--penjelasan)
9. [Troubleshooting](#9-troubleshooting)
10. [Keyboard Shortcut](#10-keyboard-shortcut)

---

## 1. Quick Start

1. **Buka aplikasi** (`SN Image Screener.exe`). Tidak butuh install
   Python — langsung double-click.
2. **Tambah image** lewat tombol `+ FOLDER` (recommended) atau
   `+ FILES` di top bar.
3. **Pilih mode** di rail kiri:
   - `TECHNICAL` (Tool A) — rule-based blur/noise/exposure check.
     Cepat & gratis. Cocok untuk **foto kamera asli**.
   - `AI INSPECTOR` (Tool B) — AI vision check untuk anatomy +
     technical. **Wajib untuk image AI-generated**, karena
     anatomy/jari/wajah gak bisa di-check dengan rule-based.
4. **Pilih preset** (kalau pakai Technical) — lihat
   [bagian 5](#5-memilih-preset-tool-a-technical-quality).
5. Klik **`▶ START SCAN`** dan tunggu sampai semua image scanned.
6. Klik baris di results table **double-click** atau **`OPEN FULL
   REVIEW`** untuk inspect satu-satu, lengkap dengan defect markers di
   atas image.
7. Setelah selesai review, klik **`EXPORT RESULTS`** untuk save
   CSV/JSON **dan** auto-sort image ke folder `pass / review / fail /
   error` di output folder yang kamu pilih. Lihat
   [bagian 4](#4-output-folder--auto-sort-baru-di-v102) untuk detail.

---

## 2. Workflow Rekomendasi

### A. Untuk Image AI-Generated (Mid-Journey, Stable Diffusion, Flux, dll)

> **Hanya pakai AI Inspector.** Tidak perlu re-check pakai Technical
> tab. AI Inspector sudah include technical-quality side-check
> (blur/noise/exposure) plus anatomy.

```
1. Klik "AI INSPECTOR" di rail kiri
2. Tambah API key (Gemini paling murah, ada free tier)
3. Pilih scan depth:
   - FAST (1 call/image) — buat triage cepat 1000+ image
   - DETAILED (10 call/image, 3×3 tile) — buat final check
   - ULTRA (lebih agresif) — buat hi-res / krusial
4. Run scan
5. Open Full Review, sort by status
6. Export hanya yang PASS → upload ke microstock
```

### B. Untuk Foto Kamera Asli (DSLR / Mirrorless / Phone)

> **Pakai Technical Quality (Tool A)** dulu untuk filter cepat,
> baru AI Inspector kalau perlu re-check anatomi.

```
1. Klik "TECHNICAL" di rail kiri
2. Pilih preset "Stock Strict" untuk submission ke Adobe/Shutterstock,
   atau "Normal" untuk umum
3. Run scan
4. REJECT items langsung di-skip (atau hapus)
5. PASS + REVIEW items → optional: re-check pakai AI Inspector
   kalau ada orang/anatomi
6. Export PASS
```

### C. Workflow Kombinasi (Paling Aman buat Submission Berbayar)

```
1. Run AI Inspector dulu → dapet anatomy + tech verdict gabungan
2. Yg verdict = REJECT → langsung buang
3. Yg verdict = REVIEW → manual check di Full Review
4. Yg verdict = PASS → DOUBLE-check via Technical preset "Stock Strict"
   khusus untuk microstock submission yang ketat (Adobe/Shutterstock)
5. Yg lulus dua-duanya → submit
```

---

## 3. Cara Baca Verdict

Status-nya sama untuk Tool A (Technical) dan Tool B (AI Inspector):

| Status | Arti | Tindakan |
|--------|------|----------|
| **PASS** | Image bersih, gak ada masalah signifikan | Submit langsung |
| **REVIEW** | Ada minor issue atau ada yg perlu manusia confirm | Buka Full Review, putuskan manual |
| **FAIL / REJECT** | Defect signifikan terdeteksi | Buang atau perbaiki ulang (re-render) |
| **ERROR** | Scan gagal (API down, file rusak) | Re-run scan untuk image itu |

### Quality Score (0-100)

Score adalah weighted mean dari sub-score per metric, dipenalti kalau
ada gating issue (file terlalu kecil, dimensi terlalu kecil, dll).

| Score | Quality Level | Bisa Submit? |
|-------|--------------|--------------|
| 90-100 | Excellent | Adobe Stock, Shutterstock, semua platform |
| 80-89 | Good | Hampir semua platform diterima |
| 70-79 | Acceptable | Platform menengah (Freepik, 123rf) |
| 60-69 | Marginal | Platform lenient, atau kategori tertentu |
| <60 | Poor | Disarankan tidak di-submit |

> **Catatan:** Score adalah **indikator**, bukan jaminan diterima.
> Microstock juga punya editor manusia yg bisa reject karena alasan
> non-teknis (komposisi jelek, tema redundant, kebanyakan model lain).

### AI Decision Recommendation

Di AI Inspector, ada field **Recommended Action** yg lebih spesifik:

- `ACCEPT` / `USE` → submit
- `REVIEW` → manual check
- `REJECT` → buang

Plus field **Reject Risk**:

- `LOW` (score >= 80) → aman submit
- `MED` (score 65-79) → 50/50, manusia harus confirm
- `HIGH` (score < 65) → kemungkinan besar ditolak

---

## 4. Output Folder & Auto-Sort (baru di v1.0.2)

Setiap kali kamu klik **`EXPORT RESULTS`**, app akan:

1. (Opsional) Tulis `report_<timestamp>.csv` dan/atau
   `report_<timestamp>.json` di output folder yang kamu pilih.
2. **MOVE** (pindah, bukan copy) setiap image ke salah satu dari 4
   subfolder berdasarkan verdict scan:

```
output_folder/
├── pass/      ← image dengan status PASS
├── review/    ← image dengan status REVIEW (perlu manual check)
├── fail/      ← image dengan status FAIL / REJECT
├── error/     ← image yang scan-nya gagal
└── report_20260502_140000.csv (kalau dicentang di Settings)
```

### Aturan-aturan penting

- **Gerak file, bukan copy.** Setelah export, file asli **dihapus**
  dari folder sumber. Pastikan kamu udah pilih output folder yang
  benar **sebelum** klik export.
- **AI verdict outranks Tool A.** Kalau image kamu sudah di-scan
  pakai AI Inspector, hasil AI yang menentukan folder tujuan. Tool A
  cuma jadi fallback untuk image yang belum AI-scan.
- **Filename collision.** Kalau file dengan nama yang sama sudah ada
  di folder tujuan, file baru akan disuffix `(1)`, `(2)`, dst —
  **tidak pernah** overwrite file yg sudah ada.
- **File yang sudah pindah → di-skip.** Re-run export setelah
  file-nya pindah tidak akan crash; cuma bilang "0 file sorted".

### Saran workflow setelah export

```
output_folder/
├── pass/      → upload ke microstock
├── review/    → buka satu-satu di Full Review, putuskan
│                manual mau di-keep atau di-buang
├── fail/      → biasanya buang (tapi cek dulu — kadang
│                false-reject di image artistik)
└── error/     → re-run scan untuk image-image ini, atau
                 hapus kalau memang corrupt
```

> **Tip keamanan:** kalau ragu mau pindah file beneran, copy dulu
> folder asli ke backup sebelum klik export. Setelah workflow-mu
> stabil, kamu bisa skip step ini.

---

## 5. Threshold Rekomendasi per Microstock Platform

> **Disclaimer:** ini berdasarkan **rule of thumb dari komunitas
> contributor**, bukan threshold resmi platform. Platform tidak
> publish threshold internal mereka. Gunakan sebagai panduan, bukan
> patokan mutlak.

### Adobe Stock (Paling Ketat)

- **Quality Score:** ≥ 80
- **AI Status:** PASS only (REVIEW pun mending di-skip)
- **Resolution:** ≥ 4MP (2000×2000 atau lebih)
- **Anatomy:** zero defect terdeteksi
- **Blur:** Tool A `Stock Strict` → blur_review ≥ 200, atau AI
  `BLUR=NONE` (kecuali bokeh sengaja)
- **Tip:** Adobe sangat strict di hands/face anatomy untuk image AI.
  Lebih baik over-filter daripada submission rate ditolak — Adobe
  menurunkan rating contributor yg sering ditolak.

### Shutterstock (Ketat)

- **Quality Score:** ≥ 78
- **AI Status:** PASS atau REVIEW dengan confidence HIGH
- **Resolution:** ≥ 4MP
- **Anatomy:** zero critical defect (minor okay kalau bukan di area
  fokus)
- **Tip:** Shutterstock punya AI generated content policy ketat. Make
  sure metadata di submission menyebut "AI generated" kalau perlu.

### iStock / Getty (Sangat Ketat untuk Editorial, Lenient untuk Creative)

- **Quality Score:** ≥ 75
- **AI Status:** PASS only untuk Editorial; REVIEW okay untuk
  Creative
- **Resolution:** ≥ 4MP, sebaiknya 6MP+
- **Tip:** iStock punya 3-image submission test untuk new contributor;
  pastikan 3 image pertama lulus dengan score 85+.

### Freepik (Menengah)

- **Quality Score:** ≥ 72
- **AI Status:** PASS atau REVIEW
- **Resolution:** ≥ 2MP
- **Tip:** Freepik lebih lenient untuk AI content tapi metadata harus
  akurat (license type AI generated).

### 123RF / Dreamstime (Lebih Lenient)

- **Quality Score:** ≥ 68
- **AI Status:** PASS, REVIEW, atau bahkan FAIL minor
- **Resolution:** ≥ 1.5MP (lebih flexible)
- **Tip:** Cocok buat upload bulk, tapi royalty per-download lebih
  rendah.

### Vecteezy / Stock-AI / Tier-2 Platforms

- **Quality Score:** ≥ 60
- **AI Status:** apapun kecuali ERROR
- **Resolution:** ≥ 1MP
- **Tip:** Volume-driven; revenue per-image kecil tapi acceptance rate
  tinggi. Gunakan semua image yg lulus minimum threshold.

---

## 6. Memilih Preset Tool A (Technical Quality)

| Preset | Cocok untuk | Catatan |
|--------|-------------|---------|
| **Stock Strict** | Adobe Stock, Shutterstock submission | Reject lebih agresif. min 2000×2000, blur < 120 langsung reject. |
| **Normal** | General culling, social media, blog hero | Default balanced. min 1024×1024. |
| **Loose** | Personal archive, casual review | Hampir gak pernah reject kecuali parah. min 640×480. |

> Bisa override threshold individu di Advanced drawer kalau preset
> bawaan kurang cocok.

---

## 7. AI Inspector (Tool B) — Tips

### Pilih Provider yg Tepat

- **Gemini** (Google) — paling murah, free tier ada. Recommended
  untuk testing dan volume tinggi.
- **OpenAI GPT-4 Vision** — lebih akurat tapi lebih mahal.
- Multiple keys dari satu provider bisa di-add untuk parallel
  processing dan failover otomatis.

### Scan Depth Mana yg Dipilih?

| Depth | Calls/Image | Latency | Best for |
|-------|-------------|---------|----------|
| **FAST** | 1 | ~3-5s | Triage cepat 100+ image, screening awal |
| **DETAILED** | 10 (1 full + 9 tile) | ~30-60s | Final check, important submission |
| **ULTRA** | Lebih agresif tile | 1-2 menit | Hi-res / klien penting / portfolio piece |

### Parallel Workers

Default = `min(jumlah_API_key, 16)`. Kalau punya 5 API key, otomatis
5 worker bareng. Bisa override manual di section "Advanced".

> **Tip:** kalau sering kena 429 rate limit, turunin worker count
> manual ke jumlah yg lebih kecil.

### Membaca Defect Areas

Di Full Review, list "Suspected Defect Areas" di kanan **hover saja**
untuk highlight markernya di image. Klik untuk select. Field per
defect:

- **Category** — Hands, Face, Body, Object, Clothing, Background
- **Severity** — Minor, Moderate, Major, Critical
- **Confidence** — Low / Medium / High (seberapa yakin AI)
- **Description** — penjelasan singkat apa yg salah

> **Critical** = pasti reject. **Minor** = mungkin gak ke-notice
> editor manusia, manual judgement.

---

## 8. Bokeh / Blur — Penjelasan

Salah satu fitur penting AI Inspector di v1.0.1+: bisa membedakan
**bokeh sengaja** vs **blur jelek**.

### Apa itu Bokeh Sengaja?

Subject (orang, produk, fokus utama) **tajam**, background sengaja
di-blur untuk efek depth-of-field. Ini **bukan defect** — itu teknik
fotografi normal yg banyak dipakai di portrait dan product shot.

- AI Inspector: `BLUR = BOKEH OK` (hijau lime)
- Verdict: gak di-downgrade
- Action: submit normal

### Apa itu Blur Jelek?

Subject sendiri buram, atau seluruh frame soft. Bisa karena:

- Foto out-of-focus
- Camera shake (di foto asli)
- AI rendering issue (subject "smudge")

- AI Inspector: `BLUR = HEAVY` (merah)
- Verdict: bumped ke REVIEW
- Action: re-render atau buang

### Tool A (Technical) Tidak Bisa Bedain Keduanya

Tool A pakai Laplacian variance — angka **global** untuk seluruh
image. Background bokeh = sharpness rendah → false-flag sebagai blur.
**Itu sebabnya untuk image AI-generated yg pake DoF, harus pake AI
Inspector.**

---

## 9. Troubleshooting

### "No usable API key" / Run button disabled

- Pergi ke **Manage API Keys** di AI Inspector tab
- Add API key (Gemini API key bisa dibuat gratis di
  https://aistudio.google.com/apikey)
- Coba "Test Key" untuk verify
- Make sure `Enabled` checkbox ON

### "Add Folder First" muncul di footer

- Belum ada image yg di-load
- Klik `+ FOLDER` di top bar untuk pilih folder berisi image, atau
  `+ FILES` untuk pilih satu-satu

### Semua image kena REVIEW di Tool A

- Preset terlalu strict, atau threshold terlalu ketat
- Kalau image AI-generated dengan bokeh background: **switch ke AI
  Inspector**, jangan andalkan Tool A
- Kalau foto asli: turunin preset ke "Normal" atau "Loose"

### Scan AI Inspector lambat banget

- Cek scan depth — DETAILED bikin 10x panggilan API per image
- Cek jumlah API key — kalau cuma 1 key dengan 100 image, sequential
  bottleneck. Tambah key untuk parallel
- Cek koneksi internet — AI Inspector butuh upload image ke
  provider

### Hasil AI Inspector inconsistent

- Provider AI memang stochastic (jawaban berbeda di run berulang)
- Untuk konsistensi tinggi, pakai DETAILED depth (multiple tile
  bikin verdict lebih stabil)
- Pakai 2-3 provider berbeda untuk cross-check pada image krusial

### Export CSV/JSON kosong / kolom AI blank

- Make sure scan udah run sampai selesai (status "Complete" di
  progress bar)
- Pastikan beberapa image lulus scan tanpa ERROR
- Export ulang setelah scan selesai

### Aku salah klik export, file aslinya udah pindah!

- **Sebelum panik:** file kamu nggak hilang. Mereka cuma pindah ke
  output folder yg kamu pilih, di subfolder `pass/`, `review/`,
  `fail/`, atau `error/`. Buka folder tersebut.
- Untuk mengembalikan: cut-paste manual dari `pass/`, `review/`,
  `fail/`, `error/` balik ke folder asli.
- **Pencegahan:** sebelum klik export, double-check field
  "Output Folder" di Settings panel — itu lokasi tujuan. Pastikan
  benar.

### File hilang ketika ada nama yg sama

- **File kamu tidak hilang.** Auto-sort tidak pernah overwrite. Kalau
  file dengan nama yang sama sudah ada di folder tujuan, file baru
  akan disuffix `(1)`, `(2)`, dst. Cari file dengan suffix tersebut
  di folder tujuan.

### Image gak kelihatan di preview

- Cek format file — supported: JPG, JPEG, PNG, WEBP, BMP
- File ukuran besar (>50MB) mungkin lambat di-load
- Coba klik baris lain dulu, lalu klik baris yg bermasalah lagi

---

## 10. Keyboard Shortcut

### Dashboard

- `Ctrl+O` — Add Folder
- `Ctrl+Shift+O` — Add Files
- `F5` / `Ctrl+R` — Start Scan
- `Ctrl+E` — Export Results
- `Delete` — Remove selected from queue (tidak menghapus file asli)

### Full Review

- `←` (Left Arrow) — Previous image
- `→` (Right Arrow) — Next image
- `Esc` — Close (back to dashboard)
- `M` — Toggle markers (show/hide defect overlays)
- `+` / `=` — Zoom in
- `-` — Zoom out
- `0` / `F` — Fit to screen
- `Ctrl+C` — Copy filename

---

## Bantuan

- Repository: https://github.com/hikhikhook-code/sn-image-screener
- Issues: report bug atau request feature di GitHub Issues
- Untuk update terbaru, check repo's Releases page

> **Versi:** 1.0.1 (technical-quality side-check via AI Inspector)
> **License:** MIT
