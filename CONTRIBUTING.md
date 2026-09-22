# Contributing

Thanks for looking. This repository is two different things, and they take
contributions differently.

## The code — pull requests welcome

Everything under `tools/`, `layouts/`, `static/`, `schema/` and `.github/` is MIT
licensed and open to improvement: the cleaning pipeline, the route builder, the
Hugo templates, the checks. Open an issue first for anything larger than a fix, so
the approach is agreed before the work. Every pull request builds the whole site
(`tools/build.sh`) and must be green to merge; `main` is protected and squash-merged.

## The content — not accepted from anyone but the author

Everything under `archive/`, `curation/` and `content/` is the site's actual claim:
that every line on the map is a GPS track one person walked and recorded, and every
condition note was written by that person on the day given. Read the
[about page](https://mazatzalhiking.com/about/) for why that matters.

So a pull request that adds or edits a trail condition, a track, a junction, or a
trip report **will be closed without merging**, however accurate it is. It is not a
judgment on the contribution; it is that the site cannot publish it under its own
name. If you know a condition has changed, please
[open an issue](https://github.com/jacobemerick/mazatzalhiking/issues) and say
where and when — that is genuinely useful, and the author can go and look.

Corrections to *derived* data (a leg's figures, a heading, a slug) are a code
matter and welcome as PRs.

## Licenses

- Code: MIT, see `LICENSE`.
- Recorded tracks, curated graph, trail notes and trip reports: CC BY-NC-ND 4.0,
  see `LICENSE-CONTENT`. Share with credit, no commercial use, no derivatives.
