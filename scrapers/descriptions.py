"""Cleaning and usability rules for archive.org item descriptions (used for the description-based training set).

Many descriptions start with catalogue text ("244 p. ; 22 cm", "A Berkley book.", "Includes index") and some are only that.
`clean_description` removes the leading catalogue part; `description_words` counts what is left. A description is
"usable" when 25 or more words remain, it is not boilerplate (for example "Book digitized by Google...") and it is not
the same text as a different work's description (checked over the whole dataset in build_description_dataset.py).
The descriptions are catalogue/publisher summaries of the book; who wrote them is not known.
"""
import html
import re

MIN_WORDS = 25

_PHYS = re.compile(
    r"^\s*(?:(?:[ivxlc]+,\s*)?[\d,]+\s*(?:p|pp|pages|leaves|unnumbered pages)\b\.?\s*"
    r"(?:[:;,]?\s*(?:ill\.?|illustrations?|maps?|col\.?|ports?\.?)\b\.?)*\s*[:;,]?\s*(?:[\d.]+\s*(?:cm|mm|in)\b\.?)?\s*"
    r"|1 online resource[^A-Za-z]{0,40}|[\d\s.,;:]*cm\.?\s*)+", re.I)
_NOTE = re.compile(
    r"^(?:\"[^\"]{0,60}\"(?:--[^.]{0,40})?\.?|(?:sequel|prequel|companion|originally published|includes|bibliography|"
    r"\"?summary:)[^.]*\.?|rl:[^.]*|\d{3}-\d{3}\.?|large print\.?|juvenile\.?)\s*", re.I)
_BOILER = re.compile(
    r"digiti[sz]ed by google|uploaded to the internet archive|description based on cip|resource not viewed|mode of access|"
    r"internet archive|no description|this item|from the collection of|public domain", re.I)


def raw_text(value):
    """Description field (string, list or None) -> plain text without HTML tags."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(map(str, value))
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def clean_description(value):
    text = _PHYS.sub("", raw_text(value)).strip()
    for _ in range(6):                      # peel leading catalogue notes such as "A Berkley book." or "RL: 2.2"
        m = _NOTE.match(text)
        if not m or not m.group(0).strip():
            break
        text = text[m.end():].strip()
    return text


def description_words(text):
    return len(text.split()) if text else 0


def is_boilerplate(text):
    return bool(_BOILER.search(text))


def normalised(text):
    return re.sub(r"\W+", " ", text.lower()).strip()
