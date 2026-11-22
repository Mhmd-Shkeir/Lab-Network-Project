# Children's-audience labels: rules (provisional labels)

**Target.** The *intended audience* of a book: is it written and published mainly for **children** (up to about age 12)? This is not a guarantee of age suitability, and it is not the catalogue's `juvenile` subject marker (which also covers teen books and is applied inconsistently).

**Who labelled.** Claude (an AI model) assigned every label in `data/labels/children_audience_labels.csv`, reading only the title, author, year, page count and the first part of the description. The labeller never saw the catalogue juvenile marker or any model prediction. The labels are **provisional**: they are not human-verified, and a manual review sample is provided in `report/ml/children/review/`. A reviewer's label overrides the provisional one.

## Label classes
| Code | Meaning | Typical examples |
|---|---|---|
| `C` children | Aimed mainly at readers up to about 12: picture books, early readers, chapter books, middle-grade novels and series, children's classics, kids' media tie-ins, kid-oriented manga, interactive/choose-your-path books, items stating "ages 8-12", Accelerated Reader low levels. | Hardy Boys, Boxcar Children, Warriors, Animorphs, Beast Quest, Goosebumps, Magic Tree House, Dr Dolittle, Pinocchio, Daisy Meadows fairies, Percy Jackson, Harry Potter |
| `Y` teen / young adult | Aimed at about 13-18: teen protagonists in YA positioning, YA dystopian/romance/paranormal, teen thrillers, YA manga, Nancy Drew Files, Vampire Academy. | Uglies, Scythe, Pretty Little Liars, Seraphina |
| `A` adult | Everything else: adult fiction (even with young characters in an adult-market book), comics and superhero collections, anthologies, criticism and reference, unabridged adult editions of classics. | Cryptonomicon, Flavia de Luce, Marvel/DC collections |
| `?` unsure | Not enough information to decide. Excluded from training and testing. | |

## Binary target used by the models
`children = 1` for `C`; `children = 0` for `Y` and `A`; `?` rows are excluded. Teen books are deliberately **negatives**.

## Rules for borderline cases
* A series' usual market decides (for example Warriors and Hardy Boys are `C`; Nancy Drew *Files* are `Y`).
* A teen or young protagonist alone does not make a book `C`; the publisher positioning does.
* Graphic novels / comics are `A` unless marketed to children.
* Large-print, omnibus, reference and criticism editions follow the work's usual audience; unabridged classics are `A` unless the edition is clearly for children.
* A description that states an age range or reading level counts as strong evidence.

## Procedure and data roles (see `data/labels/`)
1. A random sample is drawn from the **training pool** of the phase-2 juvenile split, and a separate random **fresh test sample** from that split's test side, both grouped by `ol_group`; sampling files are saved before labelling and before any model selection.
2. The 158 books of the earlier exploratory check (test side) are kept as exploratory data; they never enter the fresh test set and are used only as extra training labels.
3. Rules and the sampling files are frozen before the fresh test labels are written. The fresh test labels are used **once** for the final evaluation.
