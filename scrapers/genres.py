"""Explicit genre and exclusion rules for the training set (applied to Internet Archive subject tags and titles).

Genre labels come ONLY from these rules (no guessing from titles). A book can match several genres; it is then
assigned ONE primary genre by fixed precedence science_fiction > fantasy > mystery_thriller, and all matches are
kept as separate yes/no flags. Criticism, teaching guides, bibliographies, reference works and magazine issues are
excluded where identifiable from tags/titles. The rules are heuristics (tags are free text); every exclusion is
recorded with its reason so it can be audited.
"""
import re

GENRE_ORDER = ["science_fiction", "fantasy", "mystery_thriller"]

# A subject tag matches a genre if it CONTAINS one of these phrases (case-insensitive) ...
GENRE_PHRASES = {
    "science_fiction": ["science fiction"],
    "fantasy": ["fantasy"],
    "mystery_thriller": ["detective and mystery", "mystery and detective", "mystery fiction", "detective fiction",
                         "detective stories", "thriller", "suspense fiction", "suspense stories", "spy stories",
                         "spy fiction", "espionage fiction", "crime fiction"],
}
# ... or EQUALS one of these whole tags
GENRE_EXACT = {"mystery_thriller": {"mystery", "mysteries", "suspense"}}

# --- exclusions -------------------------------------------------------------------------------
# STRONG: a tag containing one of these marks non-fiction/reference/teaching material (any tag)
EXCLUDE_STRONG = ["study and teaching", "bibliograph", "handbook", "dictionar", "encyclop", "catalog", "reading list",
                  "history and criticism", "indexes", "stories, plots", "therapeutic use", "biography", "authors,"]
# WEAK: only counts when the tag itself is about fiction/literature/the genre (so "photo techniques" or
# "guides (spiritualism)" on a novel do not exclude it)
EXCLUDE_WEAK = ["criticism", "interpretation", "teaching", "guide", "authorship", "technique", "periodicals",
                "history and", "psycholog"]
_GENRE_RELATED = ("fiction", "literature", "stories", "fantasy", "mystery", "detective", "thriller", "science",
                  "suspense", "spy", "crime", "novel")
# fiction-form tags such as "Biography -- Fiction" are not treated as non-fiction
_FICTION_FORM = re.compile(r"(-- fiction|fiction)$|-- juvenile fiction|, fiction$", re.I)
EXCLUDE_TITLE = re.compile(
    r"\b(bibliograph\w*|criticism|critical (?:essays?|study|studies|companion|survey|introduction)|teaching|"
    r"teachers?'?s?|study guide|guide to|reader'?s guide|handbook|companion to|dictionary|index to|"
    r"catalog(?:ue)? of|essays? (?:on|in|about)|history of (?:the )?(?:science fiction|fantasy|detective|mystery|"
    r"crime)|coloring book|colouring book|activity book|magazine|encyclopedia of|encyclopaedia of|an encyclopedia)\b", re.I)
EXCLUDE_TITLE_ISSUE = re.compile(r"\b(?:v\.|vol\.?|volume)\s*\d+\s*(?:,|\s)\s*(?:no\.?|issue)\s*\d+", re.I)


def tags(subjects):
    return [str(s).strip().lower() for s in subjects if str(s).strip()]


def _genre_match(tag, genre):
    return any(p in tag for p in GENRE_PHRASES[genre]) or tag in GENRE_EXACT.get(genre, ())


def genre_flags(subjects):
    """{'science_fiction': bool, 'fantasy': bool, 'mystery_thriller': bool} from subject tags."""
    flags = {g: False for g in GENRE_ORDER}
    for tag in tags(subjects):
        for genre in GENRE_ORDER:
            if _genre_match(tag, genre):
                flags[genre] = True
    return flags


def primary_genre(flags):
    for genre in GENRE_ORDER:
        if flags.get(genre):
            return genre
    return None


def nonfiction_reason(title, subjects):
    """Reason string when the book looks like criticism/teaching/bibliography/reference/magazine issue, else None."""
    for tag in tags(subjects):
        if _FICTION_FORM.search(tag):
            continue
        for phrase in EXCLUDE_STRONG:
            if phrase in tag:
                return f"subject tag '{tag[:60]}' contains '{phrase}'"
        if any(g in tag for g in _GENRE_RELATED) or any(_genre_match(tag, g) for g in GENRE_ORDER):
            for phrase in EXCLUDE_WEAK:
                if phrase in tag:
                    return f"subject tag '{tag[:60]}' contains '{phrase}'"
    m = EXCLUDE_TITLE.search(str(title))
    if m:
        return f"title contains '{m.group(0)}'"
    if EXCLUDE_TITLE_ISSUE.search(str(title)):
        return "title looks like a periodical issue"
    return None
