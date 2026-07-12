from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme

from app import db
from app.models import Item


def init_admin(app):
    admin = Admin(app, name="bell-tracker", theme=Bootstrap4Theme())
    admin.add_view(ModelView(Item, db.session))
    return admin
