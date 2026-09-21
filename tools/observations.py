"""Read condition observations out of the trail markdown (#18).

The authored form of an observation is a section of `content/trails/<slug>.md`:

    ## Barnhardt Trailhead to Sandy Saddle {#00}

    ### 2026-06-30 water {source="haz/triplog/2026-06-30.md"}
    I even heard some water trickling down Barnhardt Canyon on the hike up.

    ### 2026-05-15 brush
    The trail maintenance along Barnhardt was appreciated.
    The manzanita above the falls has been pushed back nicely.

    ![Big Kahuna, dry](2026-05-15-big-kahuna.jpg)

    ## Club Spring {#node:0T}

    ### 2017-11-18 water
    Drank 2 liters here, pulled another 2.

Rules, which are all a person needs to know to write one:

- A `##` heading with an id attribute opens a target. `{#00}` is segment 00;
  `{#node:0T}` is node 0T; `{#feature:f2}` a feature. The heading text is for people
  and is checked against the graph by tools/sync_trails.py, never trusted.
- A `###` heading is an observation: the date, one space, the category, and an optional
  `{source="…"}` attribute naming the archive path the note came from.
- The lines that follow are the text. A blank line separates paragraphs; single line
  breaks inside a paragraph are joined with a space, so one sentence per line is the
  house style and costs nothing in the output.
- A line that is only a markdown image is a photo: `![caption](file.jpg)`.
- Anything above the first `##` is the trail's introduction and is not an observation.

Output is exactly the shape schema/observations.schema.json describes, so the builder,
the validator and the Hugo templates all consume the same document.
"""
import os, re

TARGET = re.compile(r'^##\s+(?P<name>.*?)\s*\{#(?P<id>[A-Za-z]+:)?(?P<code>[0-9A-Za-z]{2,4})\}\s*$')
OBS = re.compile(r'^###\s+(?P<date>\d{4}-\d\d-\d\d)\s+(?P<cat>[a-z-]+)\s*(?:\{(?P<attrs>[^}]*)\})?\s*$')
ATTR = re.compile(r'(\w+)="([^"]*)"')
PHOTO = re.compile(r'^!\[(?P<caption>[^\]]*)\]\((?P<file>[^)\s]+)\)\s*$')
HEADING = re.compile(r'^#{1,6}\s')


class ParseError(Exception):
    pass


def parse(text, where='<string>'):
    """Returns (intro_markdown, observations). Raises ParseError on a heading it
    cannot read, because a heading that parses as nothing silently loses a note."""
    intro, obs = [], []
    target = None
    cur = None          # the observation being accumulated
    paras, para, photos = [], [], []

    def close():
        nonlocal cur, paras, para, photos
        if cur is None:
            return
        if para:
            paras.append(' '.join(para)); para = []
        if not paras:
            raise ParseError(f"{where}: observation {cur['date']} {cur['category']} under "
                             f"{cur['target']} has no text")
        cur['text'] = '\n\n'.join(paras)
        if photos:
            cur['photos'] = photos
        obs.append(cur)
        cur, paras, para, photos = None, [], [], []

    for n, raw in enumerate(text.split('\n'), 1):
        line = raw.rstrip()
        m = TARGET.match(line)
        if m:
            close()
            kind = (m.group('id') or 'segment:').rstrip(':')
            if kind not in ('segment', 'node', 'feature'):
                raise ParseError(f"{where}:{n}: unknown target kind {kind!r}")
            target = f"{kind}:{m.group('code')}"
            continue
        m = OBS.match(line)
        if m:
            close()
            if target is None:
                raise ParseError(f"{where}:{n}: observation before any '## … {{#id}}' heading")
            cur = dict(target=target, date=m.group('date'), category=m.group('cat'))
            for k, v in ATTR.findall(m.group('attrs') or ''):
                if k == 'source':
                    cur['source'] = v
                else:
                    raise ParseError(f"{where}:{n}: unknown attribute {k!r}")
            continue
        if HEADING.match(line) and target is not None:
            raise ParseError(f"{where}:{n}: heading {line!r} is not a target ('## name {{#id}}') "
                             f"or an observation ('### YYYY-MM-DD category')")
        if target is None:
            intro.append(raw)
            continue
        if cur is None:
            if line.strip():
                raise ParseError(f"{where}:{n}: text under a leg heading but outside any "
                                 f"observation: {line[:60]!r}")
            continue
        m = PHOTO.match(line)
        if m:
            if para:
                paras.append(' '.join(para)); para = []
            p = {'file': m.group('file')}
            if m.group('caption').strip():
                p['caption'] = m.group('caption').strip()
            photos.append(p)
        elif not line.strip():
            if para:
                paras.append(' '.join(para)); para = []
        else:
            para.append(line.strip())
    close()
    return '\n'.join(intro).strip('\n'), obs


def load_dir(directory):
    """Every trail file -> {slug: (intro, observations)}."""
    out = {}
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith('.md') or fn.startswith('_'):
            continue
        path = os.path.join(directory, fn)
        body = open(path).read()
        # strip front matter
        if body.startswith('---\n'):
            end = body.find('\n---\n', 4)
            body = body[end + 5:] if end != -1 else body
        out[fn[:-3]] = parse(body, path)
    return out


def sentences(text):
    """One sentence per line, for writing. Conservative: splits only after . ! ? that is
    followed by whitespace and a capital, quote or bracket."""
    return re.sub(r'(?<=[.!?])\s+(?=[A-Z"(\'])', '\n', text)
