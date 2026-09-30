import re
from datetime import date, timedelta

import pytest
from werkzeug.security import check_password_hash

from app import create_app, get_db


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "DATABASE": str(tmp_path / "test.sqlite3"),
    })


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client, path):
    response = client.get(path)
    assert response.status_code == 200
    match = re.search(r'name="_csrf_token" value="([^"]+)"', response.get_data(as_text=True))
    assert match, "CSRF token not found at " + path
    return match.group(1)


def register(client, username="student1", email="student@example.ru"):
    return client.post("/register", data={
        "_csrf_token": csrf(client, "/register"),
        "username": username,
        "password": "StrongPass8",
        "password_confirm": "StrongPass8",
        "full_name": "Иванов Иван Иванович",
        "phone": "8(900)123-45-67",
        "email": email,
    }, follow_redirects=True)


def login(client, username="student1", password="StrongPass8"):
    return client.post("/login", data={
        "_csrf_token": csrf(client, "/login"),
        "username": username,
        "password": password,
    }, follow_redirects=True)


def logout(client, page="/dashboard"):
    return client.post("/logout", data={"_csrf_token": csrf(client, page)}, follow_redirects=True)


def test_public_pages_and_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Конференции.РФ" in response.get_data(as_text=True)
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert client.get("/rooms").status_code == 200


def test_registration_validation_and_password_hash(app, client):
    bad = client.post("/register", data={
        "_csrf_token": csrf(client, "/register"),
        "username": "я",
        "password": "short",
        "password_confirm": "different",
        "full_name": "Ivan Ivanov",
        "phone": "123",
        "email": "bad",
    })
    assert "Не менее 6 символов" in bad.get_data(as_text=True)
    assert "Формат телефона" in bad.get_data(as_text=True)

    response = register(client)
    assert "Профиль создан" in response.get_data(as_text=True)
    with app.app_context():
        user = get_db().execute("SELECT * FROM users WHERE username = ?", ("student1",)).fetchone()
        assert user["password_hash"] != "StrongPass8"
        assert check_password_hash(user["password_hash"], "StrongPass8")


def test_duplicate_username_is_rejected(client):
    register(client)
    response = register(client, email="other@example.ru")
    assert "Такой логин уже занят" in response.get_data(as_text=True)


def test_csrf_required(client):
    response = client.post("/login", data={"username": "Conf2027", "password": "Demo77"})
    assert response.status_code == 400


def test_login_rate_limit(client):
    token = csrf(client, "/login")
    for _ in range(10):
        response = client.post(
            "/login",
            data={"_csrf_token": token, "username": "missing1", "password": "WrongPass8"},
        )
        assert response.status_code == 200
    blocked = client.post(
        "/login",
        data={"_csrf_token": token, "username": "missing1", "password": "WrongPass8"},
    )
    assert blocked.status_code == 429


def test_regular_user_cannot_open_admin(client):
    register(client)
    login(client)
    assert client.get("/admin").status_code == 403


def test_complete_booking_journey(app, client):
    register(client)
    assert "Мои заявки" in login(client).get_data(as_text=True)
    future = (date.today() + timedelta(days=14)).isoformat()
    created = client.post("/applications/new", data={
        "_csrf_token": csrf(client, "/applications/new"),
        "room_id": "1",
        "conference_name": "Технологии будущего",
        "event_date": future,
        "start_time": "10:30",
        "attendees": "50",
        "payment_method": "sbp",
    }, follow_redirects=True)
    assert "Заявка №1 отправлена" in created.get_data(as_text=True)
    with app.app_context():
        assert get_db().execute("SELECT status FROM applications WHERE id=1").fetchone()[0] == "new"

    too_early = client.post("/applications/1/review", data={
        "_csrf_token": csrf(client, "/dashboard"),
        "rating": "5",
        "comment": "Отличное пространство и организация.",
    }, follow_redirects=True)
    assert "только после завершения" in too_early.get_data(as_text=True)

    logout(client)
    assert "Панель администратора" in login(client, "Conf2027", "Demo77").get_data(as_text=True)
    assert "Технологии будущего" in client.get("/admin?status=new").get_data(as_text=True)
    changed = client.post("/admin/applications/1/status", data={
        "_csrf_token": csrf(client, "/admin"),
        "status": "completed",
    }, follow_redirects=True)
    assert "Завершено" in changed.get_data(as_text=True)

    logout(client, "/admin")
    login(client)
    reviewed = client.post("/applications/1/review", data={
        "_csrf_token": csrf(client, "/dashboard"),
        "rating": "5",
        "comment": "Отличное пространство и организация.",
    }, follow_redirects=True)
    assert "Отзыв опубликован" in reviewed.get_data(as_text=True)
    with app.app_context():
        assert get_db().execute("SELECT rating FROM reviews WHERE application_id=1").fetchone()[0] == 5


def test_application_rejects_over_capacity(client):
    register(client)
    login(client)
    response = client.post("/applications/new", data={
        "_csrf_token": csrf(client, "/applications/new"),
        "room_id": "1",
        "conference_name": "Большой форум",
        "event_date": (date.today() + timedelta(days=7)).isoformat(),
        "start_time": "11:00",
        "attendees": "999",
        "payment_method": "onsite",
    })
    assert "Вместимость выбранного зала" in response.get_data(as_text=True)
