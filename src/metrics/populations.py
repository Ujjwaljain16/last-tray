"""Named session populations. A metric never picks a population implicitly: it names one of these, and `select` refuses unknown names.

A  all_observed_sessions               every session key in fact_dining_session, whatever its status
B  non_quarantined_modelled_sessions   not quarantined and at least one modellable event (the sessions the model built business fields for)
C  eligible_registered_export_sessions every registered-export session key, counted BEFORE any quarantine or removal (M5's fixed denominator)
D  core_ready_registered_export_sessions  C that meet the approved core readiness criteria (the approved measurement population)
E  non_registered_export_sessions      the other export; diagnostic only, never pooled with C or D

Populations are labels inherited from source file names. They are not interpreted as customer-registration status.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from src.metrics.inputs import SessionRow
from src.vocab import Population

REGISTERED = Population.REGISTERED_EXPORT.value


@dataclass(frozen=True)
class PopulationSpec:
    name: str
    letter: str
    definition: str
    member: Callable[[SessionRow], bool]


POPULATIONS: dict[str, PopulationSpec] = {p.name: p for p in (
    PopulationSpec("all_observed_sessions", "A", "every (session_id, population) key in fact_dining_session, whatever its status", lambda s: True),
    PopulationSpec("non_quarantined_modelled_sessions", "B", "session keys that are not quarantined and have at least one modellable event",
                   lambda s: not s.is_quarantined and s.modellable_event_count > 0),
    PopulationSpec("eligible_registered_export_sessions", "C", "every registered-export session key, counted before any quarantine or removal",
                   lambda s: s.population == REGISTERED),
    PopulationSpec("core_ready_registered_export_sessions", "D", "registered-export session keys with core_ready = true: not quarantined, at least one modellable event, "
                   "no ERROR finding, valid weights, parsed times", lambda s: s.population == REGISTERED and s.core_ready),
    PopulationSpec("non_registered_export_sessions", "E", "every non-registered-export session key (diagnostic population, never pooled)", lambda s: s.population != REGISTERED),
)}


class PopulationError(KeyError):
    pass


def select(sessions: Iterable[SessionRow], population: str) -> list[SessionRow]:
    if population not in POPULATIONS:
        raise PopulationError(f"unknown population {population!r}: a metric must name one of {sorted(POPULATIONS)}")
    member = POPULATIONS[population].member
    return [s for s in sessions if member(s)]
