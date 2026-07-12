from flask import Blueprint, redirect, render_template, request, url_for

from app import db
from app.models import Item

bp = Blueprint("routes", __name__)


@bp.route("/")
def index():
    items = Item.query.order_by(Item.created_at.desc()).all()
    return render_template("index.html", items=items)


@bp.route("/items/new", methods=["GET", "POST"])
def new_item():
    if request.method == "POST":
        item = Item(
            name=request.form["name"],
            description=request.form.get("description"),
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for("routes.index"))
    return render_template("new_item.html")
