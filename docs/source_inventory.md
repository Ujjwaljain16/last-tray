# Source Inventory

Generated from `outputs/source_inventory.csv` (Phase 0 spike, 2026-09-18). Full field-level detail lives in the CSV.

| ID | Source | Access | Grain | Retrievable | Joinable | Key limitation |
|---|---|---|---|---|---|---|
| S1 | FlavoriaFoodWeight1700 (CSV-only archive dataset_csv.tar) | PUBLIC (open) | 1 row = 1 component weighing event at a lunch-line scale (NOT 1 row per session) | YES | FMI weather via local hour; session_id->tray_id internal only; images NOT verified | Only weighed lunch-line stage. No total plate weight column (derive by summing). No waste. Timezone undocumented. Session != person. |
| S1b | FlavoriaFoodWeight1700 image archive (dataset_images_and_csv.tar) | PUBLIC (open) | 1 image per meal (not inspected) | YES (2,576,977,920 bytes; md5 56270b20...) | not tested | Not needed for any core metric; deliberately not downloaded |
| S2 | FMI open data WFS - fmi::observations::weather::simple | PUBLIC; no API key | 1 row = 1 parameter value at 1 station at 1 hour (60-min timestep) | YES | YES - hourly, UTC->Europe/Helsinki (DST change 2020-10-25) | Context only, never an operational restaurant measurement |
| S3 | Flavoria Data Catalog (index) | PUBLIC docs | source-level metadata | YES | n/a | Metadata source not a fact table |
| S4 | Flavoria Weigh & Dine documentation | PUBLIC docs; NO data sample | 1 transaction at checkout scale; total plate weight in g; NO component weights; +-5 g | docs only | n/a | Different system from S1 (pay-by-weight cash register scale). PLAN ERROR: S1 does have per-component weights |
| S5 | Flavoria Lunch Line Waste documentation | RESTRICTED data; docs public; Sample='TODO, Ask!' | per-tray customer waste total via RFID tray; NOT per component | NO | would join on tray_id (unverified) | Source gap - see source_gap_register.md |
| S6 | Restricted Flavoria sources (Cash Register, Building Data, MyFlavoria, Surveys) | Cash Register RESTRICTED; others unspecified | n/a | NO | n/a | Documented, not ingested |
| S7 | Published research (ACI 2025, DOI 10.3934/aci.2025011) - SECONDARY | PUBLIC | n/a | not verified | n/a | Use only for domain context after verification |
