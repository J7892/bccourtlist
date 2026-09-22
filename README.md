# BC Criminal Court List Monitor & Centralized Database

Automated daily monitoring, extraction, deduplication, and search dashboard for British Columbia criminal court appearance dockets.

---

## 🌟 Overview

The courts in British Columbia post criminal court appearance lists (dockets) every morning in PDF format across all provincial and Supreme court registries:
- **Daily Lists (Provincial Court):** [DAPCindex.html](https://justice.gov.bc.ca/courts/DAPCindex.html)
- **Daily Lists (B.C. Supreme Court):** [DASCindex.html](https://justice.gov.bc.ca/courts/DASCindex.html)
- **Completed Lists (Provincial Court):** [DACCPindex.html](https://justice.gov.bc.ca/courts/DACCPindex.html)
- **Completed Lists (B.C. Supreme Court):** [DACCSindex.html](https://justice.gov.bc.ca/courts/DACCSindex.html)
- **Advanced Lists (Provincial Court - Next 5 Days):** [PCDCindex.html](https://justice.gov.bc.ca/courts/PCDCindex.html)
- **Official Acronym Legend:** [Criminal Court Lists Guide](https://www2.gov.bc.ca/gov/content/justice/courthouse-services/daily-court-lists/criminal-court-lists)

This project provides:
1. **Automated Scraping & Parsing Pipeline:** Checks all court lists every day, parses table records from PDFs (both Provincial & Supreme layouts), and checks for duplicates using cryptographic SHA256 checksums to skip unchanged PDFs.
2. **Centralized Database & Case Dispositions:** Maintains an SQLite database (`data/court_data.db`) recording scheduled appearances and merging completed lists to attach **case dispositions** (e.g., `SOP` (Stay of Proceedings), `APG` (Admitted / Pled Guilty), conditional sentences, fines) and results (`IBJ`, `END`).
3. **Dedicated Advanced Lists:** Exports scheduled appearances for the next 5 days to dedicated files (`data/advanced_lists.json` and `data/advanced_lists.csv`).
4. **Interactive Dashboard:** A searchable and filterable dashboard ([docs/index.html](file:///home/jdkeller/bccourtlist/docs/index.html)) with tabbed browsing for Daily/Completed and Advanced court lists, filterable by court level, location, status, date, or keyword search. Can be hosted directly on **GitHub Pages**.
5. **GitHub Actions Automation:** Runs automatically on scheduled mornings (`.github/workflows/daily_scrape.yml`), downloads updates, updates the database and data exports, and commits changes back to the repository.

---

## 📁 Repository Structure

```text
├── .github/workflows/
│   └── daily_scrape.yml     # Automated daily GitHub Action scraper workflow
├── data/
│   ├── court_data.db        # Centralized SQLite database
│   ├── daily_court_lists.json  # Export of daily & completed appearances
│   ├── daily_court_lists.csv   # CSV export of appearances
│   ├── advanced_lists.json     # Separate file for 5-day advance schedules
│   └── advanced_lists.csv      # CSV export of advanced schedules
├── docs/                    # GitHub Pages root
│   ├── index.html           # Web dashboard
│   └── data/                # Data synced for web dashboard
├── src/
│   ├── db.py                # Database schema, deduplication & tracking
│   ├── parser.py            # PDF table extraction for all court list types
│   ├── scraper.py           # Pipeline orchestrator & exporter
│   └── legend.py            # Acronym reference & definitions
├── web/
│   └── index.html           # Dashboard template
├── requirements.txt         # Python dependencies
└── README.md
```

---

## 🚀 Quickstart & Local Usage

### 1. Set up Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Scraper
Run the full pipeline:
```bash
python -m src.scraper
```

Or test a quick run with a limited number of registries (e.g., 2 courts per category):
```bash
python -m src.scraper 2
```

### 3. Open the Dashboard
You can preview the dashboard locally by opening [docs/index.html](file:///home/jdkeller/bccourtlist/docs/index.html) in your browser or starting a local static server:
```bash
python3 -m http.server 8000 --directory docs
```
Then navigate to `http://localhost:8000`.

---

## 🌐 Enabling GitHub Pages

1. Navigate to your repository on GitHub: `https://github.com/J7892/bccourtlist/settings/pages`
2. Under **Build and deployment > Source**, select **Deploy from a branch**.
3. Choose Branch `main` and Folder `/docs`.
4. Click **Save**. The dashboard will be accessible at `https://J7892.github.io/bccourtlist/`.

---

## 🔍 Legend & Decoding

- **Proc (Bail Process):** `UTP` (Undertaking to Appear), `WAR` (Warrant), `SUM` (Summons), `RON`/`ROD` (Release Order).
- **I/C (Custody):** `Y` (In Custody), `N` (Not in Custody).
- **Rslt (Result):** `IBJ` (Adjourned / In Between Judgment), `END` (File Ended / Concluded).
- **Disposition:** `SOP` (Stay of Proceedings), `PNI` (Plea of Not Guilty), `APG` (Admitted / Pled Guilty), `G` (Guilty verdict / sentencing).
