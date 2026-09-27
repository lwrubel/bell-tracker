from urllib.parse import urlsplit

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from app import db, login_manager
from app.email import send_email
from app.forms import (
    ChangePasswordForm,
    ForgotPasswordForm,
    LoginForm,
    ResetPasswordForm,
)
from app.models import User
from app.tokens import RESET_MAX_AGE, make_reset_token, verify_reset_token

bp = Blueprint("auth", __name__)

# Where a user who still has an admin-issued password is allowed to go.
PASSWORD_CHANGE_EXEMPT_ENDPOINTS = {"auth.change_password", "auth.logout", "static"}


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@bp.before_app_request
def require_password_change():
    if (
        current_user.is_authenticated
        and current_user.must_change_password
        and request.endpoint not in PASSWORD_CHANGE_EXEMPT_ENDPOINTS
    ):
        return redirect(url_for("auth.change_password"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.login"))

        login_user(user, remember=form.remember_me.data)

        if user.must_change_password:
            flash("Please choose a new password.", "info")
            return redirect(url_for("auth.change_password"))

        next_page = request.args.get("next")
        if not next_page or urlsplit(next_page).netloc != "":
            next_page = url_for("routes.concerts_index")
        return redirect(next_page)

    return render_template("login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
        elif form.new_password.data == form.current_password.data:
            form.new_password.errors.append(
                "New password must be different from the current one."
            )
        else:
            current_user.set_password(form.new_password.data)
            current_user.must_change_password = False
            db.session.commit()
            flash("Your password has been changed.", "success")
            return redirect(url_for("routes.concerts_index"))
    return render_template("change_password.html", form=form)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("routes.concerts_index"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user is not None:
            link = url_for(
                "auth.reset_password", token=make_reset_token(user), _external=True
            )
            try:
                send_email(
                    user.email,
                    "Reset your bell-tracker password",
                    f"Hi {user.name},\n\n"
                    f"Use this link to choose a new bell-tracker password:\n\n"
                    f"{link}\n\n"
                    f"The link expires in {RESET_MAX_AGE // 60} minutes. If you "
                    f"didn't ask to reset your password, you can ignore this email.\n",
                )
            except Exception:
                current_app.logger.exception("Failed to send reset email")
        # Same answer either way, so this can't be used to probe for accounts.
        flash("If that email has an account, a reset link is on its way.", "info")
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("routes.concerts_index"))
    user = verify_reset_token(token)
    if user is None:
        flash("That reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.new_password.data)
        user.must_change_password = False
        db.session.commit()
        flash("Your password has been reset. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("reset_password.html", form=form)
