# Source Gap Register

Verified 2026-09-18 against primary sources. "Not ingested" is not "forgotten": each row is a client data gap.

| Required business fact | Expected source | Publicly accessible? | Actual access status (evidence) | Why it matters | Impact on this project | Future integration required |
|---|---|---|---|---|---|---|
| Plate waste per tray | Flavoria Lunch Line Waste | **No** | Doc page: sample section reads "TODO, Ask!"; detail in a restricted GitLab repo; MQTT feed for authorised users only. No public download, API, schema or contact address. | Waste = selected minus returned. Without it, no waste KPI can exist. | Waste KPI = `SOURCE GAP`; `waste_weight_g` stays NULL, never 0 | Request extract (tray_id, waste_time, waste_g, waste_point, imputed flag); join on tray_id + time window |
| Total plate weight at checkout | Weigh & Dine (cash register scale) | No sample | Doc describes it; no data link | Independent check on the sum of component weights | Not available; we derive selected weight by summing S1 | Extract of WnD transactions; reconcile against derived selected weight |
| Consumption | (none) | n/a | Never measured directly anywhere; only derivable as selected − waste | The real business quantity | UNKNOWN | Needs waste + reconciliation rule |
| Transaction / cash register link | Cash Register | Restricted | Catalogue: Restricted, operator approval | Confirms a tray became a paid meal | Not available | Operator approval |
| Building occupancy / footfall | Building Data | Unspecified | Not documented publicly | Denominator for demand | Not available | Request access |
| Person-level identity | MyFlavoria | Research-controlled | registered-export files carry no user id | Repeat-diner behaviour | Not needed; session != person | n/a |
| Weather | FMI WFS | Yes | Retrieved, 0 API key | Context | Available | none |
| Images for meals | Zenodo image tar (2.4 GiB) | Yes | Not downloaded | Not needed for any core metric | Out of scope | optional |
| Menu / component metadata (diet, allergens) | Kitchen Menu | Unspecified | Not in the CSV archive | Component grouping, dietary breakdown | Component names only | Menu extract |
