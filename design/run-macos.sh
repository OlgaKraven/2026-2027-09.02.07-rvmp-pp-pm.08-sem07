python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DB_BACKEND=mysql
export MYSQL_HOST=127.0.0.1
export MYSQL_PORT=3306
export MYSQL_DATABASE=pm08_design_2027
export MYSQL_USER=pm08_design
export MYSQL_PASSWORD='Practice2027Db!'
.venv/bin/python -m flask --app app run --port 5017
