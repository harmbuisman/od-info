"""
Main entrypoint for the application.

- Uses the ODInfo facade object for all queries and actions.
- Knows the routing, the templates to use, which facade calls to make and which data to pass to a template.
- Initializes Flask plugins: Flask_SQLAlchemy, Flask_Login


TODO:
- fix swapped OP/DP items, e.g. halfer
- add ops caching to make it faster
- fix adding reference OP
"""

import logging
import os
import sys

import flask
from flask import Flask, g, render_template, request, session
from flask_login import LoginManager, login_user
from flask_sqlalchemy import SQLAlchemy

from config import OP_CENTER_URL, check_dirs_and_configs, feature_toggles, load_secrets
from domain.models import *  # Ensure all models are loaded to be able to create the db.
from facade.graphs import land_history_graph, nw_history_graph
from facade.odinfo import ODInfoFacade
from facade.user import load_user_by_id, load_user_by_name
from forms import LoginForm

# ---------------------------------------------------------------------- Flask

print("Checking directories and config files...")
problems = check_dirs_and_configs()
if problems:
    sys.exit("\n".join(problems))
else:
    print("Config files OK")

# ---------------------------------------------------------------------- Flask

if getattr(sys, "frozen", False):
    # When app is built with pyinstaller
    template_folder = os.path.join(sys._MEIPASS, "templates")
    static_folder = os.path.join(sys._MEIPASS, "static")
    app = Flask("od-info", template_folder=template_folder, static_folder=static_folder)
else:
    # Regular Flask startup
    app = Flask("od-info")

app.logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------- flask_SQLAlchemy

db = SQLAlchemy(model_class=Base, session_options={"autoflush": False})
# The lib adds an "instance" folder to the URL so I have to take that into account.
db_url = load_secrets()["database_name"]

print("Database URL:", db_url)
if db_url.startswith("sqlite:"):
    print("Note that the Flask_SQLAlchemy library inserts an 'instance' subdir into a sqlite Database URL.")

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_recycle": 280}

db.init_app(app)
with app.app_context():
    db.create_all()

# ---------------------------------------------------------------------- flask_login

app.secret_key = load_secrets()["secret_key"]
print("App Secret Key:", app.secret_key)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please login"


@login_manager.user_loader
def load_user(user_id):
    # return load_user_by_id(user_id)
    print("load_user", user_id)
    if "od_user" not in session:
        session["od_user"] = load_user_by_id(user_id).to_json()
    user = User.from_json(session["od_user"])
    print("load_user", user)
    print("load_user", user.get_id(), user.name, user_id)

    if user and (user.get_id() == str(user_id)):
        return user
    else:
        return None


# ---------------------------------------------------------------------- Facade Singleton


def facade() -> ODInfoFacade:
    _facade = getattr(g, "_facade", None)
    if not _facade:
        _facade = g._facade = ODInfoFacade(db)
    return _facade


# ---------------------------------------------------------------------- Flask Routes


@app.route("/", methods=["GET", "POST"])
@app.route("/dominfo/", methods=["GET", "POST"])
# @login_required
def overview():
    if request.args.get("update"):
        facade().update_dom_index()
    elif request.args.get("update_all"):
        facade().update_all()
        facade().update_realmies()
    if request.method == "POST":
        for k, v in request.form.items():
            if k.startswith("role."):
                prefix, dom, old_role = k.split(".")
                if old_role != v:
                    facade().update_role(dom, v)
            elif k.startswith("name."):
                prefix, dom, old_name = k.split(".")
                if old_name != v:
                    facade().update_player(dom, v)
    return render_template(
        "overview.html",
        feature_toggles=feature_toggles,
        doms=facade().dom_list(),
        nw_deltas=facade().nw_deltas(),
        ages=facade().all_doms_ops_age(),
    )


@app.route("/dominfo/<domcode>")
@app.route("/dominfo/<domcode>/<update>")
# @login_required
def dominfo(domcode: int, update=None):
    if update == "update":
        facade().update_ops(domcode)
    nw_history = facade().nw_history(domcode)
    dominion = facade().dominion(domcode)
    return render_template(
        "dominfo.html",
        feature_toggles=feature_toggles,
        dominion=dominion,
        military=facade().military(dominion),
        ratios=facade().ratios(dominion),
        ops_age=facade().ops_age(dominion),
        nw_history_graph=nw_history_graph(nw_history),
        land_history_graph=land_history_graph(nw_history),
        op_center_url=OP_CENTER_URL,
    )


@app.route("/towncrier")
# @login_required
def towncrier():
    if request.args.get("update"):
        facade().update_town_crier()
    return render_template("towncrier.html", feature_toggles=feature_toggles, towncrier=facade().get_town_crier())


@app.route("/stats")
# @login_required
def stats():
    if request.args.get("update"):
        facade().update_town_crier()
    return render_template("stats.html", feature_toggles=feature_toggles, stats=facade().award_stats())


@app.route("/nwtracker/<send>")
@app.route("/nwtracker")
# @login_required
def nw_tracker(send=None):
    result_of_send = ""
    if send == "send":
        result_of_send = facade().send_top_bot_nw_to_discord()
    return render_template(
        "nwtracker.html",
        feature_toggles=feature_toggles,
        top_nw=facade().get_top_bot_nw(filter_zeroes=True),
        bot_nw=facade().get_top_bot_nw(top=False, filter_zeroes=True),
        unchanged_nw=facade().get_unchanged_nw(),
        result_of_send=result_of_send,
    )


@app.route("/economy")
# @login_required
def economy():
    return render_template("economy.html", feature_toggles=feature_toggles, economy=facade().economy())


@app.route("/ratios")
# @login_required
def ratios():
    return render_template("ratios.html", feature_toggles=feature_toggles, doms=facade().ratio_list())


@app.route("/military", defaults={"versus_op": 0})
@app.route("/military/<versus_op>")
# @login_required
def military(versus_op: int = 0):
    dom_list = facade().military_list(versus_op=versus_op, top=100)
    return render_template(
        "military.html",
        feature_toggles=feature_toggles,
        doms=dom_list,
        ages=facade().all_doms_ops_age(),
        top_op=facade().top_op(dom_list),
        versus_op=int(versus_op),
        current_day=facade().current_tick.day,
    )


@app.route("/realmies")
# @login_required
def realmies():
    return render_template(
        "realmies.html", feature_toggles=feature_toggles, realmies=facade().doms_as_mil_calcs(facade().realmies())
    )


@app.route("/stealables")
# @login_required
def stealables():
    return render_template(
        "stealables.html",
        feature_toggles=feature_toggles,
        stealables=facade().stealables(),
        ages=facade().all_doms_ops_age(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm(request.form)
    if request.method == "POST":
        print("POST request received.")
        if form.validate():
            print("Form validated.")
            user = load_user_by_name(form.username.data)
            if user:
                if user.password == form.password.data:
                    print("Authenticated", user.name)
                    login_user(user)
                    print("login_user", user, "Authenticated:", user.is_authenticated)
                else:
                    print("Invalid password for", user.name)
            else:
                print("User not found:", form.username.data)
        else:
            print("Form validation failed:", form.errors)

        next_page = request.args.get("next")
        print("Redirecting to:", next_page or flask.url_for("overview"))
        return flask.redirect(next_page or flask.url_for("overview"))

    print("GET request, rendering login form.")
    return flask.render_template("login.html", form=form)


@app.route("/set_session")
def set_session():
    session["test_key"] = "test_value"
    return "Session value set!"


@app.route("/get_session")
def get_session():
    return f"Session value: {session.get('test_key', 'Not set')}"


@app.teardown_appcontext
def teardown_app(exception):
    facade = getattr(g, "_facade", None)
    if facade:
        facade.teardown()


if __name__ == "__main__":
    print("Starting Server...")
    app.run()
