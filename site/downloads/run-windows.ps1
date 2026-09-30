py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DB_BACKEND="mysql"
$env:MYSQL_HOST="127.0.0.1"
$env:MYSQL_PORT="3306"
$env:MYSQL_DATABASE="pm08_design_2027"
$env:MYSQL_USER="pm08_design"
$env:MYSQL_PASSWORD="Practice2027Db!"
.\.venv\Scripts\python.exe -m flask --app app run --port 5017
