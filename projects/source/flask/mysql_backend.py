"""MySQL/MariaDB adapter for this portal's small, parameterized SQL interface."""
import re
from datetime import date, datetime
import sqlite3
import pymysql
from pymysql.cursors import DictCursor


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Result:
    def __init__(self, cursor):
        self.lastrowid = cursor.lastrowid
        self.rowcount = cursor.rowcount
        self.rows = [Row({key: value.isoformat(' ') if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else value for key, value in row.items()}) for row in cursor.fetchall()] if cursor.description else []
        cursor.close()

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows


class MySQLConnection:
    def __init__(self, config):
        self.connection = pymysql.connect(
            host=config['MYSQL_HOST'], port=int(config['MYSQL_PORT']),
            user=config['MYSQL_USER'], password=config['MYSQL_PASSWORD'],
            database=config['MYSQL_DATABASE'], charset='utf8mb4',
            cursorclass=DictCursor, autocommit=False)

    def execute(self, sql, params=()):
        # Statements are authored by the app. User values remain driver parameters.
        sql = re.sub(r'(?<!`)\bkey\b(?!`)', '`key`', sql)
        sql = sql.replace('`key` TEXT PRIMARY KEY', '`key` VARCHAR(191) PRIMARY KEY')
        sql = sql.replace('ON CONFLICT(`key`) DO UPDATE SET window_start = excluded.window_start, hits = 1',
                          'ON DUPLICATE KEY UPDATE window_start = VALUES(window_start), hits = 1')
        sql = sql.replace('?', '%s')
        sql = sql.replace('COLLATE NOCASE', 'COLLATE utf8mb4_unicode_ci')
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            return Result(cursor)
        except pymysql.IntegrityError as error:
            cursor.close()
            self.connection.rollback()
            raise sqlite3.IntegrityError(str(error)) from error

    def executescript(self, sql):
        for statement in sql.split(';'):
            if statement.strip():
                self.execute(statement)

    def executemany(self, sql, values):
        for params in values:
            self.execute(sql, params)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()
