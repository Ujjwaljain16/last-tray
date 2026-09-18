"""Phase 2 section M: apply the draft rules to the real data, write validation_issues.csv, derive threshold evidence
and a KPI sensitivity PREVIEW. Exploratory: the production validator will live in src/validate/."""
import json

import pandas as pd

from phase2_common import OUT, UTC_FILES, exact_dup_mask

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
e = pd.read_pickle(OUT / "_events.pkl")
s = pd.read_pickle(OUT / "_sessions.pkl")
e["dup"] = exact_dup_mask(e)
REG, NON = "registered_export", "non_registered_export"
xo = set(s[s.crossover].session_id)
issues = []


def add(rule, cat, sev, etype, eid, pop, src, msg, handling, cons):
    issues.append(dict(rule_id=rule, category=cat, severity=sev, entity_type=etype, entity_id=eid, population=pop,
                       source_file=src, message=msg, handling=handling, business_consequence=cons))


# Proposed thresholds. Evidence for each is in docs/phase2_profile_report.md section 9.
TH = dict(event_warn_g=1500, trace_g=3, session_low_g=50, session_high_g=2200, span_warn_s=600, gap_warn_s=300,
          hour_lo=9, hour_hi=15, t07_lo=10.0, t07_hi=11.0, low_volume_sessions=30)

sd = pd.read_csv(OUT / "schema_drift_by_file.csv")
tzv = pd.read_csv(OUT / "timezone_validation_by_file.csv")
for _, r in sd.iterrows():
    if not r.has_weighting_type:
        add("S03", "STRUCTURAL", "INFO", "file", r.file, r.population, r.file,
            "optional column weighting_type absent", "FLAG", "none: only value ever seen is 'line'")
    if "." in str(r.ts_format_weighing) or "." in str(r.ts_format_identification):
        add("T08", "TEMPORAL", "INFO", "file", r.file, r.population, r.file,
            f"dotted timestamp format (weighing: {r.ts_format_weighing}; identification: {r.ts_format_identification})",
            "FLAG", "parser must accept both formats")
for _, r in tzv.iterrows():
    if r.T07_suspect_raw:
        add("T07", "TEMPORAL", "WARN", "file", r.file, REG, r.file,
            f"median first-event hour {r.median_first_event_hour_raw} outside 10:00-11:00; "
            f"{int(r.events_before_10h_raw)} events before 10:00",
            "FLAG; +3h normalisation applied via per-file override (strongest-supported decision, not source-confirmed)",
            "weather join and time-of-day analysis would be 3h off")
add("C03", "COMPLETENESS", "WARN", "file", "non_registered_2020-11-16_2020-11-20.csv (absent)", NON, "",
    "no non-registered-export file for 2020-11-16..20; export ends 2020-11-13", "FLAG",
    "non-registered-export diagnostic coverage is 30 of 35 service days")

ev = e.copy()
ev["hour"] = ev.t.dt.hour
for r in ev[ev.dup].itertuples():
    add("I02", "IDENTITY", "WARN", "event", f"{r.source_file}#{r.source_row_number}", r.population, r.source_file,
        f"exact duplicate of an earlier row ({r.session_id}, {r.scale_identifier}, {int(r.w)} g)",
        "KEEP FIRST; repeat excluded from sums", "prevents double-counted grams")
for r in ev[ev.w >= TH["event_warn_g"]].itertuples():
    add("B02", "BUSINESS", "WARN", "event", f"{r.source_file}#{r.source_row_number}", r.population, r.source_file,
        f"event weight {int(r.w)} g >= {TH['event_warn_g']} g on {r.scale_identifier}", "FLAG; kept in sums",
        "large value may be a plate/tray artefact or a genuine bulk portion")
for r in ev[(ev.w <= TH["trace_g"]) & ~ev.dup].itertuples():
    add("B03", "BUSINESS", "INFO", "event", f"{r.source_file}#{r.source_row_number}", r.population, r.source_file,
        f"trace weight {int(r.w)} g", "FLAG; kept", "may be scale noise or a garnish")
for r in ev[(ev.hour < TH["hour_lo"]) | (ev.hour >= TH["hour_hi"])].itertuples():
    add("T03", "TEMPORAL", "ERROR", "event", f"{r.source_file}#{r.source_row_number}", r.population, r.source_file,
        f"event at {r.t} outside 09:00-15:00 local after timezone rule", "QUARANTINE", "clock problem")

for r in s[s.crossover].itertuples():
    add("I01", "IDENTITY", "ERROR", "session", f"{r.session_id}|{r.population}", r.population, r.source_file,
        "session_id present in both populations", "QUARANTINE both versions; excluded from primary metrics",
        "no authority chosen")
add("I06", "IDENTITY", "WARN", "session", "session3222|both", "both", "",
    "cross-export versions disagree: all timestamps differ by exactly 10,800 s; 2 of 6 component names differ "
    "(Punakaali vs Marinoitu kaalisalaatti; Paahdettuja kasviksia vs Parsakaali-kukkakaali)", "FLAG",
    "supports the +3h decision; shows menu-lookup instability")
add("I06", "IDENTITY", "INFO", "session", "session2266|both", "both", "",
    "cross-export versions identical event-for-event (5 of 5); the non-registered file lists events newest-first",
    "FLAG", "exact cross-export duplicate")
one = s[s.component_weighing_event_count.eq(1) & s.population.eq(REG) & ~s.crossover]
for r in one.itertuples():
    add("B04", "BUSINESS", "WARN", "session", f"{r.session_id}|{r.population}", r.population, r.source_file,
        "registered-export session with a single weighing event", "FLAG; kept",
        "may be a single-item lunch or a partial capture")
lohi = s[(s.derived_selected_meal_weight_g < TH["session_low_g"]) | (s.derived_selected_meal_weight_g > TH["session_high_g"])]
for r in lohi.itertuples():
    add("B07", "BUSINESS", "WARN", "session", f"{r.session_id}|{r.population}", r.population, r.source_file,
        f"derived_selected_meal_weight_g {int(r.derived_selected_meal_weight_g)} outside "
        f"[{TH['session_low_g']}, {TH['session_high_g']}]", "FLAG; kept", "extreme sessions influence P90")
for r in s[s.session_span_s > TH["span_warn_s"]].itertuples():
    add("T05", "TEMPORAL", "WARN", "session", f"{r.session_id}|{r.population}", r.population, r.source_file,
        f"session span {int(r.session_span_s)} s > {TH['span_warn_s']} s (a within-session gap suggests a second pass)",
        "FLAG; kept", "may merge two tray passes")
for r in s[s.identified_minus_last_s < 0].itertuples():
    add("T04", "TEMPORAL", "WARN", "session", f"{r.session_id}|{r.population}", r.population, r.source_file,
        f"identification {int(r.identified_minus_last_s)} s before last weighing", "FLAG; kept",
        "workflow order assumption violated")
edc = e[~e.dup & ~e.session_id.isin(xo)].sort_values(["population", "session_id", "t"])
rep = edc[edc.duplicated(["population", "session_id", "scale_identifier"], keep=False)]
for (pop, sid), g in rep.groupby(["population", "session_id"]):
    add("B05", "BUSINESS", "INFO", "session", f"{sid}|{pop}", pop, g.source_file.iloc[0],
        f"same scale weighed {len(g)} times (additive scoops; 100% same component name)", "FLAG; summed",
        "derived weight includes repeat scoops")

# ---- C02 volume regime -------------------------------------------------------------------------
day = s[~s.crossover].groupby(["service_date", "population"]).size().unstack()
wd = pd.Series(pd.to_datetime(day.index).day_name(), index=day.index)
is_mwd = wd.isin(["Monday", "Tuesday", "Wednesday"])
base_idx = [d for d in day.index if d <= pd.Timestamp("2020-10-30").date()]
print("baseline weeks (Oct 5-30): Mon-Wed min", int(day.loc[base_idx][REG][is_mwd.loc[base_idx]].min()),
      "| Thu-Fri max", int(day.loc[base_idx][REG][~is_mwd.loc[base_idx]].max()))
regime_exp = is_mwd.map({True: "high", False: "low"})
obs = day[REG].map(lambda v: "high" if v >= TH["low_volume_sessions"] else "low")
irr = day[REG][obs != regime_exp]
lowdays = day[REG][day[REG] < TH["low_volume_sessions"]]
print("registered-export days classed low (<30):", len(lowdays), "of", len(day),
      "| irregular vs weekday regime:", {str(k): int(v) for k, v in irr.items()})
print("non-registered-export daily sessions: min", int(day[NON].min()), "max", int(day[NON].max()),
      "| min in high regime days? weekday means:", day[NON].groupby(wd).mean().round(1).to_dict())
for d, v in irr.items():
    add("C02", "COMPLETENESS", "WARN", "service_day", str(d), REG, "",
        f"volume irregularity: {int(v)} registered-export sessions on a {wd[d]} (expected regime {regime_exp[d]}); "
        "cause unresolved, NOT labelled a data error", "FLAG volume_irregularity=true; retained in analytical population",
        "M3 must not be read as restaurant demand")
add("C02", "COMPLETENESS", "INFO", "population", REG, REG, "",
    f"{len(lowdays)} of {len(day)} service days have < {TH['low_volume_sessions']} registered-export sessions "
    "(Thursday and Friday are usually low: weekday medians 8 and 11)", "FLAG low_observed_volume_day",
    "volume comparisons across days are not like-for-like")

vi = pd.DataFrame(issues)
vi.insert(0, "issue_id", range(1, len(vi) + 1))
vi.insert(1, "run_id", "phase2_exploration")
vi.to_csv(OUT.parent / "validation" / "validation_issues.csv", index=False)
summ = vi.assign(population=vi.population.fillna("n/a")).groupby(["rule_id", "category", "severity", "population"]).agg(issues=("issue_id", "size"), entities=("entity_id", "nunique")).reset_index()
summ.to_csv(OUT.parent / "validation" / "validation_summary_by_rule.csv", index=False)
print("\nvalidation issues:", len(vi))
print(summ.to_string(index=False))

# ---- KPI sensitivity PREVIEW (not final metrics) ------------------------------------------------
sr = s[s.population == REG].copy()
warn_ids = set(vi[(vi.entity_type == "session") & (vi.severity == "WARN")].entity_id.str.split("|").str[0])
sr["warn"] = sr.session_id.isin(warn_ids) & ~sr.crossover
day_irr = set(irr.index)


def kp(d, label):
    w = d.derived_selected_meal_weight_g
    return dict(scenario=label, sessions=len(d), M1_median_g=w.median(), M2_p90_g=w.quantile(.9),
                M4_median_components=d.distinct_component_count.median())


prim = sr[~sr.crossover]
rows = [kp(prim, "PRIMARY: registered-export, crossover quarantined"),
        kp(prim[~prim.warn], "exclude any session with a WARN rule"),
        kp(prim[~prim.source_file.isin(UTC_FILES)], "exclude the +3h-normalised file (timezone independence)"),
        kp(prim[~prim.service_date.isin(day_irr)], "exclude volume-irregularity days"),
        kp(prim[pd.to_datetime(prim.service_date) < pd.Timestamp("2020-11-16")], "exclude Nov 16-20"),
        kp(prim[prim.component_weighing_event_count > 1], "exclude single-event sessions"),
        kp(prim[prim.session_id != "session2104"], "exclude the 2,097 g session"),
        kp(sr, "include the 2 crossover sessions (unquarantined)")]
kd = pd.DataFrame(rows).round(2)
kd["M1_delta_g"] = (kd.M1_median_g - kd.M1_median_g.iloc[0]).round(1)
kd["M2_delta_g"] = (kd.M2_p90_g - kd.M2_p90_g.iloc[0]).round(1)
kd.to_csv(OUT / "kpi_sensitivity_preview.csv", index=False)
print("\nKPI SENSITIVITY PREVIEW (not final evidence):")
print(kd.to_string(index=False))
elig = len(sr)
ready = int((~sr.crossover).sum())
clean = int(((~sr.crossover) & (~sr.warn)).sum())
print(f"\nM5 preview: core_ready {ready}/{elig} = {100 * ready / elig:.2f}% ; warn-free {clean}/{elig} = {100 * clean / elig:.2f}%")
print("sessions with span in (300,1700):", int(((s.session_span_s > 300) & (s.session_span_s < 1700)).sum()),
      "| registered sessions >2200 g:", int((sr.derived_selected_meal_weight_g > 2200).sum()),
      "| <50 g:", int((sr.derived_selected_meal_weight_g < 50).sum()))
print("registered-export largest spans (s):", sr.session_span_s.sort_values().tail(12).astype(int).tolist())
print("WARN sessions among primary:", int(sr.warn.sum()), "| by rule:",
      vi[(vi.entity_type == "session") & (vi.severity == "WARN")].rule_id.value_counts().to_dict())
json.dump(dict(thresholds=TH, m5=dict(ready=ready, elig=elig, warn_free=clean),
               irregular_days=[str(k) for k in irr.index], low_days=len(lowdays), days=len(day)),
          open(OUT / "results_d.json", "w"), indent=1)
