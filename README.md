# Bell Tracker

Flask + Postgres app with a Flask-Admin panel, running in Docker.

## Local development

```sh
docker compose up
```

Visit http://127.0.0.1:5000 for the app and http://127.0.0.1:5000/admin/ for the admin panel.

That starts Postgres and the app, applies any pending migrations, and serves
with Flask's reloader. The source directory is mounted into the container, so
edits take effect without a rebuild — rebuild (`docker compose build web`) only
when dependencies change.

The database lives in a named Docker volume (`pgdata`), so it survives
`docker compose down`. Only `docker compose down -v` destroys it. Postgres is
published on host port 5432, so nothing else can be bound to that port while
the stack is up.

There's no self-signup — bootstrap the first admin with:

```sh
docker compose exec web flask --app wsgi create-admin
```

## User accounts and passwords

Admins create users at `/admin/` → **User** with a temporary password. Any
password an admin sets (on create or edit, except on their own account)
marks the user as needing a change: at their next login they're held on
`/change-password` until they choose their own. Anyone logged in can change
their password from the **Change password** link in the nav.

The login page's **Forgot my password?** link emails a reset link that
expires after an hour and works only once.

Email goes out over SMTP, configured with environment variables:

| Variable | Meaning |
| --- | --- |
| `MAIL_SERVER` | SMTP host. Unset → emails are written to the app log instead of sent. |
| `MAIL_PORT` | Default `587` (STARTTLS). |
| `MAIL_USE_SSL` | `true` for implicit TLS, usually port `465`. |
| `MAIL_USERNAME` / `MAIL_PASSWORD` | SMTP credentials. |
| `MAIL_DEFAULT_SENDER` | The From address. Falls back to `MAIL_USERNAME`. |

Locally `MAIL_SERVER` is unset, so copy reset links from
`docker compose logs web`. DigitalOcean may block outbound port 587. If sends
time out there, use your provider's port 2525, or 465 with `MAIL_USE_SSL=true`.

## Tests

```sh
docker compose up -d db
uv sync
uv run pytest
```

Tests run against Postgres — the same engine as production, so the suite
catches dialect problems that SQLite would have hidden. They use a separate
`bell_tracker_test` database (created by `docker/initdb/01-test-db.sql` when
the volume is first initialized) and rebuild the schema per test, so they
never touch your development data. Override the connection with
`TEST_DATABASE_URL` if needed.

Because they share one database, tests can't run in parallel.

## Importing an old SQLite database

If you have a pre-Postgres `instance/app.db`, copy it across once:

```sh
docker compose up -d db
docker compose run --rm web flask --app wsgi db upgrade
uv run python scripts/sqlite_to_pg.py instance/app.db
```

This **replaces** everything in the target database. It preserves row ids and
realigns Postgres' sequences afterward, so admin-created rows don't collide.

## Cycles, programs and pieces

A **Cycle** is a season's repertoire: it owns its **Pieces**, and has several
**Programs** (performances, each with a name and date/time). Each program
plays some of the cycle's pieces in its own order. Admins manage these at
`/admin/`:

- **Cycle**: create one and tick **Active** to make it the one ringers see
  when they log in. Only one cycle can be active, so activating a cycle
  deactivates the previous one. Programs can be added inline here too.
- **Program**: pick its cycle, then add rows under **Program Pieces**, each a
  piece, its **Order** number and, for programs split into sets, its **Set**
  number (see [Sets and Resets](#sets-and-resets)). A program can only use
  its own cycle's pieces. Tick **Starting placement report** for programs
  that need it.
- **Piece**: title, cycle, instrument types.

Ringers' equipment is stored per piece, so it's entered once and shows up in
every program that plays the piece. The home page shows the active cycle with
an **Edit my equipment** button, and lists its programs. Each program links
to these pages, all printable:

| Page | Who sees it | What it shows |
| --- | --- | --- |
| **View my equipment** | Everyone | The ringer's own equipment, in program order. |
| **Program order** | Everyone | The program's pieces in order, under set headings if it has sets. |
| **My resets** | Everyone, in programs with sets | What the ringer puts out and takes off at each Reset. |
| **Cover sheets: Standard** | Everyone | A page per piece with each ringer's position and equipment (LB positions left out). |
| **Cover sheets: Bass bells** | Admins, managers, and anyone ringing an LB position in the program | A page per piece for the LB positions, showing where each bell is coming from. |
| **Starting placement** | Everyone, in programs with it ticked | Where each item is set out before the first piece: at the position that first uses it. |
| **Equipment tables** | Everyone | Every pitch used, sorted into each treble position's range, plus bell trees, percussion, sticks, mallets and misc notes. |
| **Pull list** | Everyone | Which bells to take out of each case. |
| **Resets** | Admins and managers, in programs with sets | Every position's take-off and put-out at each Reset. |
| **Everyone's resets** | Admins and managers, in programs with sets | Each ringer's My resets on its own printed page; print to PDF from the browser. |
| **Bass bell assignments** | Admins and managers | Each piece's LB positions and their bells. |
| **Cases used list** | Admins and managers | The cases to bring. |

A piece that needs no cover sheet can have **Cover sheet** unticked on its
row in the Program admin. It's left off both kinds of cover sheet but still
counts everywhere else, including where bells are coming from on the bass
bell cover sheets for later pieces.

In programs with a Starting placement report, the standard cover sheets also
say which equipment is **coming from** another position.

To make someone a manager, tick **Is Manager** on their user in `/admin/` →
**User**. Managers can see every program's reports but can't open the admin
panel.

## Sets and Resets

Some programs are split into sets, each a run of pieces. Between sets comes
a **Reset**: ringers take off what the next set doesn't use and put out what
it needs that isn't already out. There's no Reset after the last set.

To split a program into sets, give every piece a **Set** number in the
**Program** admin (1, 1, 1, 2, 2, …). Either every piece has one or none
does, and the numbers can't go down in program order. Programs without set
numbers have no Reset pages.

How the reports work it out (`resets()` in `app/reports.py`):

- Main Bells are always out and are left out. Everything else counts,
  including Bass Bells and Bass Chimes.
- Each bell, each percussion option, and a bell tree as one item is put out
  at the position that first uses it in the set, unless the set before also
  used it. It's taken off at the end of a set by the position that last
  rang it, unless the next set uses it too.
- Mallets and singing bell sticks are counted per position: a position puts
  out however many more it needs than in the set before, and takes off
  however many more it had than it needs next.
- Equipment belongs to the position. **Only the ringer on a set's first
  piece puts out** at their position, and **only the ringer on its last
  piece takes off**. A ringer who sits out either piece has nothing to do
  for that side, and one who ends a set at P5 and starts the next at P2 takes
  off P5's items and puts out P2's.
- **Leave on table** (Program admin): an instrument type and a set. That
  set's items of the type stay out through the next Reset instead of coming
  off, and the position holding them takes them off a Reset later.
- **Put out early** (Program admin): an instrument type and a set. Before
  that set, everything of the type that the set *or the next one* uses is
  put out, the next set's items at the position that first uses them there.
  For example, Chimes before Set 1 puts out every chime Sets 1 and 2 use
  before Set 1, and none come off or go out at the Reset between them. Use
  it with Leave on table after the same set to keep Set 1's chimes out
  through Set 2 as well.
- **Non-handbell** (tick it on the piece's row in the Program admin): a
  piece not rung on handbells. It stays in its set and in Program order, but
  Resets skip it: put out goes by the set's first handbell piece and take off
  by its last, and any equipment on it is ignored. A set of only non-handbell
  pieces is skipped, so the set before it runs straight into the set after
  ("Reset between Sets 1 and 3").
- Leave on table and Put out early apply only to single items (bells, percussion options, bell trees),
  not to mallets or singing bell sticks, and neither can name the last set.

## Assigning ringers to pieces and positions (admin)

Roster assignment is admin-driven: a ringer only sees a piece in their own
program view once an admin has explicitly assigned them a position on it.
This is done through the **Entry** section of the Flask-Admin panel
(`/admin/`), not by the ringer.

Prerequisites (usually set up once per cycle):

1. The **Cycle** exists with its **Pieces**.
2. The ringer has a **User** account (admin-created via `/admin/` → Users).

To assign a ringer to a piece:

1. Go to `/admin/` → **Entry** → **Create**.
2. Pick the **User** (the ringer) and the **Piece**.
3. Pick the **Position** from the fixed code list (`P1`–`P11`, `LB1`–`LB3`,
   `Float`, `Other`).
4. Save.

That Entry row is what makes the piece appear on the ringer's
**Edit my equipment** page for the cycle (`/cycles/<id>`), with the position
shown read-only. Repeat once per
(ringer, piece) — a ringer can only have one Entry per piece.

A few things worth knowing:

- **`Float`** means "not performing" — the ringer sees the piece listed with
  the `Float` label but no equipment form to fill in.
- If a ringer has no Entry for a piece, that piece doesn't appear in their
  cycle or program views at all.
- The equipment fields (misc notes, instrument/pitch selections) show up on
  the Entry list and detail views. Ringers normally fill them in, but an admin
  can correct them: misc notes on the Entry edit form, and selections with the
  music-note icon on the Entry list, which opens the ringer's equipment form.

### Progress report

`/admin/` → **Progress report** lays out a cycle's assignments like the
roster spreadsheet, with a check by each ringer who has saved their
equipment and an entered/expected count per piece. Float ringers aren't
counted.

### Equipment conflicts

An instrument can only be in one place at a time. `/admin/` → **Equipment
conflicts** lists, for a cycle, each piece where more than one position
signed up for the same instrument: a pitch, a percussion option, or a bell
tree (one instrument, whichever pitches each ringer uses). Each ringer has an
**edit** link to their selections. Main Bells and Bass Bells (every position
has its own), mallets and singing bell sticks (counted, not single
instruments) aren't checked. Nothing stops a ringer saving a clash; this page
is how you find them.

### Importing positions from a spreadsheet

For a whole cycle at once, use `/admin/` → **Import positions**. Pick the
cycle and upload the roster sheet saved as CSV:

- The first row lists the pieces. Its first cell is just a label and is
  ignored.
- Each following row starts with a position (`P1`–`P11`, `LB1`–`LB3`,
  `Float`, `Other`). Under each piece is the **first name** of the ringer at
  that position. `-` or a blank cell means nobody, and several names can
  share a cell separated by commas (e.g. `"Cam, Matt"` under Float).

Names match each user's **First name** field, ignoring case. Admins set it
on the User form; it defaults to the first word of Name. Keep first names
unique among ringers: if two users share one, give one of them a distinct
value (e.g. `Sam B`) and use that in the sheet. The page
shows a preview before anything is saved: the pieces it will create and the
assignments it will add or change. Any problem, such as an unknown position
or a name matching no user or more than one, blocks the whole import until
the sheet is fixed.

Importing only adds and updates. Pieces not already in the cycle are
created with the default instrument types, but aren't in any program yet:
add them to programs from the **Program** admin.
Assignments missing from the sheet are **not** removed, and ringers keep any
equipment they've saved. Delete stale assignments in the **Entry** list.

## Instrument types: pitch, color (mallets), checkbox and options

Each **Instrument Type** (`/admin/` → Instrument Type) has a **selection mode**:

- **`pitch`** (default): the type has a low/high note range, and a ringer's
  equipment form shows a chromatic pitch picker for it. `Case` rows and the
  cases used list only apply to pitch-mode types.
- **`color`**: for mallets. Leave the note ranges blank. The permitted colors
  are a fixed list in `app/color.py` (`Black yarn`, `Red yarn`, …). A ringer's
  equipment form shows a **count field per color** plus one free-text
  **Other** row (description + count). Selections are stored in
  `EntryInstrument.notes` as `label:count` pairs, e.g.
  `Green yarn:2,Red yarn:1,Other: soft bass:1`.

The **Equipment tables** report lists, for each kind of mallet, the most
needed on any one piece (every ringer's count on that piece added up), which
is how many to bring.

- **`checkbox`**: a single yes/no tick, for **Singing Bell Sticks**. Leave
  the note ranges blank. A ticked box stores `yes` in `EntryInstrument.notes`.
  The **Equipment table** and **Pull list** reports show the most ringers who
  ticked it on any one piece in the program, which is how many to bring.

- **`options`**: a checkbox per option, for **Percussion**. Leave the note
  ranges blank and list the options (Triangle, Slap Stick, …) under
  **Options** at the bottom of the Instrument Type form. Unlike Mallets and
  Singing Bell Sticks it isn't enabled by default: add it to the pieces that
  use it. A ringer's picks are stored as option ids in
  `EntryInstrument.notes`, so renaming an option keeps them, and deleting one
  drops it from everyone's picks. The **Equipment table** and **Pull list**
  list every option picked at least once in the program.

Any type can have a **Form label**: what ringers see on their equipment form
in place of the name. Singing Bell Sticks uses it to read "Singing Bell
Stick". Leave it blank to show the name.

Two more fields shape how a type is shown:

- **Display order**: where the type sits on the equipment form and in the
  reports, low to high. The bells are numbered in tens so a new type can go
  between two of them; anything left at the default (100) sorts last.
- **Keyboard type**: set up as one instrument with all its pitches together,
  like a bell tree. The Equipment tables list its pitches in their own
  section, and Starting placement and Resets move it as one item.

**Main Bells** are always on the tables, so the equipment form marks them
optional.

### Where a type is enabled, and who sees it

Two more fields on an Instrument Type control this, independently of the
selection mode:

- **`enabled_by_default`**: the type is attached to every newly created piece.
  Pieces get created from two different admin paths (the Piece view and the
  roster import), so this lives in a `before_flush` hook in
  `app/models.py` rather than in either form. It only applies to pieces being
  created — you can still uncheck the type on a piece that doesn't use it, and
  it won't come back. Set on **Main Bells**, **Bass Bells**, **Mallets** and
  **Singing Bell Sticks**.
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

`.do/app.yaml` describes an [App Platform](https://docs.digitalocean.com/products/app-platform/)
app: one web service built from the `prod` stage of `Dockerfile`, plus a
Managed Postgres database. The database is a separate managed service, so
App Platform's ephemeral container filesystem doesn't matter. The spec also
sets the `belltracker.org` domain and the SMTP settings for password-reset
email, sent through Postmark on port 2525.

`github.repo` in `.do/app.yaml` names the repository to deploy. To create
the app from scratch:

```sh
doctl apps create --spec .do/app.yaml
doctl apps logs <app-id> --type deploy
```

With `deploy_on_push: true`, later deploys happen on push to `main`.

DigitalOcean substitutes the real connection string into `DATABASE_URL` via
`${db.DATABASE_URL}`, so there is no database credential to manage by hand.
`SECRET_KEY`, `MAIL_USERNAME` and `MAIL_PASSWORD` are the secrets you set
yourself, in the App Platform UI or with `doctl`. Postmark's Server API Token
serves as both the SMTP username and password.

Migrations run from the container's `CMD` on every boot, which is correct at
`instance_count: 1`. If you ever scale past one instance, move `db upgrade`
into a `PRE_DEPLOY` job so instances don't race each other.

Production starts empty — bootstrap the first admin with `create-admin` from
the App Platform console.

### Loading the cases

`seed/cases.csv` holds the case list and ships in the image. Once the
instrument types exist (the `type` column has to match their names), load it
from the App Platform console (**Console** tab on the `web` component):

```sh
flask --app wsgi load-cases --dry-run   # check the sheet, save nothing
flask --app wsgi load-cases
```

Each row overwrites the case with the same case number or adds it, and cases
not in the sheet are left alone, so re-running it is harmless. Every row is
checked first (known type, valid pitches, inside the type's range), and any
problem loads nothing. A blank `high` means a single bell. Locally, run the
same command through `docker compose exec web`.

## Environment variables

- `SECRET_KEY` - Flask session secret. Defaults to `dev`; set a real value in
  production.
- `MAIL_*` - SMTP settings for password-reset email; see
  [User accounts and passwords](#user-accounts-and-passwords).
- `DATABASE_URL` - Postgres connection string. **Required** — there is no
  fallback, so a `flask` command with it unset fails immediately instead of
  quietly operating on a stray local file. Compose sets it for the app
  container, so run one-off commands there:
  `docker compose exec web flask --app wsgi <command>`. A bare `postgres://`
  or `postgresql://` URL (the form DigitalOcean hands out) is rewritten to
  `postgresql+psycopg://` in `app/__init__.py`, since SQLAlchemy would
  otherwise reach for psycopg2.
- `TEST_DATABASE_URL` - overrides the database the test suite uses
