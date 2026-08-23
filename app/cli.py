import click

from app import db
from app.models import User


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
