

DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS applications;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS rate_limits;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(191) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email VARCHAR(191) NOT NULL UNIQUE,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE rooms (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(191) NOT NULL UNIQUE,
    category VARCHAR(20) NOT NULL CHECK (category IN ('auditorium', 'coworking', 'cinema')),
    city TEXT NOT NULL,
    address TEXT NOT NULL,
    capacity INTEGER NOT NULL CHECK (capacity > 0),
    hourly_rate INTEGER NOT NULL CHECK (hourly_rate >= 0),
    image TEXT NOT NULL,
    description TEXT NOT NULL,
    equipment TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    user_id INTEGER NOT NULL,
    room_id INTEGER NOT NULL,
    conference_name TEXT NOT NULL CHECK (length(conference_name) BETWEEN 3 AND 120),
    event_date VARCHAR(10) NOT NULL,
    start_time TEXT NOT NULL,
    attendees INTEGER NOT NULL CHECK (attendees > 0),
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('onsite', 'sbp')),
    status VARCHAR(20) NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'scheduled', 'completed')),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    application_id INTEGER NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment TEXT NOT NULL CHECK (length(comment) BETWEEN 10 AND 500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE rate_limits (
    `key` VARCHAR(191) PRIMARY KEY,
    window_start INTEGER NOT NULL,
    hits INTEGER NOT NULL CHECK (hits > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX applications_user_idx ON applications(user_id);
CREATE INDEX applications_status_idx ON applications(status);
CREATE INDEX applications_event_date_idx ON applications(event_date);
CREATE INDEX applications_room_idx ON applications(room_id);
CREATE INDEX reviews_user_idx ON reviews(user_id);
