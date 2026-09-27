# bell-tracker

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

`.do/app.yaml` describes an [App Platform](https://docs.digitalocean.com/products/app-platform/)
app: one web service built from the `prod` stage of `Dockerfile`, plus a
Managed Postgres database. The database is a separate managed service, so
App Platform's ephemeral container filesystem no longer matters.

Before the first deploy, set `github.repo` in `.do/app.yaml` to your
repository. Then:

```sh
doctl apps create --spec .do/app.yaml
doctl apps logs <app-id> --type deploy
```

With `deploy_on_push: true`, later deploys happen on push to `main`.

DigitalOcean substitutes the real connection string into `DATABASE_URL` via
`${db.DATABASE_URL}`, so there is no database credential to manage by hand.
`SECRET_KEY` is the one secret you set yourself, in the App Platform UI or
with `doctl`.

Migrations run from the container's `CMD` on every boot, which is correct at
`instance_count: 1`. If you ever scale past one instance, move `db upgrade`
into a `PRE_DEPLOY` job so instances don't race each other.

Production starts empty — bootstrap the first admin with `create-admin` from
the App Platform console.

## Environment variables

- `SECRET_KEY` - Flask session secret (set a real value in production)
- `DATABASE_URL` - Postgres connection string. **Required** — there is no
  fallback, so a `flask` command with it unset fails immediately instead of
  quietly operating on a stray local file. Compose sets it for the app
  container, so run one-off commands there:
  `docker compose exec web flask --app wsgi <command>`. A bare `postgres://`
  or `postgresql://` URL (the form DigitalOcean hands out) is rewritten to
  `postgresql+psycopg://` in `app/__init__.py`, since SQLAlchemy would
  otherwise reach for psycopg2.
- `TEST_DATABASE_URL` - overrides the database the test suite uses
