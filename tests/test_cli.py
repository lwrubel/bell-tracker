from app.models import User


def test_create_admin_creates_an_admin_user(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-admin"],
        input="new-admin@example.com\nAdmin Name\nsecretpass\nsecretpass\n",
    )
    assert result.exit_code == 0

    user = User.query.filter_by(email="new-admin@example.com").first()
    assert user is not None
    assert user.is_admin is True
    assert user.check_password("secretpass") is True


def test_create_admin_lowercases_email(app):
    runner = app.test_cli_runner()
    runner.invoke(
        args=["create-admin"],
        input="Mixed-Case@Example.com\nAdmin\nsecretpass\nsecretpass\n",
    )

    assert User.query.filter_by(email="mixed-case@example.com").first() is not None


def test_create_admin_refuses_duplicate_email(app, admin_user):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-admin"],
        input=f"{admin_user.email}\nSomeone Else\nsecretpass\nsecretpass\n",
    )
    assert result.exit_code == 0
    assert "already exists" in result.output
    assert User.query.filter_by(email=admin_user.email).count() == 1
