# Data Provenance

Every number in this project comes from real, public data. This document records exactly where that data came from, under
what terms, when it was retrieved, how it is identified, and what we did and did not do to it. It is the human-readable
twin of `config/sources.yml` (the machine pins) and `NOTICE` (the attribution). A test checks that the checksums and
snapshot identifiers below equal the pins and the ingestion output.

> The client scenario is **simulated for educational purposes**. The data and documentation are real and public.
> We are not affiliated with the University of Turku, the University of Helsinki, Flavoria, or the Finnish Meteorological
> Institute, and none of them endorses this project.

**Date convention.** Calendar dates in this project are the operator's local date. The exact UTC time of each explicit retrieval is
recorded in that retrieval's `snapshot.json`; for the originally committed artifacts, only the retrieval date was recorded, not the
HTTP response headers.

## 1. Sources

### 1.1 FlavoriaFoodWeight1700 (core data)

| | |
|---|---|
| Provider | University of Turku and University of Helsinki researchers: Teemu Sarapisto, Lauri Koivunen, Tuomas Mäkilä, Arto Klami, Pauliina Ojansivu (data curator: Juho Savela) |
| Title | FlavoriaFoodWeight1700: Automated Lunch Line Meal Pictures with Automatic Measurement of Weight and Contents |
| Publisher / URL | Zenodo, https://zenodo.org/records/5850856 |
| DOI | https://doi.org/10.5281/zenodo.5850856 |
| Version / date | 1.0.0, published 2022-06-10 |
| Licence | **Creative Commons Attribution 4.0 International (CC BY 4.0)**, https://creativecommons.org/licenses/by/4.0/ . Recorded in the Zenodo API record (`license.id = cc-by-4.0`, `access_right = open`), read 2026-09-18 |
| Retrieved | **2026-09-18**, one explicit HTTP GET of `https://zenodo.org/api/records/5850856/files/dataset_csv.tar/content`, no authentication |
| What we hold | the CSV-only archive `dataset_csv.tar`. The 2.4 GiB image archive is **not** used and **not** held |
| Attribution required | CC BY 4.0: credit the creators, give the title and source link, name the licence, and indicate changes. See `NOTICE` |
| Redistribution | permitted under CC BY 4.0 with attribution; the archive is committed **unmodified** so the pipeline runs offline |
| Snapshot | `flavoria-1b68c194acc5` |

### 1.2 Finnish Meteorological Institute open data (context data)

| | |
|---|---|
| Provider | Finnish Meteorological Institute (Ilmatieteen laitos) |
| Service | FMI open data web feature service, https://opendata.fmi.fi/wfs ; stored query `fmi::observations::weather::simple` ; station Turku Artukainen (FMISID 100949) |
| Documentation | https://en.ilmatieteenlaitos.fi/open-data-manual-time-series-data |
| Licence | **Creative Commons Attribution 4.0 International (CC BY 4.0)**. Verified on the official FMI licence page https://en.ilmatieteenlaitos.fi/open-data-licence on **2026-09-19**, which states "Creative Commons Attribution 4.0 International license (CC BY 4.0)" and links https://creativecommons.org/licenses/by/4.0/ |
| Scope of that licence | FMI datasets, Radiation and Nuclear Safety Authority datasets and air-quality datasets in the open data web service. Air-quality data has an appendix of licensors; we do not use air-quality data |
| Attribution wording | **the licence page does not prescribe attribution wording** beyond referencing CC BY 4.0. The statement in `NOTICE` is ours and is labelled as such |
| Retrieved | **2026-09-18**, seven chunked HTTP GET requests, no authentication (the server rejects spans over 168 hours) |
| Service limits (published) | 20,000 requests per day; 600 per 5 minutes |
| Redistribution | permitted under CC BY 4.0 with attribution; the retrieved XML is committed unmodified |
| Snapshot | `fmi-8ab7d7d344b4` |

### 1.3 Flavoria Data Catalog (documentation only)

| | |
|---|---|
| Provider | Flavoria Research Infrastructure, University of Turku |
| URLs | https://flavoriadatacatalog.tt.utu.fi/ and the Lunch Line, Weigh & Dine and Lunch Line Waste pages under `/docs/lunch-line/` |
| Use | source-definition evidence only. **No data is taken from it.** Short factual phrases are quoted with the URL (for example that the waste sample section reads "TODO, Ask!") |
| Terms | **no licence or terms statement was found on the pages reviewed** (2026-09-18 and 2026-09-19). We therefore quote briefly, link, and do not copy or redistribute the pages. The catalogue itself warns that it is being reconstructed in 2026 and may contain missing or incorrect data |
| Retrieved | 2026-09-18 (pages last updated 2026-04-09 according to the pages) |

### 1.4 Not used

The Flavoria waste, Weigh & Dine, cash-register, building, MyFlavoria and survey data are documented but not publicly retrievable and are **not** part of this project (`source_gap_register.md`). The 2025 forecasting paper cited in the original plan was not ingested and its claims were not verified.

## 2. What we did to the data

- **Raw files are unmodified.** The archive and the seven XML files are byte-for-byte what was retrieved. The pipeline reads them read-only and proves after every run that they are unchanged.
- **Derived data is ours.** Sessions, derived selected meal weights, component counts, flags, metrics and the sensitivity analysis are our reconstruction and are labelled DERIVED. They are not published by the data providers.
- **Indication of changes (CC BY 4.0).** No provider data was altered. Analytical transformations (session reconstruction, a file-specific +3 hour timestamp normalization for one file, string normalisation of component names) happen in downstream tables and are documented in `data_dictionary.md` and `timezone_decision.md`. The +3h normalization is an evidence-backed engineering decision; the source does not confirm its timezone.
- **No fabricated data.** No waste, consumption or customer value was created or estimated.

## 3. Snapshot register

A **source snapshot** is an immutable, checksum-identified set of raw artifacts from one source. Its identifier is derived from
content (SHA-256 and size of each artifact), never from time, so identical bytes always give the same identifier and any changed
byte gives a new one. Every downstream record carries a `source_snapshot_id` and can be traced to the raw artifact, its checksum,
its source URL and its retrieval metadata (`outputs/ingestion/raw_artifact_manifest.csv`).

| Snapshot | Source | Lane | Status |
|---|---|---|---|
| `flavoria-1b68c194acc5` | Flavoria (12 artifacts: archive + 11 members) | core | VERIFIED |
| `fmi-8ab7d7d344b4` | FMI weather (7 chunk files) | context | VERIFIED |

Input fingerprint of the complete set of inputs: `3f71e643244182b4`.

### 3.1 Flavoria archive

| File | Bytes | MD5 (published by Zenodo) | SHA-256 |
|---|---:|---|---|
| dataset_csv.tar | 1,277,440 | 74410f922287ceffbd8092d7dd4e5530 | 7f7e46f0a50683b61f8dde67b097ed8f4130a9503866f045cc4f40eee2c0207d |

### 3.2 Flavoria archive members (extracted in memory; the archive is the raw artifact)

| File | Bytes | Data rows | SHA-256 |
|---|---:|---:|---|
| non_registered_2020-10-05_2020-10-18.csv | 138,343 | 1313 | b8132640bc606a2b51fbe622536fd147b8486ae393e6796e629b6a7872be6056 |
| non_registered_2020-10-19_2020-10-25.csv | 75,590 | 698 | f4b29b301e88ad7221519c4a20f538871dfcd5fb6b9236a33d8e90c41b78ad29 |
| non_registered_2020-10-25_2020-10-31.csv | 72,766 | 721 | fddb0dae7109e0dcb7007eca06d0ee048a3ec13a7356227eff5dba7ecae3873c |
| non_registered_2020-11-02_2020-11-08.csv | 61,363 | 600 | 7902cba6812f04f6be2ea161faded9756784b80b23bb85f98e6e7e7de8c96b13 |
| non_registered_2020-11-09_2020-11-15.csv | 58,257 | 580 | 3c122adad7e5a81c39a3437262c53b796832e3f34cfdc0837ca6592ecc76ba99 |
| registered_2020-10-19_2020-10-25.csv | 147,633 | 1352 | 53ab99bd9fb8574448444908360dbbfcb52acc7e039e429930c1a85445f04d41 |
| registered_2020-10-25_2020-10-31.csv | 141,369 | 1396 | 038216ba25cc78fc6af89a6a84e6a731a0b745773dafd66e3684fe4ec42b7e7d |
| registered_2020-11-02_2020-11-08.csv | 154,303 | 1526 | a4ef75e53ede43d5c70921b643ab99e1912bcf82f1e0c8d833f81a2dc7688154 |
| registered_2020-11-09_2020-11-15.csv | 130,542 | 1305 | 467ccab0e3930068bef36650e9562f43b91f22138229ecf126eacff55e70b501 |
| registered_2020-11-16_2020-11-20.csv | 87,428 | 862 | b05454dedfc8accab0a980b2551a968fd093c5da17f2c483e55aa3cb9777d4a2 |
| registered_2020_10_05-2020_10_18.csv | 200,546 | 1931 | be5c8513eaac522cb4a396fc842094024733de4511498fe1e7d1c903348954b4 |

Total data rows: 12,284. Two header variants exist (with and without `weighting_type`); each file's header fingerprint is in
`outputs/ingestion/schema_fingerprints.csv`.

### 3.3 FMI weather chunks

| File | Bytes | SHA-256 |
|---|---:|---|
| fmi_100949_20201005_20201011.xml | 413,676 | 20d267f18b97dd7ee8a7d3e6999134989e1741da8df8f364fee10a95d40e346a |
| fmi_100949_20201012_20201018.xml | 413,537 | 2ea81634d9a29831d444ec61c3c3fbec936d3518e260c4ac4eadb0c330b74519 |
| fmi_100949_20201019_20201025.xml | 413,560 | 25ea3dd894df0ab53a12491533710a5f8f0c41826ff9f74033c05e67368a9712 |
| fmi_100949_20201026_20201101.xml | 413,588 | 23df3c938695d0591a20e28871ee4e4180119b63a2ecf3e911c33a79e53f44a2 |
| fmi_100949_20201102_20201108.xml | 413,567 | 23be71cfde2dc550a75badecf2a2c99fa010e6f45098469142906eb01b98d71f |
| fmi_100949_20201109_20201115.xml | 413,524 | 6fbd347358e42e3fef087c3541970c85fde554057f94e62b9a4d84905ddc7772 |
| fmi_100949_20201116_20201121.xml | 297,794 | 6b1f778dfc4fceae9ad27d4699e33c813632fadc803f90f1fd4e9e7af2118e42 |

Each response embeds the time it was generated, so re-retrieving produces different **bytes** with identical **content**. The
pins therefore also record a content signature (`content_sha256`, in `config/sources.yml`), and a re-retrieval is reported as
content-identical or not (this was checked by a real explicit retrieval on 2026-09-18 and the content was identical; the check output was discarded, not committed).

### 3.4 Preserved evidence (not pipeline inputs, not part of snapshot identity)

| File | Bytes | SHA-256 |
|---|---:|---|
| probe_fmi_100949_20201021_20201023_10min_r1h_semantics.xml | 193,587 | 0de87195e9884d8a5ab0fe5b91ffc2146e1b92273604baa32d2e5d13bdeb51c6 |
| stations.xml | 472,383 | 4c5b06e5f4f3ef8d164a824b5ae0c35d37d44f505c6cf61e8b8a3134a61c15e6 |

## 4. Retrieval and refresh policy

- **A normal run is offline.** `python -m src.pipeline.run` never downloads. If a required raw source is missing it fails clearly and
  names the retrieval command.
- **Retrieval is explicit.** `python -m src.pipeline.fetch --source flavoria|weather`. It never overwrites an existing raw file and
  never edits a pin.
- **A refreshed source is a new snapshot**, written to its own `refresh-<time>/` directory with a `snapshot.json` recording the URL,
  time, HTTP status, response headers and checksums.
- **Adopting a refreshed snapshot is a deliberate act**: copy the files, update `config/sources.yml` (the fetch command prints the pin
  lines with `--print-pins`), and record the decision in `decision_log.md`. The pipeline never does this by itself.
- **Mismatch handling.** A size, checksum or row-count mismatch is FAILED. Nothing is silently re-downloaded or re-pinned.

## 5. Open provenance items

| Item | Status |
|---|---|
| FMI attribution wording | not prescribed by FMI; our wording is in `NOTICE` |
| Flavoria Data Catalog terms | none found on the pages reviewed; only short quotations used |
| Licence for this project's own code and documentation | **MIT** (`LICENSE`); it does not apply to the third-party data, which stays under CC BY 4.0 |
| Confirmation of the population labels and of the timezone of one file | source owner (Q1, Q3); not a licensing matter |

## 6. Ownership and public-accessibility limits

- **No ownership is claimed** over FlavoriaFoodWeight1700 or the FMI observations. They belong to their providers, are licensed CC BY 4.0, and are redistributed unmodified with attribution (`NOTICE`).
- **Accessibility limits.** The waste, checkout (Weigh & Dine), cash-register, building, MyFlavoria and survey data are documented but not publicly accessible in a usable form. None of it is held or reproduced; the consequence is the permanent source gap in `source_gap_register.md`.
- **Catalogue terms unknown.** The Flavoria Data Catalog states no licence or terms on the pages reviewed. We do not assume any: pages are read as documentation, quoted briefly with links, and not redistributed.
- **Redistribution of raw data.** The 1.28 MB archive and the seven weather XML files (about 4 MB in total) are committed unmodified because CC BY 4.0 permits it and because it lets a fresh clone run offline. This is a deliberate decision by the project owner (D69): the raw data stays in the public repository. Removing it was considered and rejected because the weather bytes cannot be re-retrieved identically (FMI stamps each response), so a fresh clone could not reproduce the pinned state.
- **Scope statement.** The project is an FDE-style reconstruction using public research data. It is not an analysis of Flavoria's operational systems and does not represent all current dining operations.
