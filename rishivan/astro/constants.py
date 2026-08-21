"""Static Jyotish reference data. No computation, no configuration."""

from __future__ import annotations

from dataclasses import dataclass

RASHIS = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)
RASHI_SANSKRIT = (
    "Mesha",
    "Vrishabha",
    "Mithuna",
    "Karka",
    "Simha",
    "Kanya",
    "Tula",
    "Vrishchika",
    "Dhanu",
    "Makara",
    "Kumbha",
    "Meena",
)
RASHI_LORDS = (
    "mars",
    "venus",
    "mercury",
    "moon",
    "sun",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "saturn",
    "jupiter",
)

PLANET_ORDER = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
    "rahu",
    "ketu",
)
PLANET_LABELS = {
    "sun": "Sun",
    "moon": "Moon",
    "mars": "Mars",
    "mercury": "Mercury",
    "jupiter": "Jupiter",
    "venus": "Venus",
    "saturn": "Saturn",
    "rahu": "Rahu",
    "ketu": "Ketu",
}
PLANET_CODES = {
    "sun": "Su",
    "moon": "Mo",
    "mars": "Ma",
    "mercury": "Me",
    "jupiter": "Ju",
    "venus": "Ve",
    "saturn": "Sa",
    "rahu": "Ra",
    "ketu": "Ke",
}

VIMSHOTTARI_CYCLE = (
    "ketu",
    "venus",
    "sun",
    "moon",
    "mars",
    "rahu",
    "jupiter",
    "saturn",
    "mercury",
)

NAKSHATRA_ARC = 360.0 / 27.0
PADA_ARC = NAKSHATRA_ARC / 4.0


@dataclass(frozen=True, slots=True)
class NakshatraInfo:
    """One row of the 27-nakshatra reference table."""

    name: str
    lord: str
    deity: str
    gana: str
    yoni: str
    nadi: str
    varna: str
    symbol: str
    element: str


# Columns: name, lord, deity, gana, yoni, nadi, varna, symbol, element.
# The lord column is VIMSHOTTARI_CYCLE repeating every nine rows — pinned by a test.
# fmt: off
_NAKSHATRA_ROWS = (
    ("Ashwini", "ketu", "Ashwini Kumaras", "Deva", "Horse", "Vata",
     "Vaishya", "Horse's head", "Earth"),
    ("Bharani", "venus", "Yama", "Manushya", "Elephant", "Pitta",
     "Mleccha", "Yoni", "Earth"),
    ("Krittika", "sun", "Agni", "Rakshasa", "Sheep", "Kapha",
     "Brahmin", "Razor", "Earth"),
    ("Rohini", "moon", "Brahma", "Manushya", "Serpent", "Kapha",
     "Shudra", "Ox cart", "Earth"),
    ("Mrigashira", "mars", "Soma", "Deva", "Serpent", "Pitta",
     "Shudra", "Deer's head", "Earth"),
    ("Ardra", "rahu", "Rudra", "Manushya", "Dog", "Vata",
     "Shudra", "Teardrop", "Water"),
    ("Punarvasu", "jupiter", "Aditi", "Deva", "Cat", "Vata",
     "Vaishya", "Quiver of arrows", "Water"),
    ("Pushya", "saturn", "Brihaspati", "Deva", "Sheep", "Pitta",
     "Kshatriya", "Cow's udder", "Water"),
    ("Ashlesha", "mercury", "Nagas", "Rakshasa", "Cat", "Kapha",
     "Mleccha", "Coiled serpent", "Water"),
    ("Magha", "ketu", "Pitris", "Rakshasa", "Rat", "Kapha",
     "Shudra", "Throne", "Water"),
    ("Purva Phalguni", "venus", "Bhaga", "Manushya", "Rat", "Pitta",
     "Brahmin", "Hammock", "Water"),
    ("Uttara Phalguni", "sun", "Aryaman", "Manushya", "Cow", "Vata",
     "Kshatriya", "Bed", "Fire"),
    ("Hasta", "moon", "Savitar", "Deva", "Buffalo", "Vata",
     "Vaishya", "Hand", "Fire"),
    ("Chitra", "mars", "Vishvakarma", "Rakshasa", "Tiger", "Pitta",
     "Mleccha", "Bright jewel", "Fire"),
    ("Swati", "rahu", "Vayu", "Deva", "Buffalo", "Kapha",
     "Shudra", "Coral", "Fire"),
    ("Vishakha", "jupiter", "Indra-Agni", "Rakshasa", "Tiger", "Kapha",
     "Mleccha", "Triumphal arch", "Fire"),
    ("Anuradha", "saturn", "Mitra", "Deva", "Hare", "Pitta",
     "Shudra", "Lotus", "Fire"),
    ("Jyeshtha", "mercury", "Indra", "Rakshasa", "Hare", "Vata",
     "Shudra", "Earring", "Air"),
    ("Mula", "ketu", "Nirriti", "Rakshasa", "Dog", "Vata",
     "Kshatriya", "Tied roots", "Air"),
    ("Purva Ashadha", "venus", "Apas", "Manushya", "Monkey", "Pitta",
     "Brahmin", "Fan", "Air"),
    ("Uttara Ashadha", "sun", "Vishvedevas", "Manushya", "Mongoose", "Kapha",
     "Kshatriya", "Elephant tusk", "Air"),
    ("Shravana", "moon", "Vishnu", "Deva", "Monkey", "Kapha",
     "Mleccha", "Three footprints", "Air"),
    ("Dhanishta", "mars", "Vasus", "Rakshasa", "Lion", "Pitta",
     "Shudra", "Drum", "Air"),
    ("Shatabhisha", "rahu", "Varuna", "Rakshasa", "Horse", "Vata",
     "Butcher", "Empty circle", "Ether"),
    ("Purva Bhadrapada", "jupiter", "Aja Ekapada", "Manushya", "Lion", "Vata",
     "Brahmin", "Sword", "Ether"),
    ("Uttara Bhadrapada", "saturn", "Ahir Budhnya", "Manushya", "Cow", "Pitta",
     "Kshatriya", "Twin bier", "Ether"),
    ("Revati", "mercury", "Pushan", "Deva", "Elephant", "Kapha",
     "Shudra", "Fish", "Ether"),
)
# fmt: on

NAKSHATRAS = tuple(NakshatraInfo(*row) for row in _NAKSHATRA_ROWS)
