"""FMI weather: request plan, XML parsing, completeness evidence, verification against pins.

Nothing here touches the network. The plan is shared with the explicit fetch command, so the set of requests that fetch
would make is provably the set of chunk files that are pinned (a test compares them).

Weather is CONTEXT. A weather problem blocks weather-dependent outputs only; it never blocks core outputs.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from src.config import Config, RawFileSpec, WeatherSource
from src.ingest.hashing import digest_file, sha256_of_lines
from src.ingest.model import Artifact, ArtifactStatus, Lane, LaneOutcome, Level, Message, Snapshot, WeatherChunk
from src.ingest.snapshot import snapshot_id, snapshot_sha256

SOURCE = "fmi_weather"
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
FETCH_HINT = "python -m src.pipeline.fetch --source weather"
MAX_XML_BYTES = 5 * 1024 * 1024


class WeatherParseError(Exception):
    """The response is not a usable FMI simple-feature collection."""


@dataclass(frozen=True)
class ChunkPlan:
    filename: str
    start: datetime
    end: datetime
    params: dict[str, str]

    @property
    def hours(self) -> int:
        return int((self.end - self.start) / timedelta(hours=1)) + 1

    def url(self, endpoint: str) -> str:
        return f"{endpoint}?{urlencode(self.params, safe=':,')}"


@dataclass(frozen=True)
class ParsedWeather:
    number_returned: int | None
    triples: tuple[tuple[str, str, str], ...]        # (time, parameter, raw value string)

    @property
    def parameters(self) -> tuple[str, ...]:
        return tuple(sorted({p for _, p, _ in self.triples}))

    @property
    def hours(self) -> int:
        return len({t for t, _, _ in self.triples})

    @property
    def nulls(self) -> int:
        return sum(1 for _, _, v in self.triples if v.strip().lower() == "nan")

    @property
    def content_sha256(self) -> str:
        return sha256_of_lines(sorted(f"{t}|{p}|{v}" for t, p, v in self.triples))


def parse_time(s: str) -> datetime:
    return datetime.strptime(s, TS_FORMAT).replace(tzinfo=timezone.utc)


def plan_weather_chunks(w: WeatherSource) -> list[ChunkPlan]:
    """The requests needed to cover the window without exceeding the server's per-request limit."""
    start, window_end = parse_time(w.window_start), parse_time(w.window_end)
    plans: list[ChunkPlan] = []
    base = {k: str(v) for k, v in w.request.items() if k not in ("parameters", "timestep_minutes")}
    while start <= window_end:
        end = min(start + timedelta(hours=w.chunk_hours), window_end)
        params = dict(base)
        params.update(starttime=start.strftime(TS_FORMAT), endtime=end.strftime(TS_FORMAT),
                      timestep=str(w.request["timestep_minutes"]), parameters=",".join(w.request["parameters"]))
        plans.append(ChunkPlan(f"fmi_{w.fmisid}_{start:%Y%m%d}_{end:%Y%m%d}.xml", start, end, params))
        start = end + timedelta(hours=1)
    return plans


def parse_weather_xml(data: bytes) -> ParsedWeather:
    if len(data) > MAX_XML_BYTES:
        raise WeatherParseError(f"response larger than {MAX_XML_BYTES} bytes")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise WeatherParseError(f"not well-formed XML: {exc}") from exc
    local = root.tag.rsplit("}", 1)[-1]
    if local == "ExceptionReport":
        texts = [e.text.strip() for e in root.iter() if e.tag.rsplit("}", 1)[-1] == "ExceptionText" and e.text]
        raise WeatherParseError("FMI returned an exception report: " + "; ".join(texts))
    if local != "FeatureCollection":
        raise WeatherParseError(f"unexpected root element <{local}>")
    triples = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "BsWfsElement":
            continue
        vals = {c.tag.rsplit("}", 1)[-1]: (c.text or "").strip() for c in el}
        if not {"Time", "ParameterName", "ParameterValue"} <= vals.keys():
            raise WeatherParseError("a BsWfsElement lacks Time, ParameterName or ParameterValue")
        triples.append((vals["Time"], vals["ParameterName"], vals["ParameterValue"]))
    nr = root.attrib.get("numberReturned")
    return ParsedWeather(int(nr) if nr and nr.isdigit() else None, tuple(triples))


def check_chunk_completeness(parsed: ParsedWeather, plan: ChunkPlan, expected_params: tuple[str, ...]) -> str | None:
    """None if complete, otherwise the reason it is not."""
    n = len(parsed.triples)
    if parsed.number_returned is None or parsed.number_returned != n:
        return f"numberReturned={parsed.number_returned} but {n} elements were parsed"
    if set(parsed.parameters) != set(expected_params):
        return f"parameters {parsed.parameters} != expected {tuple(sorted(expected_params))}"
    expected_n = plan.hours * len(expected_params)
    if n != expected_n:
        return f"{n} elements, expected {expected_n} ({plan.hours} hours x {len(expected_params)} parameters)"
    if len({(t, p) for t, p, _ in parsed.triples}) != n:
        return "duplicate (time, parameter) pairs"
    return None


@dataclass
class WeatherOutcome:
    snapshot: Snapshot
    artifacts: list[Artifact]
    chunks: list[WeatherChunk]
    messages: list[Message]
    outcome: LaneOutcome


def _rel(w: WeatherSource, name: str) -> str:
    return (Path(w.local_dir) / name).as_posix()


def verify_weather(cfg: Config, repo_root: Path) -> WeatherOutcome:
    w = cfg.sources.weather
    plans = {p.filename: p for p in plan_weather_chunks(w)}
    expected_params = tuple(w.request["parameters"])
    version = f"FMISID {w.fmisid}; simple observations; r_1h = {w.r_1h_convention}"
    retrieved = str(w.retrieved_on)
    messages: list[Message] = []
    pending: list[tuple[RawFileSpec, ArtifactStatus, str, object, ParsedWeather | None]] = []

    if set(plans) != {s.file for s in w.raw_files}:
        messages.append(Message(Level.ERROR, "X01", f"pinned weather files {sorted(s.file for s in w.raw_files)} do not match the request plan {sorted(plans)}"))

    all_triples: list[tuple[str, str, str]] = []
    for spec in w.raw_files:
        path = repo_root / w.local_dir / spec.file
        if not path.is_file():
            msg = f"raw weather file missing: {_rel(w, spec.file)}. Normal runs never download. Retrieve a new snapshot explicitly: {FETCH_HINT}"
            messages.append(Message(Level.ERROR, "X01", msg))
            pending.append((spec, ArtifactStatus.MISSING, msg, None, None))
            continue
        d = digest_file(path)
        if d.size != spec.bytes:
            st, note = ArtifactStatus.SIZE_MISMATCH, f"size {d.size} != pinned {spec.bytes}"
        elif d.sha256 != spec.sha256:
            st, note = ArtifactStatus.CHECKSUM_MISMATCH, f"SHA-256 {d.sha256} != pinned {spec.sha256}"
        else:
            st, note = ArtifactStatus.VERIFIED, ""
        parsed = None
        if st is ArtifactStatus.VERIFIED:
            try:
                parsed = parse_weather_xml(path.read_bytes())
                plan = plans.get(spec.file)
                reason = check_chunk_completeness(parsed, plan, expected_params) if plan else "file is not part of the request plan"
                if reason is None and spec.content_sha256 and parsed.content_sha256 != spec.content_sha256:
                    reason = "parsed content differs from the pinned content signature"
                if reason:
                    st, note = ArtifactStatus.INCOMPLETE, reason
                else:
                    all_triples += list(parsed.triples)
            except WeatherParseError as exc:
                st, note = ArtifactStatus.MALFORMED, str(exc)
        if st is not ArtifactStatus.VERIFIED:
            messages.append(Message(Level.ERROR, "X01", f"{spec.file}: {st.value}: {note}. Pins are not updated; a refreshed source needs an explicit retrieval and a new snapshot"))
        pending.append((spec, st, note, d, parsed))

    # snapshot identity from the bytes that are actually there
    observed = [(s.file, d.sha256, d.size) for s, _, _, d, _ in pending if d is not None]
    if observed:
        sha = snapshot_sha256(("weather_chunk", n, h, z) for n, h, z in observed)
        sid = snapshot_id("fmi", sha)
    else:
        sha, sid = None, None

    artifacts: list[Artifact] = []
    chunks: list[WeatherChunk] = []
    for spec, st, note, d, parsed in pending:
        aid = f"{sid or 'UNSNAPSHOTTED'}/{spec.file}"
        plan = plans.get(spec.file)
        url = plan.url(w.endpoint) if plan else w.endpoint
        artifacts.append(Artifact(aid, sid, SOURCE, Lane.CONTEXT, "weather_chunk", spec.file, _rel(w, spec.file), None, url, retrieved, version, True,
                                  d.size if d else None, d.md5 if d else None, d.sha256 if d else None, spec.bytes, spec.sha256, None, None, st, note))
        chunks.append(WeatherChunk(aid, spec.file, len(parsed.triples) if parsed else None, parsed.number_returned if parsed else None,
                                   parsed.hours if parsed else None, parsed.parameters if parsed else (), parsed.nulls if parsed else None,
                                   parsed.content_sha256 if parsed else None, spec.content_sha256, st, note))

    # union completeness across chunks
    ok_chunks = all(a.status is ArtifactStatus.VERIFIED for a in artifacts) and len(artifacts) == len(w.raw_files)
    if ok_chunks:
        hours = {t for t, p, _ in all_triples if p == expected_params[0]}
        pairs = [(t, p) for t, p, _ in all_triples]
        first, last = min(hours), max(hours)
        problems = []
        if len(hours) != w.expected_hours:
            problems.append(f"{len(hours)} distinct hours, expected {w.expected_hours}")
        if len(pairs) != len(set(pairs)):
            problems.append("duplicate (time, parameter) across chunks")
        if first != w.window_start or last != w.window_end:
            problems.append(f"covers {first}..{last}, expected {w.window_start}..{w.window_end}")
        if problems:
            ok_chunks = False
            messages.append(Message(Level.ERROR, "X01", "weather window incomplete: " + "; ".join(problems)))
        nulls = sum(1 for _, _, v in all_triples if v.strip().lower() == "nan")
        if nulls:
            messages.append(Message(Level.INFO, "X03", f"{nulls} NaN weather value(s) preserved as NULL (never zero)"))

    # preserved evidence (not part of snapshot identity)
    evidence_bad = False
    for spec in w.evidence_files:
        path = repo_root / w.local_dir / spec.file
        aid = f"{sid or 'UNSNAPSHOTTED'}/{spec.file}"
        if not path.is_file():
            st, note, d = ArtifactStatus.MISSING, "evidence file missing", None
        else:
            d = digest_file(path)
            if d.size != spec.bytes:
                st, note = ArtifactStatus.SIZE_MISMATCH, f"size {d.size} != pinned {spec.bytes}"
            elif d.sha256 != spec.sha256:
                st, note = ArtifactStatus.CHECKSUM_MISMATCH, f"SHA-256 mismatch"
            else:
                st, note = ArtifactStatus.VERIFIED, ""
        if st is not ArtifactStatus.VERIFIED:
            evidence_bad = True
            messages.append(Message(Level.ERROR, "S01", f"evidence file {spec.file}: {st.value}: {note}"))
        artifacts.append(Artifact(aid, sid, SOURCE, Lane.CONTEXT, "evidence", spec.file, _rel(w, spec.file), None, w.endpoint, retrieved, version, False,
                                  d.size if d else None, d.md5 if d else None, d.sha256 if d else None, spec.bytes, spec.sha256, None, None, st, note))

    status = "VERIFIED" if ok_chunks else ("MISSING" if not observed else "FAILED")
    snap = Snapshot(sid, SOURCE, Lane.CONTEXT, w.endpoint, version, w.license, retrieved, w.retrieval_method, len(observed), sha, status)
    outcome = LaneOutcome.OK if ok_chunks and not evidence_bad else (LaneOutcome.BLOCKED if not ok_chunks else LaneOutcome.WARNING)
    return WeatherOutcome(snap, artifacts, chunks, messages, outcome)
