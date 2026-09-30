"""Set PORTAL_TEST_MYSQL=1 to run the existing suite against isolated MariaDB databases."""
import os
import uuid
import pytest


@pytest.fixture(autouse=True)
def mysql_for_test(monkeypatch):
    if os.environ.get('PORTAL_TEST_MYSQL') != '1':
        monkeypatch.setenv('DB_BACKEND', 'sqlite')
        yield
        return
    import pymysql
    name = 'rvpm_test_' + uuid.uuid4().hex
    connection = pymysql.connect(host='127.0.0.1', port=int(os.environ.get('MYSQL_PORT', '3306')), user=os.environ.get('MYSQL_USER', 'root'),
                                 password=os.environ.get('MYSQL_PASSWORD', ''), autocommit=True)
    with connection.cursor() as cursor:
        cursor.execute('CREATE DATABASE `' + name + '` CHARACTER SET utf8mb4')
    monkeypatch.setenv('DB_BACKEND', 'mysql')
    monkeypatch.setenv('MYSQL_DATABASE', name)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('DROP DATABASE `' + name + '`')
        connection.close()
