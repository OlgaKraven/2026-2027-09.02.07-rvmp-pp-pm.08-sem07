<?php
declare(strict_types=1);
final class Database {
    private PDO $pdo;
    public function __construct() {
        $this->pdo = new PDO('mysql:host='.(getenv('MYSQL_HOST') ?: '127.0.0.1').';port='.(getenv('MYSQL_PORT') ?: '3306').';dbname='.(getenv('MYSQL_DATABASE') ?: 'conference_php_2027').';charset=utf8mb4', getenv('MYSQL_USER') ?: 'root', getenv('MYSQL_PASSWORD') ?: '', [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC,PDO::ATTR_EMULATE_PREPARES=>false]);
    }
    public function query(string $sql,array $args=[]): PDOStatement {$s=$this->pdo->prepare($sql);$s->execute($args);return $s;}
}
function e(mixed $v):string{return htmlspecialchars((string)$v,ENT_QUOTES|ENT_SUBSTITUTE,'UTF-8');}
function url(string $route='home'):string{return 'index.php?r='.rawurlencode($route);}
function go(string $route):never{header('Location: '.url($route));exit;}
function csrf():string{return '<input type="hidden" name="csrf" value="'.e($_SESSION['csrf']).'">';}
function flash(string $text):void{$_SESSION['flash']=$text;}
function fail(int $status,string $message):never{http_response_code($status);echo '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Ошибка</title><h1>'.e($status).'</h1><p>'.e($message).'</p><a href="index.php">На главную</a></html>';exit;}
function field(string $name,string $label,array $values,array $errors,string $type='text',string $extra=''):void{echo '<label for="'.e($name).'">'.e($label).'</label><input id="'.e($name).'" name="'.e($name).'" type="'.e($type).'" value="'.($type==='password'?'':e($values[$name]??'')).'" required '.$extra.'>';if(isset($errors[$name]))echo '<p class="error" role="alert">'.e($errors[$name]).'</p>';}
