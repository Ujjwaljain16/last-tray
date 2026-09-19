"""Typed, validated configuration.

Judgement lives in config/*.yml, not in code paths. This module loads those files and refuses to continue when a
value would silently change an analytical decision: for example a timezone marked "source confirmed", volume flags
that are allowed to exclude data, or a waste source that is not BLOCKED.

Every failure raises ConfigError with the file and the reason, so a bad edit is caught before any data is touched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from src.vocab import Handling, Population, Severity, TimezoneNormalization

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
OPERATORS = {">", ">=", "<", "<="}
GAP_STATUSES = {"BLOCKED", "NOT_RETRIEVABLE", "RESTRICTED"}


class ConfigError(Exception):
    """A configuration file is missing, malformed, or would change an approved decision."""


# ---- approved decisions that configuration may NOT change (one place; every check below reads these) ------------------------------------------------
APPROVED_OVERRIDE_OFFSET_HOURS = 3        # the file-specific normalization; its label NORMALISED_PLUS_3H_STRONGEST_SUPPORT names it
APPROVED_READINESS_DENOMINATOR = "registered_export_session_ids_in_source"      # M5's denominator, counted before any removal or quarantine
# (severity, handling) of every rule that config/thresholds.yml declares. A WARN or INFO rule may only FLAG; only T03 quarantines here.
APPROVED_TREATMENT: dict[str, tuple[str, str]] = {
    "B02": ("WARN", "FLAG"), "B03": ("INFO", "FLAG"), "B07": ("WARN", "FLAG"), "T05": ("WARN", "FLAG"), "T03": ("ERROR", "QUARANTINE"),
    "T07": ("WARN", "FLAG"), "C02a": ("INFO", "FLAG"), "C02b": ("WARN", "FLAG"),
}
NETWORK_KEY_PARTS = ("auto_fetch", "auto_retriev", "auto_download", "download_on_missing", "fetch_on_missing", "allow_network", "network_retrieval")


# ---- thresholds -----------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    rule_id: str
    description: str
    severity: Severity
    handling: Handling
    rationale: str
    parameter: str | None = None
    operator: str | None = None
    value: float | None = None
    low: float | None = None
    high: float | None = None


@dataclass(frozen=True)
class VolumeConfig:
    high_regime_min_sessions: int
    baseline_start: date
    baseline_end: date
    expected_regime_by_weekday: dict[str, str]
    flag_only: bool


@dataclass(frozen=True)
class Thresholds:
    statement: str
    approved_on: date
    rules: dict[str, Rule]
    volume: VolumeConfig


# ---- timezone ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OverrideScope:
    """Where a file-specific normalization is valid (rule T10)."""

    first_event_date: date
    last_event_date: date
    raw_median_first_event_hour_band: tuple[float, float]


@dataclass(frozen=True)
class TimezoneOverride:
    """A FILE-SPECIFIC, evidence-backed normalization. Never a statement about a timezone in general."""

    filename: str
    offset_hours: int
    label: TimezoneNormalization
    source_confirmed: bool
    applies_to_columns: tuple[str, ...]
    residual_uncertainty: str
    valid_for: OverrideScope


@dataclass(frozen=True)
class TimezoneConfig:
    default_assume: str
    default_label: TimezoneNormalization
    overrides: dict[str, TimezoneOverride]
    statement: str


# ---- populations ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class PopulationRule:
    code: Population
    display_name: str
    filename_prefix: str
    role: str  # primary | diagnostic


@dataclass(frozen=True)
class PopulationsConfig:
    statement: str
    rules: tuple[PopulationRule, ...]
    never_pooled: bool
    forbidden_phrases: tuple[str, ...]

    @property
    def primary(self) -> PopulationRule:
        return next(r for r in self.rules if r.role == "primary")

    def population_for_filename(self, filename: str) -> Population:
        """Population from the filename prefix. Exactly one rule must match."""
        hits = [r for r in self.rules if filename.startswith(r.filename_prefix)]
        if len(hits) != 1:
            raise ConfigError(f"{filename!r} matches {len(hits)} population prefixes; expected exactly 1")
        return hits[0].code


# ---- sources ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MemberSpec:
    file: str
    bytes: int
    sha256: str
    rows: int
    weighting_type: bool


@dataclass(frozen=True)
class FlavoriaSource:
    record_url: str
    version: str
    doi: str
    license: str
    attribution: str
    archive_filename: str
    archive_url: str
    archive_path: str
    archive_size_bytes: int
    archive_md5: str
    archive_sha256: str
    archive_retrieved_on: date
    archive_retrieval_method: str
    schema_variants: dict[str, tuple[str, ...]]
    expected_total_rows: int
    expected_session_ids: int
    required_columns: tuple[str, ...]
    optional_columns: tuple[str, ...]
    members: tuple[MemberSpec, ...]
    window_start: date
    window_end: date


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_base_seconds: float
    backoff_factor: float
    timeout_seconds: float


@dataclass(frozen=True)
class RawFileSpec:
    file: str
    bytes: int
    sha256: str
    content_sha256: str | None = None   # sha256 of the sorted 'time|param|value' triples (weather chunks)
    elements: int | None = None


@dataclass(frozen=True)
class WeatherSource:
    endpoint: str
    local_dir: str
    request: dict[str, Any]
    fmisid: int
    max_hours_per_request: int
    chunk_hours: int
    window_start: str
    window_end: str
    expected_hours: int
    r_1h_convention: str
    retry: RetryPolicy
    raw_files: tuple[RawFileSpec, ...]
    evidence_files: tuple[RawFileSpec, ...]
    retrieved_on: date
    retrieval_method: str
    license: str
    license_url: str
    license_terms_url: str
    license_verified_on: date


@dataclass(frozen=True)
class GapSource:
    key: str
    name: str
    status: str
    evidence: str
    required_extract: str | None = None


@dataclass(frozen=True)
class SourcesConfig:
    flavoria: FlavoriaSource
    weather: WeatherSource
    gaps: dict[str, GapSource]


@dataclass(frozen=True)
class Config:
    thresholds: Thresholds
    timezone: TimezoneConfig
    populations: PopulationsConfig
    sources: SourcesConfig
    config_dir: Path = field(default=DEFAULT_CONFIG_DIR)


# ---- helpers ----------------------------------------------------------------------------------------------------
def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"missing configuration file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return data


def _need(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d or d[key] is None:
        raise ConfigError(f"{where}: missing required key '{key}'")
    return d[key]


def _enum(cls: type, raw: Any, where: str):
    try:
        return cls(raw)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in cls)
        raise ConfigError(f"{where}: {raw!r} is not one of [{allowed}]") from exc


def _hex(value: Any, length: int, where: str) -> str:
    s = str(value).lower()
    if len(s) != length or any(c not in "0123456789abcdef" for c in s):
        raise ConfigError(f"{where}: expected {length} hex characters, got {value!r}")
    return s


# ---- loaders ----------------------------------------------------------------------------------------------------
def load_thresholds(path: Path) -> Thresholds:
    d = _read(path)
    name = path.name
    statement = str(_need(d, "statement", name)).strip()
    if "not claims of physical impossibility" not in statement.replace("\n", " "):
        raise ConfigError(f"{name}: the statement must say the thresholds are not claims of physical impossibility")
    rules: dict[str, Rule] = {}
    for rid, r in _need(d, "rules", name).items():
        where = f"{name}: rule {rid}"
        rule = Rule(
            rule_id=rid,
            description=str(_need(r, "description", where)),
            severity=_enum(Severity, _need(r, "severity", where), where),
            handling=_enum(Handling, _need(r, "handling", where), where),
            rationale=str(_need(r, "rationale", where)),
            parameter=r.get("parameter"),
            operator=r.get("operator"),
            value=r.get("value"),
            low=r.get("low"),
            high=r.get("high"),
        )
        if rule.operator is not None and rule.operator not in OPERATORS:
            raise ConfigError(f"{where}: operator {rule.operator!r} not in {sorted(OPERATORS)}")
        if (rule.low is None) != (rule.high is None):
            raise ConfigError(f"{where}: 'low' and 'high' must be given together")
        if rule.low is not None and not rule.low < rule.high:
            raise ConfigError(f"{where}: low ({rule.low}) must be below high ({rule.high})")
        rules[rid] = rule
    for rid, rule in rules.items():
        approved = APPROVED_TREATMENT.get(rid)
        if approved is not None and (rule.severity.value, rule.handling.value) != approved:
            raise ConfigError(f"{name}: rule {rid} must be {approved[0]}/{approved[1]}; changing its severity or handling would change an approved decision "
                              "(a WARN or INFO rule never excludes a record; only ERROR rules quarantine)")
        if approved is None and rule.handling in (Handling.QUARANTINE, Handling.BLOCK) and rule.severity is not Severity.ERROR:
            raise ConfigError(f"{name}: rule {rid} excludes or blocks but is not ERROR: a non-ERROR rule may only FLAG")
    denominator = (d.get("readiness") or {}).get("eligible_denominator")
    if denominator != APPROVED_READINESS_DENOMINATOR:
        raise ConfigError(f"{name}: readiness.eligible_denominator must be {APPROVED_READINESS_DENOMINATOR!r}, got {denominator!r}. "
                          "M5's denominator is fixed before any removal or quarantine; changing it changes the meaning of M5")
    v = _need(d, "volume", name)
    regimes = _need(v, "expected_regime_by_weekday", f"{name}: volume")
    if set(regimes) != set(WEEKDAYS) or not set(regimes.values()) <= {"high", "low"}:
        raise ConfigError(f"{name}: volume.expected_regime_by_weekday must map Monday..Friday to high/low")
    if v.get("flag_only") is not True:
        raise ConfigError(f"{name}: volume flags must be flag_only: true. They never exclude a day or session from the KPI population")
    volume = VolumeConfig(
        high_regime_min_sessions=int(_need(v, "high_regime_min_sessions", f"{name}: volume")),
        baseline_start=_need(v["baseline_window"], "start", f"{name}: volume.baseline_window"),
        baseline_end=_need(v["baseline_window"], "end", f"{name}: volume.baseline_window"),
        expected_regime_by_weekday=dict(regimes),
        flag_only=True,
    )
    return Thresholds(statement=statement, approved_on=_need(d, "approved_on", name), rules=rules, volume=volume)


def load_timezone(path: Path) -> TimezoneConfig:
    d = _read(path)
    name = path.name
    default = _need(d, "default", name)
    overrides: dict[str, TimezoneOverride] = {}
    for fname, o in (d.get("overrides") or {}).items():
        where = f"{name}: override {fname}"
        label = _enum(TimezoneNormalization, _need(o, "label", where), where)
        if label is not TimezoneNormalization.NORMALISED_PLUS_3H_STRONGEST_SUPPORT:
            raise ConfigError(f"{where}: an override must carry the NORMALISED_PLUS_3H_STRONGEST_SUPPORT label")
        if int(_need(o, "offset_hours", where)) != APPROVED_OVERRIDE_OFFSET_HOURS:
            raise ConfigError(f"{where}: offset_hours must be {APPROVED_OVERRIDE_OFFSET_HOURS}. The approved normalization is the file-specific "
                              f"+{APPROVED_OVERRIDE_OFFSET_HOURS}h named by its label; another offset is a sensitivity scenario, never a configuration")
        if o.get("source_confirmed") is not False:
            raise ConfigError(
                f"{where}: source_confirmed must be false. The +3h normalisation is an evidence-backed engineering decision; "
                "the source does not confirm its timezone. Update docs/timezone_decision.md before changing this."
            )
        if o.get("scope") != "file_specific":
            raise ConfigError(f"{where}: scope must be 'file_specific'. A timezone normalization is never applied generally")
        vf = _need(o, "valid_for", where)
        band = _need(vf, "raw_median_first_event_hour_band", f"{where}: valid_for")
        first_d, last_d = _need(vf, "first_event_date", f"{where}: valid_for"), _need(vf, "last_event_date", f"{where}: valid_for")
        if not (isinstance(first_d, date) and isinstance(last_d, date) and first_d <= last_d):
            raise ConfigError(f"{where}: valid_for dates must be real dates with first_event_date <= last_event_date")
        if len(band) != 2 or not band[0] < band[1]:
            raise ConfigError(f"{where}: raw_median_first_event_hour_band must be [low, high] with low < high")
        overrides[fname] = TimezoneOverride(
            filename=fname,
            offset_hours=int(_need(o, "offset_hours", where)),
            label=label,
            source_confirmed=False,
            applies_to_columns=tuple(_need(o, "applies_to_columns", where)),
            residual_uncertainty=str(_need(o, "residual_uncertainty", where)),
            valid_for=OverrideScope(first_d, last_d, (float(band[0]), float(band[1]))),
        )
    default_label = _enum(TimezoneNormalization, _need(default, "label", f"{name}: default"), f"{name}: default")
    if default_label is not TimezoneNormalization.SOURCE_LOCAL_ASSUMED:
        raise ConfigError(f"{name}: the default treatment must be SOURCE_LOCAL_ASSUMED: no zone is stated by the source")
    return TimezoneConfig(
        default_assume=str(_need(default, "assume", f"{name}: default")),
        default_label=default_label,
        overrides=overrides,
        statement=str(_need(d, "statement", name)).strip(),
    )


def load_populations(path: Path) -> PopulationsConfig:
    d = _read(path)
    name = path.name
    rules = tuple(
        PopulationRule(
            code=_enum(Population, code, f"{name}: {code}"),
            display_name=str(_need(p, "display_name", f"{name}: {code}")),
            filename_prefix=str(_need(p, "filename_prefix", f"{name}: {code}")),
            role=str(_need(p, "role", f"{name}: {code}")),
        )
        for code, p in _need(d, "populations", name).items()
    )
    if {r.code for r in rules} != set(Population):
        raise ConfigError(f"{name}: must define exactly the populations {[p.value for p in Population]}")
    if sorted(r.role for r in rules) != ["diagnostic", "primary"]:
        raise ConfigError(f"{name}: exactly one 'primary' and one 'diagnostic' population are required")
    if d.get("never_pooled") is not True:
        raise ConfigError(f"{name}: never_pooled must be true; the populations are never pooled")
    return PopulationsConfig(
        statement=str(_need(d, "statement", name)).strip(),
        rules=rules,
        never_pooled=True,
        forbidden_phrases=tuple(d.get("forbidden_phrases") or ()),
    )


def _forbid_automatic_retrieval(node: Any, name: str, trail: str = "") -> None:
    """Normal execution is offline. No configuration key may switch on automatic retrieval or downloading."""
    if isinstance(node, dict):
        for key, value in node.items():
            where = f"{trail}.{key}" if trail else str(key)
            if any(part in str(key).lower() for part in NETWORK_KEY_PARTS) and value not in (False, None, 0, "", "never"):
                raise ConfigError(f"{name}: {where} enables automatic network retrieval. Retrieval is explicit only: python -m src.pipeline.fetch")
            _forbid_automatic_retrieval(value, name, where)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _forbid_automatic_retrieval(value, name, f"{trail}[{i}]")


def load_sources(path: Path) -> SourcesConfig:
    d = _read(path)
    name = path.name
    _forbid_automatic_retrieval(d, name)
    f = _need(d, "flavoria", name)
    arc = _need(f, "archive", f"{name}: flavoria")
    members = tuple(
        MemberSpec(str(m["file"]), int(m["bytes"]), _hex(m["sha256"], 64, f"{name}: member {m['file']}"), int(m["rows"]), bool(m["weighting_type"]))
        for m in _need(f, "members", f"{name}: flavoria")
    )
    window = _need(f, "study_window", f"{name}: flavoria")
    flavoria = FlavoriaSource(
        record_url=str(_need(f, "record_url", name)),
        version=str(_need(f, "version", name)),
        doi=str(_need(f, "doi", name)),
        license=str(_need(f, "license", name)),
        attribution=str(_need(f, "attribution", name)),
        archive_filename=str(_need(arc, "filename", name)),
        archive_url=str(_need(arc, "download_url", name)),
        archive_path=str(_need(arc, "local_path", name)),
        archive_size_bytes=int(_need(arc, "size_bytes", name)),
        archive_md5=_hex(_need(arc, "md5", name), 32, f"{name}: archive.md5"),
        archive_sha256=_hex(_need(arc, "sha256", name), 64, f"{name}: archive.sha256"),
        archive_retrieved_on=_need(arc, "retrieved_on", name),
        archive_retrieval_method=str(_need(arc, "retrieval_method", name)),
        schema_variants={k: tuple(str(c) for c in v) for k, v in _need(f, "schema_variants", name).items()},
        expected_total_rows=int(_need(f, "expected_total_rows", name)),
        expected_session_ids=int(_need(f, "expected_session_ids", name)),
        required_columns=tuple(_need(f, "required_columns", name)),
        optional_columns=tuple(f.get("optional_columns") or ()),
        members=members,
        window_start=_need(window, "start", name),
        window_end=_need(window, "end", name),
    )
    for vname, cols in flavoria.schema_variants.items():
        missing = [c for c in flavoria.required_columns if c not in cols]
        if missing:
            raise ConfigError(f"{name}: schema variant {vname} lacks required columns {missing}")
    if len(flavoria.schema_variants) < 1:
        raise ConfigError(f"{name}: at least one schema variant is required")
    if sum(m.rows for m in members) != flavoria.expected_total_rows:
        raise ConfigError(f"{name}: member rows sum to {sum(m.rows for m in members)}, expected_total_rows is {flavoria.expected_total_rows}")
    if len({m.file for m in members}) != len(members):
        raise ConfigError(f"{name}: duplicate member filenames")

    w = _need(d, "weather", name)
    retry = _need(w, "retry", f"{name}: weather")
    weather = WeatherSource(
        endpoint=str(_need(w, "endpoint", name)),
        local_dir=str(_need(w, "local_dir", name)),
        request=dict(_need(w, "request", name)),
        fmisid=int(_need(_need(w, "request", name), "fmisid", name)),
        max_hours_per_request=int(_need(w, "max_hours_per_request", name)),
        chunk_hours=int(_need(w, "chunk_hours", name)),
        window_start=str(_need(_need(w, "window", name), "start", name)),
        window_end=str(_need(_need(w, "window", name), "end", name)),
        expected_hours=int(_need(w, "expected_hours", name)),
        r_1h_convention=str(_need(w, "r_1h_convention", name)),
        retry=RetryPolicy(int(retry["max_attempts"]), float(retry["backoff_base_seconds"]),
                          float(retry["backoff_factor"]), float(retry["timeout_seconds"])),
        raw_files=tuple(
            RawFileSpec(r["file"], int(r["bytes"]), _hex(r["sha256"], 64, f"{name}: {r['file']}"),
                        _hex(r["content_sha256"], 64, f"{name}: {r['file']} content_sha256"), int(r["elements"]))
            for r in w["raw_files"]),
        evidence_files=tuple(RawFileSpec(r["file"], int(r["bytes"]), _hex(r["sha256"], 64, f"{name}: {r['file']}")) for r in w.get("evidence_files", [])),
        retrieved_on=_need(w, "retrieved_on", name),
        retrieval_method=str(_need(w, "retrieval_method", name)),
        license=str(_need(w, "license", name)),
        license_url=str(_need(w, "license_url", name)),
        license_terms_url=str(_need(w, "license_terms_url", name)),
        license_verified_on=_need(w, "license_verified_on", name),
    )
    if weather.chunk_hours > weather.max_hours_per_request:
        raise ConfigError(f"{name}: chunk_hours ({weather.chunk_hours}) exceeds the server limit ({weather.max_hours_per_request})")
    if weather.r_1h_convention != "hour_ending":
        raise ConfigError(f"{name}: r_1h_convention must be 'hour_ending' (profiling empirical result); change it only with new evidence")
    if weather.retry.max_attempts < 1:
        raise ConfigError(f"{name}: retry.max_attempts must be at least 1")

    gaps = {
        key: GapSource(key, str(g["name"]), str(g["status"]), str(g["evidence"]), g.get("required_extract"))
        for key, g in _need(d, "gaps", name).items()
    }
    for g in gaps.values():
        if g.status not in GAP_STATUSES:
            raise ConfigError(f"{name}: gap {g.key} has status {g.status!r}; allowed: {sorted(GAP_STATUSES)}")
    if "waste" not in gaps or gaps["waste"].status != "BLOCKED":
        raise ConfigError(f"{name}: the waste source must be present and BLOCKED. It is a source gap and is never ingested or estimated")
    if not gaps["waste"].required_extract:
        raise ConfigError(f"{name}: the waste gap must state the required extract (what integration closes the gap)")
    return SourcesConfig(flavoria=flavoria, weather=weather, gaps=gaps)


def load_config(config_dir: Path | str | None = None) -> Config:
    """Load and cross-validate every configuration file."""
    cdir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    cfg = Config(
        thresholds=load_thresholds(cdir / "thresholds.yml"),
        timezone=load_timezone(cdir / "timezone_overrides.yml"),
        populations=load_populations(cdir / "populations.yml"),
        sources=load_sources(cdir / "sources.yml"),
        config_dir=cdir,
    )
    _cross_validate(cfg)
    return cfg


def _cross_validate(cfg: Config) -> None:
    members = {m.file for m in cfg.sources.flavoria.members}
    for fname in cfg.timezone.overrides:
        if fname not in members:
            raise ConfigError(f"timezone_overrides.yml: override for {fname!r}, which is not a member of the Flavoria archive")
    for m in cfg.sources.flavoria.members:
        cfg.populations.population_for_filename(m.file)  # raises unless exactly one prefix matches
