"""Flask application for the «Конференции.РФ» venue booking portal."""

from __future__ import annotations

import json
import hmac
import os
import re
import secrets
import sqlite3
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

import click
from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent

STATUS_LABELS = {
    "new": "Новая",
    "scheduled": "Мероприятие назначено",
    "completed": "Завершено",
}
ROOM_TYPE_LABELS = {
    "auditorium": "Аудитория",
    "coworking": "Коворкинг",
    "cinema": "Кинозал",
}
PAYMENT_LABELS = {
    "onsite": "При очном посещении",
    "sbp": "Переводом по системе СБП",
}
PASSWORD_HASH_METHOD = "pbkdf2:sha256:600000"

USERNAME_RE = re.compile(r"^[A-Za-z0-9]{6,}$")
FULL_NAME_RE = re.compile(r"^[А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)*$")
PHONE_RE = re.compile(r"^8\(\d{3}\)\d{3}-\d{2}-\d{2}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-zА-Яа-яЁё]{2,}$")

F = TypeVar("F", bound=Callable[..., Any])
bp = Blueprint("portal", __name__)


def _persistent_secret(instance_path: str) -> str:
    """Return an environment secret or create a private persistent local key."""
    from_environment = os.environ.get("SECRET_KEY")
    if from_environment:
        return from_environment

    secret_path = Path(instance_path) / "secret_key"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    value = secrets.token_hex(32)
    secret_path.write_text(value, encoding="utf-8")
    try:
        secret_path.chmod(0o600)
    except OSError:
        pass
    return value


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    app.config.from_mapping(
        DB_BACKEND=os.environ.get('DB_BACKEND', 'sqlite'),
        MYSQL_HOST=os.environ.get('MYSQL_HOST', '127.0.0.1'),
        MYSQL_PORT=os.environ.get('MYSQL_PORT', '3306'),
        MYSQL_USER=os.environ.get('MYSQL_USER', 'root'),
        MYSQL_PASSWORD=os.environ.get('MYSQL_PASSWORD', ''),
        MYSQL_DATABASE=os.environ.get('MYSQL_DATABASE', 'conference_rvpm_2027'),
        DATABASE=str(Path(app.instance_path) / "conference.sqlite3"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 8,
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    app.config.from_pyfile("config.py", silent=True)
    if test_config:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _persistent_secret(app.instance_path)

    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.register_blueprint(bp)

    @app.before_request
    def load_logged_in_user() -> None:
        user_id = session.get("user_id")
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_id is not None
            else None
        )

    @app.before_request
    def protect_from_csrf() -> None:
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "") or request.headers.get(
            "X-CSRF-Token", ""
        )
        if not expected or not supplied or not hmac.compare_digest(expected, supplied):
            abort(400, description="Срок действия формы истёк. Обновите страницу.")

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; font-src 'self'; form-action 'self'; base-uri 'self'",
        )
        return response

    @app.context_processor
    def inject_template_globals() -> dict[str, Any]:
        return {
            "csrf_token": get_csrf_token,
            "status_labels": STATUS_LABELS,
            "room_type_labels": ROOM_TYPE_LABELS,
            "payment_labels": PAYMENT_LABELS,
            "today_iso": date.today().isoformat(),
        }

    @app.template_filter("pretty_date")
    def pretty_date(value: str) -> str:
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
        except (TypeError, ValueError):
            return value

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(429)
    def handle_http_error(error):
        messages = {
            400: ("Ошибка запроса", getattr(error, "description", "Проверьте данные.")),
            403: ("Доступ ограничен", "У вас нет прав для этой страницы."),
            404: ("Страница не найдена", "Возможно, ссылка устарела или в ней опечатка."),
            429: ("Слишком много запросов", getattr(error, "description", "Повторите позже.")),
        }
        title, message = messages[error.code]
        return render_template("error.html", title=title, message=message), error.code

    database_path = Path(app.config["DATABASE"])
    if app.config['DB_BACKEND'] == 'mysql':
        with app.app_context():
            db = get_db()
            tables = db.execute('SHOW TABLES').fetchall()
            if not tables:
                init_db()
    elif not database_path.exists():
        with app.app_context():
            init_db()

    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        if current_app.config['DB_BACKEND'] == 'mysql':
            from mysql_backend import MySQLConnection
            g.db = MySQLConnection(current_app.config)
            return g.db
        g.db = sqlite3.connect(
            current_app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def consume_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    """Consume one attempt in a small SQLite-backed fixed window."""
    now = int(time.time())
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limits (
            key TEXT PRIMARY KEY,
            window_start INTEGER NOT NULL,
            hits INTEGER NOT NULL
        )
        """
    )
    db.execute("DELETE FROM rate_limits WHERE window_start < ?", (now - 86400,))
    row = db.execute(
        "SELECT window_start, hits FROM rate_limits WHERE key = ?", (key,)
    ).fetchone()
    if row is None or now - row["window_start"] >= window_seconds:
        db.execute(
            """
            INSERT INTO rate_limits (key, window_start, hits) VALUES (?, ?, 1)
            ON CONFLICT(key) DO UPDATE SET window_start = excluded.window_start, hits = 1
            """,
            (key, now),
        )
        db.commit()
        return True
    if row["hits"] >= limit:
        db.commit()
        return False
    db.execute("UPDATE rate_limits SET hits = hits + 1 WHERE key = ?", (key,))
    db.commit()
    return True


def reset_rate_limit(key: str) -> None:
    db = get_db()
    db.execute("DELETE FROM rate_limits WHERE key = ?", (key,))
    db.commit()


def init_db() -> None:
    db = get_db()
    schema = (BASE_DIR / ('schema-mysql.sql' if current_app.config['DB_BACKEND'] == 'mysql' else 'schema.sql')).read_text(encoding="utf-8")
    db.executescript(schema)

    admin_hash = generate_password_hash("Demo77", method=PASSWORD_HASH_METHOD)
    db.execute(
        """
        INSERT INTO users (username, password_hash, full_name, phone, email, is_admin)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (
            "Conf2027",
            admin_hash,
            "Администратор Портала",
            "8(800)000-00-00",
            "admin@conference.test",
        ),
    )

    catalogue = json.loads((BASE_DIR / "rooms.json").read_text(encoding="utf-8"))
    fields = ("name", "category", "city", "address", "capacity", "hourly_rate", "image", "description", "equipment")
    rooms = [tuple(room[field] for field in fields) for room in catalogue]
    db.executemany(
        """
        INSERT INTO rooms
            (name, category, city, address, capacity, hourly_rate, image, description, equipment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rooms,
    )
    db.commit()


@click.command("init-db")
@click.option("--yes", is_flag=True, help="Подтвердить пересоздание без вопроса.")
def init_db_command(yes: bool) -> None:
    """Recreate the database and seed the venue catalogue."""
    if not yes and not click.confirm("Пересоздать базу? Текущие данные будут удалены"):
        click.echo("Отменено.")
        return
    init_db()
    click.echo("База данных создана.")


def get_csrf_token() -> str:
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return session["_csrf_token"]


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Войдите, чтобы продолжить.", "info")
            return redirect(url_for("portal.login"))
        return view(*args, **kwargs)

    return wrapped_view  # type: ignore[return-value]


def admin_required(view: F) -> F:
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Войдите как администратор.", "info")
            return redirect(url_for("portal.login"))
        if not g.user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view  # type: ignore[return-value]


@bp.get("/")
def index():
    db = get_db()
    rooms = db.execute("SELECT * FROM rooms ORDER BY id LIMIT 3").fetchall()
    stats = db.execute(
        "SELECT COUNT(*) AS room_count, SUM(capacity) AS total_capacity FROM rooms"
    ).fetchone()
    reviews = db.execute(
        """
        SELECT reviews.*, users.full_name, rooms.name AS room_name
        FROM reviews
        JOIN users ON users.id = reviews.user_id
        JOIN applications ON applications.id = reviews.application_id
        JOIN rooms ON rooms.id = applications.room_id
        ORDER BY reviews.created_at DESC
        LIMIT 3
        """
    ).fetchall()
    return render_template("index.html", rooms=rooms, stats=stats, reviews=reviews)


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user is not None:
        return redirect(url_for("portal.dashboard"))

    errors: dict[str, str] = {}
    values = {
        "username": request.form.get("username", "").strip(),
        "full_name": request.form.get("full_name", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
    }

    if request.method == "POST":
        rate_key = f"register:{request.remote_addr or 'local'}"
        if not consume_rate_limit(rate_key, 5, 60 * 60):
            abort(429, description="Слишком много регистраций. Повторите через час.")
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if len(values["username"]) > 40 or not USERNAME_RE.fullmatch(values["username"]):
            errors["username"] = "Не менее 6 символов: только латиница и цифры."
        if not 8 <= len(password) <= 128:
            errors["password"] = "Пароль должен содержать от 8 до 128 символов."
        if password != password_confirm:
            errors["password_confirm"] = "Пароли не совпадают."
        if len(values["full_name"]) > 120 or not FULL_NAME_RE.fullmatch(values["full_name"]):
            errors["full_name"] = "Укажите ФИО кириллицей, между словами — пробелы."
        if not PHONE_RE.fullmatch(values["phone"]):
            errors["phone"] = "Формат телефона: 8(XXX)XXX-XX-XX."
        if len(values["email"]) > 254 or not EMAIL_RE.fullmatch(values["email"]):
            errors["email"] = "Введите корректный адрес электронной почты."

        if not errors:
            try:
                db = get_db()
                db.execute(
                    """
                    INSERT INTO users (username, password_hash, full_name, phone, email)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        values["username"],
                        generate_password_hash(password, method=PASSWORD_HASH_METHOD),
                        values["full_name"],
                        values["phone"],
                        values["email"],
                    ),
                )
                db.commit()
            except sqlite3.IntegrityError as exc:
                message = str(exc).lower()
                if "email" in message:
                    errors["email"] = "Эта почта уже используется."
                else:
                    errors["username"] = "Такой логин уже занят."
            else:
                flash("Профиль создан. Теперь войдите в систему.", "success")
                return redirect(url_for("portal.login"))

    return render_template("register.html", errors=errors, values=values)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        destination = "portal.admin" if g.user["is_admin"] else "portal.dashboard"
        return redirect(url_for(destination))

    error = None
    username = request.form.get("username", "").strip()
    if request.method == "POST":
        password = request.form.get("password", "")
        if not username or not password:
            error = "Введите логин и пароль."
        elif len(username) > 40 or len(password) > 128:
            error = "Неверный логин или пароль."
        else:
            rate_key = f"login:{request.remote_addr or 'local'}:{username.casefold()}"
            if not consume_rate_limit(rate_key, 10, 15 * 60):
                abort(429, description="Слишком много попыток входа. Повторите позже.")
            user = get_db().execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                error = "Неверный логин или пароль."
            else:
                reset_rate_limit(rate_key)
                session.clear()
                session["user_id"] = user["id"]
                session.permanent = True
                flash(f"С возвращением, {user['full_name'].split()[0]}!", "success")
                destination = "portal.admin" if user["is_admin"] else "portal.dashboard"
                return redirect(url_for(destination))

    return render_template("login.html", error=error, username=username)


@bp.post("/logout")
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("portal.index"))


@bp.get("/rooms")
def rooms():
    category = request.args.get("category", "")
    city = request.args.get("city", "")
    capacity_raw = request.args.get("capacity", "").strip()
    conditions: list[str] = []
    params: list[Any] = []

    if category in ROOM_TYPE_LABELS:
        conditions.append("category = ?")
        params.append(category)
    else:
        category = ""
    if city:
        conditions.append("city = ?")
        params.append(city)
    try:
        capacity = max(0, int(capacity_raw)) if capacity_raw else 0
    except ValueError:
        capacity = 0
    if capacity:
        conditions.append("capacity >= ?")
        params.append(capacity)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    db = get_db()
    room_rows = db.execute(
        f"SELECT * FROM rooms {where} ORDER BY hourly_rate, name", params
    ).fetchall()
    cities = db.execute("SELECT DISTINCT city FROM rooms ORDER BY city").fetchall()
    return render_template(
        "rooms.html",
        rooms=room_rows,
        cities=cities,
        filters={"category": category, "city": city, "capacity": capacity_raw},
    )


@bp.get("/rooms/<int:room_id>")
def room_detail(room_id: int):
    room = get_db().execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
    if room is None:
        abort(404)
    reviews = get_db().execute(
        """
        SELECT reviews.*, users.full_name
        FROM reviews
        JOIN users ON users.id = reviews.user_id
        JOIN applications ON applications.id = reviews.application_id
        WHERE applications.room_id = ?
        ORDER BY reviews.created_at DESC
        """,
        (room_id,),
    ).fetchall()
    return render_template("room_detail.html", room=room, reviews=reviews)


@bp.get("/dashboard")
@login_required
def dashboard():
    if g.user["is_admin"]:
        return redirect(url_for("portal.admin"))
    applications = get_db().execute(
        """
        SELECT applications.*, rooms.name AS room_name, rooms.category, rooms.city,
               rooms.image, rooms.address, reviews.id AS review_id,
               reviews.rating, reviews.comment AS review_comment
        FROM applications
        JOIN rooms ON rooms.id = applications.room_id
        LEFT JOIN reviews ON reviews.application_id = applications.id
        WHERE applications.user_id = ?
        ORDER BY applications.created_at DESC, applications.id DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template("dashboard.html", applications=applications)


def _application_form_values() -> dict[str, str]:
    return {
        "room_id": request.form.get("room_id", request.args.get("room", "")).strip(),
        "conference_name": request.form.get("conference_name", "").strip(),
        "event_date": request.form.get("event_date", "").strip(),
        "start_time": request.form.get("start_time", "").strip(),
        "attendees": request.form.get("attendees", "").strip(),
        "payment_method": request.form.get("payment_method", "").strip(),
    }


@bp.route("/applications/new", methods=("GET", "POST"))
@login_required
def new_application():
    if g.user["is_admin"]:
        return redirect(url_for("portal.admin"))

    db = get_db()
    rooms = db.execute("SELECT * FROM rooms ORDER BY city, name").fetchall()
    values = _application_form_values()
    errors: dict[str, str] = {}

    if request.method == "POST":
        room = None
        try:
            room_id = int(values["room_id"])
            room = db.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        except (TypeError, ValueError):
            room_id = 0
        if room is None:
            errors["room_id"] = "Выберите помещение из списка."

        if not 3 <= len(values["conference_name"]) <= 120:
            errors["conference_name"] = "Название должно содержать от 3 до 120 символов."

        try:
            requested_date = date.fromisoformat(values["event_date"])
            if requested_date < date.today():
                errors["event_date"] = "Дата конференции не может быть в прошлом."
        except ValueError:
            errors["event_date"] = "Укажите дату конференции."

        if not re.fullmatch(r"(?:0[8-9]|1\d|2[0-2]):[0-5]\d", values["start_time"]):
            errors["start_time"] = "Выберите время с 08:00 до 22:59."

        try:
            attendees = int(values["attendees"])
            if attendees < 1:
                raise ValueError
            if room is not None and attendees > room["capacity"]:
                errors["attendees"] = f"Вместимость выбранного зала — {room['capacity']} чел."
        except ValueError:
            attendees = 0
            errors["attendees"] = "Укажите количество участников."

        if values["payment_method"] not in PAYMENT_LABELS:
            errors["payment_method"] = "Выберите способ оплаты."

        if not errors:
            cursor = db.execute(
                """
                INSERT INTO applications
                    (user_id, room_id, conference_name, event_date, start_time,
                     attendees, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    room_id,
                    values["conference_name"],
                    values["event_date"],
                    values["start_time"],
                    attendees,
                    values["payment_method"],
                ),
            )
            db.commit()
            flash(f"Заявка №{cursor.lastrowid} отправлена на рассмотрение.", "success")
            return redirect(url_for("portal.dashboard"))

    return render_template(
        "application_form.html", rooms=rooms, values=values, errors=errors
    )


@bp.post("/applications/<int:application_id>/review")
@login_required
def add_review(application_id: int):
    db = get_db()
    application = db.execute(
        """
        SELECT applications.*, reviews.id AS review_id
        FROM applications
        LEFT JOIN reviews ON reviews.application_id = applications.id
        WHERE applications.id = ? AND applications.user_id = ?
        """,
        (application_id, g.user["id"]),
    ).fetchone()
    if application is None:
        abort(404)
    if application["status"] != "completed":
        flash("Отзыв можно оставить только после завершения мероприятия.", "error")
        return redirect(url_for("portal.dashboard") + f"#application-{application_id}")
    if application["review_id"] is not None:
        flash("Отзыв к этой заявке уже оставлен.", "info")
        return redirect(url_for("portal.dashboard") + f"#application-{application_id}")

    try:
        rating = int(request.form.get("rating", ""))
    except ValueError:
        rating = 0
    comment = request.form.get("comment", "").strip()
    if rating not in range(1, 6) or not 10 <= len(comment) <= 500:
        flash("Поставьте оценку от 1 до 5 и напишите от 10 до 500 символов.", "error")
        return redirect(url_for("portal.dashboard") + f"#application-{application_id}")

    try:
        db.execute(
            "INSERT INTO reviews (application_id, user_id, rating, comment) VALUES (?, ?, ?, ?)",
            (application_id, g.user["id"], rating, comment),
        )
        db.commit()
    except sqlite3.IntegrityError:
        flash("Отзыв к этой заявке уже оставлен.", "info")
    else:
        flash("Спасибо! Отзыв опубликован.", "success")
    return redirect(url_for("portal.dashboard") + f"#application-{application_id}")


@bp.get("/admin")
@admin_required
def admin():
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    payment = request.args.get("payment", "")
    query = request.args.get("q", "").strip()[:100]
    sort = request.args.get("sort", "newest")

    conditions: list[str] = []
    params: list[Any] = []
    if status in STATUS_LABELS:
        conditions.append("applications.status = ?")
        params.append(status)
    else:
        status = ""
    if category in ROOM_TYPE_LABELS:
        conditions.append("rooms.category = ?")
        params.append(category)
    else:
        category = ""
    if payment in PAYMENT_LABELS:
        conditions.append("applications.payment_method = ?")
        params.append(payment)
    else:
        payment = ""
    if query:
        conditions.append(
            "(users.username LIKE ? OR users.full_name LIKE ? OR "
            "applications.conference_name LIKE ? OR rooms.name LIKE ?)"
        )
        params.extend([f"%{query}%"] * 4)

    order_options = {
        "newest": "applications.created_at DESC, applications.id DESC",
        "date_asc": "applications.event_date ASC, applications.start_time ASC",
        "date_desc": "applications.event_date DESC, applications.start_time DESC",
    }
    if sort not in order_options:
        sort = "newest"
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    db = get_db()
    applications = db.execute(
        f"""
        SELECT applications.*, users.username, users.full_name, users.phone, users.email,
               rooms.name AS room_name, rooms.category, rooms.city, rooms.address, rooms.image,
               reviews.rating, reviews.comment AS review_comment
        FROM applications
        JOIN users ON users.id = applications.user_id
        JOIN rooms ON rooms.id = applications.room_id
        LEFT JOIN reviews ON reviews.application_id = applications.id
        {where}
        ORDER BY {order_options[sort]}
        """,
        params,
    ).fetchall()
    counts = db.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) AS new_count,
               SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled_count,
               SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_count
        FROM applications
        """
    ).fetchone()
    return render_template(
        "admin.html",
        applications=applications,
        counts=counts,
        filters={
            "status": status,
            "category": category,
            "payment": payment,
            "q": query,
            "sort": sort,
        },
    )


@bp.post("/admin/applications/<int:application_id>/status")
@admin_required
def update_application_status(application_id: int):
    new_status = request.form.get("status", "")
    if new_status not in STATUS_LABELS:
        abort(400, description="Неизвестный статус заявки.")
    db = get_db()
    cursor = db.execute(
        """
        UPDATE applications
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_status, application_id),
    )
    if cursor.rowcount == 0:
        abort(404)
    db.commit()
    flash(f"Статус заявки №{application_id}: {STATUS_LABELS[new_status]}.", "success")
    return redirect(url_for("portal.admin", **request.args))


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
