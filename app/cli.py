from pathlib import Path

import click

from app import case_seed, db
from app.models import User

DEFAULT_CASES_CSV = Path(__file__).resolve().parent.parent / "seed" / "cases.csv"


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.option(
        "--password", prompt=True, hide_input=True, confirmation_prompt=True
    )
    def create_admin(email, name, password):
        """Create the first admin user (there's no self-registration)."""
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            click.echo(f"A user with email {email} already exists.")
            return
        user = User(email=email, name=name, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created admin user {email}.")

    @app.cli.command("load-cases")
    @click.argument(
        "csv_path",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        default=DEFAULT_CASES_CSV,
    )
    @click.option(
        "--dry-run", is_flag=True, help="Check the sheet and report, saving nothing."
    )
    def load_cases(csv_path, dry_run):
        """Add or overwrite cases from a CSV (default: seed/cases.csv)."""
        result = case_seed.load_cases(
            csv_path.read_text(encoding="utf-8-sig"), dry_run=dry_run
        )
        if result.errors:
            for error in result.errors:
                click.echo(error, err=True)
            raise click.ClickException("Nothing was loaded.")
        verb = "Would add" if dry_run else "Added"
        click.echo(f"{verb} {len(result.added)}: {', '.join(result.added) or '-'}")
        verb = "Would overwrite" if dry_run else "Overwrote"
        click.echo(f"{verb} {len(result.updated)}: {', '.join(result.updated) or '-'}")
