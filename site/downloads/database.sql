-- Выполните под учётной записью администратора локального MySQL.
CREATE DATABASE pm08_design_2027
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pm08_design'@'127.0.0.1'
  IDENTIFIED BY 'Practice2027Db!';
GRANT ALL PRIVILEGES ON pm08_design_2027.*
  TO 'pm08_design'@'127.0.0.1';
