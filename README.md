# bell-tracker

Flask + SQLite app with a Flask-Admin panel.

## Local development

```sh
uv sync
uv run flask --app wsgi run --debug
```

Visit http://127.0.0.1:5000 for the app and http://127.0.0.1:5000/admin/ for the admin panel.

The SQLite file is created automatically at `instance/app.db` on first run.

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
