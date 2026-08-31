"""Abhijit, Choghadiya, and a muhurta assessment that is arithmetic rather than
the model's judgement.

There was no muhurta engine at all. `QueryDomain.MUHURTA` cast a chart and
computed Rahu Kaal, and the model decided whether tomorrow was good — an
unauditable judgement standing where a table belongs.
"""

from datetime import date

import pytest

from rishivan.chart.limbs import Karana, Nakshatra, Tithi, Yoga
from rishivan.chart.muhurta import (
    CHOGHADIYA_QUALITY, GOOD, abhijit_muhurta, assess_day, choghadiya,
)
from rishivan.chart.panchang import compute_panchang

DELHI = dict(lat=28.6139, lon=77.2090, tz_offset=5.5, place="New Delhi")


def _limbs(tithi_no=5, karana="Bava", yoga="Siddhi"):
    from rishivan.chart.limbs import Limbs

    return Limbs(
        tithi=Tithi(index=tithi_no - 1, name=f"Shukla {tithi_no}",
                    paksha="Shukla", number=tithi_no, rikta=tithi_no in (4, 9, 14)),
        nakshatra=Nakshatra(index=0, name="Ashwini", pada=1),
        yoga=Yoga(index=0, name=yoga, inauspicious=yoga in ("Vyatipata", "Vaidhriti")),
        karana=Karana(index=1, name=karana, inauspicious=karana == "Vishti"),
    )


class TestAbhijit:
    def test_it_straddles_local_noon(self):
        """The 8th of fifteen day-muhurtas, so it is centred on the midpoint of
        sunrise and sunset by construction."""
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        window = abhijit_muhurta(panchang)
        midday = (_minutes(panchang.sunrise) + _minutes(panchang.sunset)) / 2
        assert _minutes(window.start) < midday < _minutes(window.end)

    def test_it_is_a_fifteenth_of_the_day(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        window = abhijit_muhurta(panchang)
        expected = panchang.day_length_minutes / 15
        assert abs(window.duration_minutes - expected) <= 1

    def test_it_is_withheld_on_wednesday(self):
        """The convention this implements holds Abhijit void on Wednesday.
        Stated rather than silently applied — traditions differ, and a muhurta
        that does not name its convention is one nobody can check."""
        wednesday = compute_panchang(date(2026, 9, 2), **DELHI)
        assert wednesday.weekday == "Wednesday"
        assert abhijit_muhurta(wednesday) is None


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


class TestChoghadiya:
    def test_eight_by_day_and_eight_by_night(self):
        slots = choghadiya(compute_panchang(date(2026, 8, 30), **DELHI))
        assert len([s for s in slots if s.period == "day"]) == 8
        assert len([s for s in slots if s.period == "night"]) == 8

    def test_the_day_slots_span_sunrise_to_sunset(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        day = [s for s in choghadiya(panchang) if s.period == "day"]
        assert day[0].start == panchang.sunrise
        assert day[-1].end == panchang.sunset

    def test_the_slots_are_contiguous(self):
        slots = [s for s in choghadiya(compute_panchang(date(2026, 8, 30), **DELHI))
                 if s.period == "day"]
        for earlier, later in zip(slots, slots[1:]):
            assert earlier.end == later.start

    def test_the_day_begins_with_the_lord_of_the_day(self):
        """Sunday opens on Udveg because the Sun rules it; Monday on Amrit for
        the Moon. The sequence then follows Chaldean order, the same cycle the
        hora uses."""
        for day, first in (
            (date(2026, 8, 30), "Udveg"),    # Sunday, Sun
            (date(2026, 8, 31), "Amrit"),    # Monday, Moon
            (date(2026, 9, 1), "Rog"),       # Tuesday, Mars
            (date(2026, 9, 2), "Labh"),      # Wednesday, Mercury
            (date(2026, 9, 3), "Shubh"),     # Thursday, Jupiter
            (date(2026, 9, 4), "Chal"),      # Friday, Venus
            (date(2026, 9, 5), "Kaal"),      # Saturday, Saturn
        ):
            slots = [s for s in choghadiya(compute_panchang(day, **DELHI))
                     if s.period == "day"]
            assert slots[0].name == first, day

    def test_the_night_begins_with_the_lord_of_the_fifth_weekday(self):
        """Sunday night opens on Shubh — Jupiter, who rules Thursday, the 5th
        day counted from Sunday. The night does NOT continue the day's cycle."""
        for day, first in (
            (date(2026, 8, 30), "Shubh"),    # Sunday   -> Thursday, Jupiter
            (date(2026, 8, 31), "Chal"),     # Monday   -> Friday, Venus
            (date(2026, 9, 1), "Kaal"),      # Tuesday  -> Saturday, Saturn
            (date(2026, 9, 2), "Udveg"),     # Wednesday-> Sunday, Sun
        ):
            slots = [s for s in choghadiya(compute_panchang(day, **DELHI))
                     if s.period == "night"]
            assert slots[0].name == first, day

    def test_every_slot_carries_a_verdict(self):
        for slot in choghadiya(compute_panchang(date(2026, 8, 30), **DELHI)):
            assert slot.name in CHOGHADIYA_QUALITY
            assert slot.quality in ("good", "neutral", "bad")


class TestAssessment:
    def test_it_flags_a_rikta_tithi(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        report = assess_day(panchang, _limbs(tithi_no=4))
        assert any("rikta" in note.lower() for note in report.day_notes)

    def test_it_flags_vishti_karana(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        report = assess_day(panchang, _limbs(karana="Vishti"))
        assert any("Vishti" in note for note in report.day_notes)

    def test_it_flags_an_inauspicious_yoga(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        report = assess_day(panchang, _limbs(yoga="Vyatipata"))
        assert any("Vyatipata" in note for note in report.day_notes)

    def test_a_clean_day_reports_nothing_rather_than_reassurance(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        assert assess_day(panchang, _limbs()).day_notes == ()

    def test_a_slot_inside_rahu_kaal_is_marked_whatever_its_choghadiya(self):
        """The collision that matters. A Labh slot overlapping Rahu Kaal is not
        a good hour, and the two tables know nothing about each other."""
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        report = assess_day(panchang, _limbs())
        collided = [s for s in report.windows if s.collisions]
        assert collided
        for slot in collided:
            assert not slot.recommended

    def test_the_best_windows_are_good_and_uncollided(self):
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        report = assess_day(panchang, _limbs())
        for slot in report.best():
            assert slot.name in GOOD
            assert not slot.collisions
            assert slot.recommended

    def test_it_ranks_rather_than_returning_a_verdict(self):
        """A muhurta engine that answers yes or no has thrown away the reason.
        The reading needs the windows AND why each was rejected."""
        panchang = compute_panchang(date(2026, 8, 30), **DELHI)
        report = assess_day(panchang, _limbs())
        assert len(report.windows) >= 16
        assert all(hasattr(s, "reasons") for s in report.windows)
