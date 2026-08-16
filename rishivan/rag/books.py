"""Human-readable titles for the ingested corpus.

The ``document.title`` column currently mirrors the slug, and the vector
payload only carries ``book_slug`` — neither is presentable to a seeker. This
module is the single place that turns a slug into a citable title, so answers
can say "Phaladeepika, p. 176" instead of a bare, meaningless "Page 176".

Kept as a lookup rather than a query so citation rendering costs no round-trip
on the request path.
"""

from __future__ import annotations

BOOK_TITLES: dict[str, str] = {
    "bphs-gcsharma-vol1": "Brihat Parashara Hora Shastra, Vol. 1",
    "bphs-gcsharma-vol2": "Brihat Parashara Hora Shastra, Vol. 2",
    "phaladeepika-sastri-1950": "Phaladeepika",
    "saravali-santhanam-en": "Saravali",
    "jatakaparijata-sastri-vol1": "Jataka Parijata, Vol. 1",
    "jatakaparijata-sastri-vol2": "Jataka Parijata, Vol. 2",
    "brihatjataka-row-1919": "Brihat Jataka",
    "laghu-parashari": "Laghu Parashari",
    "sarvartha-chintamani": "Sarvartha Chintamani",
    "bhavartha-ratnakara-by-b-v-raman-text": "Bhavartha Ratnakara",
    "muhurtachintamani": "Muhurta Chintamani",
    "prasnamarga-raman-part1": "Prashna Marga, Part 1",
    "prasnamarga-raman-part2": "Prashna Marga, Part 2",
    "prashna-tantra": "Prashna Tantra",
    "devakeralam-chandrakalanadi-vol1": "Deva Keralam (Chandra Kala Nadi), Vol. 1",
    "hindupredictiveastrology-raman": "Hindu Predictive Astrology",
    "dharma-sindhu": "Dharma Sindhu",
    "vivaha-patalam": "Vivaha Patalam",
    "cheiros-book-of-numbers": "Cheiro's Book of Numbers",
    "the-complete-book-of-numerology": "The Complete Book of Numerology",
    "numerology-key-to-your-inner-self": "Numerology: Key to Your Inner Self",
}


def title_for_slug(slug: str | None) -> str:
    """Citable title for a book slug, prettifying anything unmapped."""
    if not slug:
        return "Classical text"
    key = slug.lower().strip()
    if key in BOOK_TITLES:
        return BOOK_TITLES[key]
    return key.replace("-", " ").replace("_", " ").title()
