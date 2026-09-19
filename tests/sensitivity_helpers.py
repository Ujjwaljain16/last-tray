"""Builders for sensitivity engine tests: sessions written by hand so each operation can be tested at its exact boundary."""
from __future__ import annotations

import itertools
from datetime import datetime

from src.sensitivity.data import Agg, WorkingSet

REG, NON = "registered_export", "non_registered_export"
OVERRIDE_FILE = "registered_2020_10_05-2020_10_18.csv"
_n = itertools.count(1)


def agg(weight=500, comps=5, population=REG, quarantined=False, core_ready=None, session_warn=False, event_warn=False, day="2020-10-12", n_modellable=3, span_s=60,
        events=None, key=None, w_nonrepeat=None, w_incl_repeats=None, raw_comps=None, scales=None) -> Agg:
    i = next(_n)
    k = key or f"s{i}|{population}"
    ready = (population == REG and not quarantined) if core_ready is None else core_ready
    return Agg(k, k.split("|")[0], population, day, quarantined, ready, None if quarantined else weight, w_nonrepeat if w_nonrepeat is not None else weight,
               w_incl_repeats if w_incl_repeats is not None else weight, frozenset(f"c{j}" for j in range(comps)), frozenset(f"r{j}" for j in range(raw_comps if raw_comps is not None else comps)),
               frozenset(f"scale{j}" for j in range(scales if scales is not None else comps)), n_modellable, span_s, session_warn, event_warn,
               events if events is not None else [(datetime(2020, 10, 12, 11, 0, 0), "other.csv", "MODELLABLE")])


def working_set(aggs: list[Agg], irregular=(), low=(), largest=("f#1", "big|registered_export", 2097)) -> WorkingSet:
    d = {a.key: a for a in aggs}
    baseline = [a for a in aggs if a.population == REG and a.core_ready]
    return WorkingSet(d, baseline, sum(1 for a in aggs if a.population == REG), frozenset(irregular), frozenset(low), largest, {}, False)
