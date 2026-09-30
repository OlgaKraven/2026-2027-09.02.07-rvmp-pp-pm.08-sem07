PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS rate_limits;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (category IN ('auditorium', 'coworking', 'cinema')),
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    hourly_rate INTEGER NOT NULL CHECK (hourly_rate >= 0),
    image TEXT NOT NULL,
    description TEXT NOT NULL,
    equipment TEXT NOT NULL
);

CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE RESTRICT,
    conference_name TEXT NOT NULL CHECK (length(conference_name) BETWEEN 3 AND 120),
    event_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    attendees INTEGER NOT NULL CHECK (attendees > 0),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('onsite', 'sbp')),
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'scheduled', 'completed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL UNIQUE REFERENCES applications(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL CHECK (length(comment) BETWEEN 10 AND 500),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rate_limits (
    key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    hits INTEGER NOT NULL CHECK (hits > 0)
);

CREATE INDEX applications_user_idx ON applications(user_id);
CREATE INDEX applications_status_idx ON applications(status);
CREATE INDEX applications_event_date_idx ON applications(event_date);
CREATE INDEX applications_room_idx ON applications(room_id);
CREATE INDEX reviews_user_idx ON reviews(user_id);
