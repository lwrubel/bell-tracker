# bell-tracker

Flask + SQLite app with a Flask-Admin panel.

## Local development

```sh
uv sync
uv run flask --app wsgi run --debug
```

Visit http://127.0.0.1:5000 for the app and http://127.0.0.1:5000/admin/ for the admin panel.

The SQLite file is created automatically at `instance/app.db` on first run.

There's no self-signup — bootstrap the first admin with:

```sh
uv run flask --app wsgi create-admin
```

## Tests

```sh
uv run pytest
```

Tests run against a throwaway on-disk SQLite database created fresh per
test (see `tests/conftest.py`) — they never touch `instance/app.db`.

## Assigning ringers to pieces and positions (admin)

Roster assignment is admin-driven: a ringer only sees a piece in their own
program view once an admin has explicitly assigned them a position on it.
This is done through the **Entry** section of the Flask-Admin panel
(`/admin/`), not by the ringer.

Prerequisites (usually set up once per concert):

1. The **Concert** exists with its **Pieces** (each with a `program_order`).
2. The ringer has a **User** account (admin-created via `/admin/` → Users).

To assign a ringer to a piece:

1. Go to `/admin/` → **Entry** → **Create**.
2. Pick the **User** (the ringer) and the **Piece**.
3. Pick the **Position** from the fixed code list (`P1`–`P11`, `LB1`–`LB3`,
   `Float`, `Other`).
4. Save.

That Entry row is what makes the piece appear on the ringer's
`/concerts/<id>` page, with the position shown read-only. Repeat once per
(ringer, piece) — a ringer can only have one Entry per piece.

A few things worth knowing:

- **`Float`** means "not performing" — the ringer sees the piece listed with
  the `Float` label but no equipment form to fill in.
- If a ringer has no Entry for a piece, that piece doesn't appear in their
  program view at all.
- The equipment fields (misc notes, instrument/pitch selections) also show
  up on the Entry list/detail view, but read-only — those are filled in by
  the ringer from the front end, not set by the admin here.

## Instrument types: pitch vs. color (mallets)

Each **Instrument Type** (`/admin/` → Instrument Type) has a **selection mode**:

- **`pitch`** (default): the type has a low/high note range, and a ringer's
  equipment form shows a chromatic pitch picker for it. `Case` rows and the
  packing list only apply to pitch-mode types.
- **`color`**: for mallets. Leave the note ranges blank. The permitted colors
  are a fixed list in `app/color.py` (`Black yarn`, `Red yarn`, …). A ringer's
  equipment form shows a **count field per color** plus one free-text
  **Other** row (description + count). Selections are stored in
  `EntryInstrument.notes` as `label:count` pairs, e.g.
  `Green yarn:2,Red yarn:1,Other: soft bass:1`.

Per-piece mallet totals (summed across every ringer assigned to the piece)
appear on the ringer's concert-detail and piece-entry pages and in the
**Equipment Table** report ("Mallets Needed Per Piece").

### Where a type is enabled, and who sees it

Two more fields on an Instrument Type control this, independently of the
selection mode:

- **`enabled_by_default`**: the type is attached to every newly created piece.
  Pieces get created from two different admin forms (the Piece view and the
  inline form under a Concert), so this lives in a `before_flush` hook in
  `app/models.py` rather than in either form. It only applies to pieces being
  created — you can still uncheck the type on a piece that doesn't use it, and
  it won't come back. Set on **Mallets** and **Bass Bells**.
- **`position_prefix`**: when set, only ringers whose position starts with it
  see that picker on their equipment form. **Bass Bells** uses `LB`, so it
  reaches `LB1`–`LB3` and nobody else. Blank means everyone on the piece sees
  it. The dropdown is derived from `POSITION_CODES` by
  `positions.position_prefixes()`, so it can't drift out of sync.

The two combine: Bass Bells is enabled on every piece, but since only LB
ringers ever see it, enabling it everywhere costs nothing and saves the admin
from ticking it piece by piece.

Visibility is presentation only. A selection that's hidden from its own ringer
— say an `LB1` ringer who's since been moved to `P1` — is left untouched when
they save, and still counts in the reports.

## Deploying to DigitalOcean

This repo includes a `Dockerfile` and `.do/app.yaml` for [App Platform](https://docs.digitalocean.com/products/app-platform/).

```sh
doctl apps create --spec .do/app.yaml
```

**SQLite persistence caveat:** App Platform's filesystem is ephemeral — anything written to disk (including the SQLite file) is lost on every redeploy or restart. This scaffold is fine for a prototype or low-stakes internal tool, but for anything you need to keep:

- Switch to DigitalOcean's Managed Postgres (change `DATABASE_URL` — SQLAlchemy makes this a one-line swap), or
- Deploy to a Droplet instead of App Platform, where the SQLite file lives on a real persistent disk.

## Environment variables

- `SECRET_KEY` - Flask session secret (set a real value in production)
- `DATABASE_URL` - defaults to the local SQLite file if unset
