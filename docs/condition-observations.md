# Condition observations

Closes [#17](https://github.com/jacobemerick/mazatzalhiking/issues/17). Populated by
[#18](https://github.com/jacobemerick/mazatzalhiking/issues/18); rendered by
[#19](https://github.com/jacobemerick/mazatzalhiking/issues/19).

- Contract: [`schema/observations.schema.json`](../schema/observations.schema.json)
- Example instance: [`schema/example/observations.json`](../schema/example/observations.json)
  (placeholder text, deliberately)
- Real instance: [`curation/observations.json`](../curation/observations.json), empty
  until #18
- Validator: `./tools/validate_graph.py curation/graph.json` picks up the sibling
  `observations.json` automatically

**Decision: an observation is one dated, categorised, first-person note about one
segment, junction, or feature, with photos hanging off it. It is hand-authored into a
file the pipeline never touches, and it is the only way any condition text or photo
reaches the site.**

```json
{
  "target": "segment:0C",
  "date": "2026-05-23",
  "category": "brush",
  "text": "…",
  "source": "RS_SandySaddleTM12_231525.gpx",
  "photos": [{ "file": "…jpg", "caption": "…" }]
}
```

Four consumers read this record and nothing else: the builder popup, the GPX/KML
export descriptions ([#21](https://github.com/jacobemerick/mazatzalhiking/issues/21)),
the shared display component (#19), and the generated trail pages
([#31](https://github.com/jacobemerick/mazatzalhiking/issues/31)). One record, so they
cannot drift.

---

## Decisions

### 1. A target names its kind, because the id spaces overlap

**Decision: `target` is `<kind>:<id>`, kind being `segment`, `node`, or `feature`.**

The graph schema gave each entity type its own id space, and the sketch of observations
in that document used a bare id as the target. That sketch was wrong in practice, not
just in theory: in the committed graph **82 of 84 node ids are also segment ids**, and
49 of 49 trail ids are. A note targeting `4H` names a junction and a leg at once, and
the old validator masked this by accepting an id found in *any* space.

The prefix costs eight characters per record and removes the ambiguity entirely. The
validator now resolves the id in the named space only, and points at `superseded_by`
when the id is a retired segment, since a split is the one graph change that
invalidates an observation and the tombstone says where the note should move.

**Trails are not a target.** A trail-wide note ("the whole Barnhardt Trail was cleared
in spring 2024") is real, but the surfaces that show conditions are all leg-shaped: the
popup is on a leg, the export lists legs, the trail page is sectioned by leg. A trail
note would either be repeated under every leg or shown nowhere, so it is written against
the legs it applies to. The per-trail introduction paragraph in #31 is prose, not an
observation, and is not this file's concern.

### 2. The date is a full day, always

**Decision: `date` is `YYYY-MM-DD`. No month-only dates, no "spring 2021".**

Every observation comes from a walk, and every walk in this project has a date:
[`tools/trips.csv`](../tools/trips.csv) carries one per recorded trip, and the
HikeArizona trip reports #18 will draw on are dated too. So the strictness costs nothing
for real observations, and what it prevents is worth having: a note whose date was
guessed is a note whose age is a guess, and the age is the whole point. A 2016 note on a
burn-scar leg and a note from last spring mean different things, which is why the date
travels with the text on every surface and is never hidden behind "recently".

The validator rejects a future date, which is the only mistake a full date can still make.

### 3. One category per observation

**Decision: `category` is required and single-valued, from a closed list.**

The list, and what each means:

| category | means |
|---|---|
| `brush` | overgrowth narrowing or hiding the tread |
| `deadfall` | downed timber across it, the post-fire problem that keeps changing |
| `tread` | the surface itself, washed out, sloughed, or rebuilt |
| `route-finding` | where the way is hard to follow, including missing signs and cairns |
| `water` | whether a source is running |
| `access` | how you reach the ground at all: roads, gates, crossings, closures |

`deadfall` is new since the graph document's sketch. Both fires that shaped this range
(Willow 2004, Sunflower 2012) predate the corpus, so every recorded track is post-fire,
and inside the scars the thing that changes between visits is deadfall and regrowth. They
are different problems for a hiker, so they are different categories. The "unsigned
junction" case from the graph document is `route-finding` on a node, and the Fig
Trailhead kayak crossing is `access` on a node.

Single-valued so that a surface can summarise a leg by its categories and pick an icon
without parsing text. A note that genuinely covers two things becomes two observations
with the same date, which is a small authoring cost and keeps the summaries honest.
There is no catch-all category on purpose: if #18 meets a note that fits nothing here,
the list grows by a reviewed edit to the schema, rather than `general` quietly absorbing
everything.

### 4. Text is plain, and only Jacob writes it

**Decision: `text` is plain text with blank-line paragraphs. No markup, no links.**

The same string is rendered into HTML on a page and in a popup, and into a GPX
`<desc>` that a GPS unit shows as raw characters. Markdown would either need three
renderers or show up as asterisks on a device in the field. Paragraph breaks are the one
piece of structure every consumer can honour.

The rule from the ticket is unchanged and now mechanically enforced as far as it can be:
the validator refuses any text containing `PLACEHOLDER` outside `schema/example/`, so
the illustrative records can never be validated as real ones. It cannot check
authorship. Nothing can. That remains a rule about who edits the file.

### 5. Photos hang off observations, and nowhere else

**Decision: `photos` is an optional list on an observation; each entry is a filename
and an optional caption. There is no photo entity, no gallery, and no photo without a
dated note above it.**

[#20](https://github.com/jacobemerick/mazatzalhiking/issues/20) decided that photos
are context for conditions only. The natural consequence is that a photo's date and
place are the observation's date and place, so the photo carries neither. Attaching it
to the note rather than to the segment means it is shown with the words that explain
it, and it ages with them: a 2016 photo of brush is under a 2016 note, and a 2026 note
saying the brush is gone sits above both.

`file` is a **basename only**. Where the files live and how they are served is the page
generator's decision (#30) and may change; a reference that is just a name survives
that, while a path would not. The narrowed photo inventory
([#5](https://github.com/jacobemerick/mazatzalhiking/issues/5)) only has to place the
photos that get attached here, not the whole library.

The validator warns when one file is attached to two observations. Legitimate, perhaps,
but usually a copy-paste, and one photo shows one dated condition.

### 6. Provenance is recorded when it exists

**Decision: optional `source`, the archive filename of the trip the note comes from.**

Segments carry the tracks they were traced from because walked-it-myself provenance is
the point of the project. An observation drawn from a recorded trip can carry the same
link, and the date should match that trip's date in `trips.csv`. It is optional because a
note can predate the corpus or come from a walk that was not recorded, and a true note
without a file is better than a fabricated file. The validator does not cross-check it
against `archive/` today; #18 may want that once the field is in use.

### 7. Storage order is not display order

**Decision: the file is an append-in-any-order list. Every consumer sorts newest-first
per target, ties in file order.**

Enforcing sort order in the file would make authoring a chore and gain nothing, since
consumers have to group by target anyway. Newest-first is a display rule and lives in
the display component (#19). An observation is never edited into a different claim:
if conditions changed, that is a new observation with a new date, and the old one
stays. Corrections to wording are edits; corrections to fact are new records.

## What this does not decide

- **Where photos are stored and served.** #30. The schema only guarantees the
  reference is a bare name.
- **Partial-leg targets.** "Brushy for the upper mile" is expressed in the text. A
  fractional range on a segment (the `at` that features use) would be additive to this
  schema if #18 turns out to need it, and nothing here precludes it.
- **What counts as an observation worth writing.** #18. The schema accepts a one-line
  note and a three-paragraph one equally; an absent note is correct, and an invented one
  is not.
- **How a split segment's observations migrate.** The tombstone says where the ground
  went; moving the note onto the right half is a hand decision, and the validator
  reports it rather than guessing.
