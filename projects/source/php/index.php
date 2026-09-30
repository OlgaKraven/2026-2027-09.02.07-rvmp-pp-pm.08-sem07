<?php
declare(strict_types=1);
require __DIR__.'/lib.php';
session_start(['cookie_httponly'=>true,'cookie_samesite'=>'Lax','use_strict_mode'=>true]);
header('X-Content-Type-Options: nosniff');header('X-Frame-Options: DENY');header("Content-Security-Policy: default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'");header('Cache-Control: no-store');
$_SESSION['csrf']??=bin2hex(random_bytes(32));
try{$db=new Database();$db->query('SELECT id FROM users LIMIT 1');}catch(Throwable $ex){fail(503,'База не подготовлена. Выполните шаги README: создайте пустую базу и запустите setup.php из командной строки.');}
$user=isset($_SESSION['user_id'])?$db->query('SELECT * FROM users WHERE id=?',[$_SESSION['user_id']])->fetch():null;
$route=is_string($_GET['r']??null)?$_GET['r']:'home';
if(!in_array($route,['home','rooms','register','login','logout','dashboard','new','admin','status','review'],true))fail(404,'Страница не найдена.');
if(in_array($route,['dashboard','new','review','admin','status','logout'],true)&&!$user)go('login');
if(in_array($route,['admin','status'],true)&&!(int)$user['is_admin'])fail(403,'Доступ только администратору.');
$post=$_SERVER['REQUEST_METHOD']==='POST';
if(in_array($route,['logout','status','review'],true)&&!$post)fail(405,'Для этого действия нужен POST.');
if($post&&(!is_string($_POST['csrf']??null)||!hash_equals($_SESSION['csrf'],$_POST['csrf'])))fail(400,'Неверный CSRF-токен. Обновите форму.');
$values=[];foreach($_POST as $k=>$v)if(is_string($v))$values[$k]=trim($v);
$errors=[];$statusLabels=['new'=>'Новая','scheduled'=>'Мероприятие назначено','completed'=>'Завершено'];$payments=['onsite'=>'При очном посещении','sbp'=>'Переводом по системе СБП'];
if($post&&in_array($route,['login','register'],true)){
    // Atomic counter shared by sessions; a new cookie does not bypass the limit.
    $key=$route.':'.($_SERVER['REMOTE_ADDR']??'local');$now=time();
    $db->query('INSERT INTO rate_limits(`key`,window_start,hits) VALUES(?,?,1) ON DUPLICATE KEY UPDATE hits=IF(window_start < ?,1,hits+1),window_start=IF(window_start < ?,VALUES(window_start),window_start)',[$key,$now,$now-600,$now-600]);
    if((int)$db->query('SELECT hits FROM rate_limits WHERE `key`=?',[$key])->fetchColumn()>30)fail(429,'Слишком много попыток. Повторите через 10 минут.');
}
if($post&&$route==='register'){
    if(!preg_match('/^[A-Za-z0-9]{6,191}$/D',$values['username']??''))$errors['username']='Латиница и цифры, от 6 до 191 символа.';
    if(mb_strlen($values['password']??'')<8||strlen($values['password']??'')>72)$errors['password']='Пароль: от 8 символов, не более 72 байт.';
    if(($values['password']??'')!==($values['confirm']??''))$errors['confirm']='Пароли не совпадают.';
    if(!preg_match('/^[А-Яа-яЁё]+(?: +[А-Яа-яЁё]+)*$/uD',$values['full_name']??'')||mb_strlen($values['full_name']??'')>150)$errors['full_name']='Введите ФИО кириллицей, слова разделяйте пробелами.';
    if(!preg_match('/^8\([0-9]{3}\)[0-9]{3}-[0-9]{2}-[0-9]{2}$/D',$values['phone']??''))$errors['phone']='Формат: 8(XXX)XXX-XX-XX.';
    if(!filter_var($values['email']??'',FILTER_VALIDATE_EMAIL)||strlen($values['email']??'')>191)$errors['email']='Введите корректный e-mail до 191 символа.';
    if(!$errors){try{$db->query('INSERT INTO users(username,password_hash,full_name,phone,email) VALUES(?,?,?,?,?)',[$values['username'],password_hash($values['password'],PASSWORD_DEFAULT),$values['full_name'],$values['phone'],$values['email']]);flash('Профиль создан. Теперь войдите.');go('login');}catch(PDOException $ex){if($ex->getCode()!=='23000')throw $ex;$errors['username']='Логин или e-mail уже используется.';}}
}
if($post&&$route==='login'){
    $found=$db->query('SELECT * FROM users WHERE username=?',[$values['username']??''])->fetch();
    if(!$found||!password_verify($values['password']??'',$found['password_hash']))$errors['password']='Неверный логин или пароль.';
    else{session_regenerate_id(true);$_SESSION['user_id']=$found['id'];$_SESSION['csrf']=bin2hex(random_bytes(32));go((int)$found['is_admin']?'admin':'dashboard');}
}
if($post&&$route==='logout'){$_SESSION=[];session_regenerate_id(true);go('home');}
if($post&&$route==='new'){
    $room=$db->query('SELECT * FROM rooms WHERE id=?',[(int)($values['room_id']??0)])->fetch();
    if(!$room)$errors['room_id']='Выберите помещение из каталога.';
    $date=DateTimeImmutable::createFromFormat('!Y-m-d',$values['event_date']??'');
    if(!$date||$date->format('Y-m-d')!==($values['event_date']??'')||$date<new DateTimeImmutable('today'))$errors['event_date']='Выберите существующую дату не раньше сегодняшней.';
    if(!preg_match('/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/D',$values['start_time']??''))$errors['start_time']='Введите время ЧЧ:ММ.';
    if(!isset($payments[$values['payment_method']??'']))$errors['payment_method']='Выберите способ оплаты.';
    $count=filter_var($values['attendees']??'',FILTER_VALIDATE_INT);
    if(!$count||$count<1||($room&&$count>(int)$room['capacity']))$errors['attendees']='Количество участников должно соответствовать вместимости зала.';
    if(mb_strlen($values['conference_name']??'')<3||mb_strlen($values['conference_name']??'')>120)$errors['conference_name']='Название: от 3 до 120 символов.';
    if(!$errors){$db->query('INSERT INTO applications(user_id,room_id,conference_name,event_date,start_time,attendees,payment_method) VALUES(?,?,?,?,?,?,?)',[$user['id'],$room['id'],$values['conference_name'],$values['event_date'],$values['start_time'],$count,$values['payment_method']]);flash('Заявка отправлена. Статус: Новая.');go('dashboard');}
}
if($post&&$route==='status'){
    if(!isset($statusLabels[$values['status']??'']))fail(400,'Неизвестный статус.');
    $id=(int)($values['id']??0);if(!$db->query('SELECT id FROM applications WHERE id=?',[$id])->fetch())fail(404,'Заявка не найдена.');
    $db->query('UPDATE applications SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',[$values['status'],$id]);flash('Статус обновлён.');go('admin');
}
if($post&&$route==='review'){
    $a=$db->query('SELECT * FROM applications WHERE id=? AND user_id=?',[(int)($values['id']??0),$user['id']])->fetch();
    if(!$a)fail(404,'Заявка не найдена.');if($a['status']!=='completed')fail(403,'Отзыв доступен после завершения мероприятия.');
    $rating=filter_var($values['rating']??'',FILTER_VALIDATE_INT);$comment=$values['comment']??'';
    if(!$rating||$rating<1||$rating>5||mb_strlen($comment)<10||mb_strlen($comment)>500){flash('Оценка: 1–5. Текст отзыва: 10–500 символов.');go('dashboard');}
    try{$db->query('INSERT INTO reviews(application_id,user_id,rating,comment) VALUES(?,?,?,?)',[$a['id'],$user['id'],$rating,$comment]);flash('Отзыв опубликован.');}catch(PDOException $ex){if($ex->getCode()!=='23000')throw $ex;flash('Отзыв уже существует.');}go('dashboard');
}
$titles=['home'=>'Помещения для конференций','rooms'=>'Каталог помещений','register'=>'Регистрация','login'=>'Вход','dashboard'=>'Мои заявки','new'=>'Новая заявка','admin'=>'Панель администратора'];
?><!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title><?=e($titles[$route]??'Портал')?> — Конференции.РФ</title><link rel="icon" href="static/img/auditorium-neva.webp"><link rel="stylesheet" href="static/style.css"><script src="static/app.js" defer></script></head><body><a class="skip" href="#main">К содержанию</a><header><a class="brand" href="<?=url()?>">Конференции.РФ</a><nav aria-label="Главное меню"><a href="<?=url('rooms')?>">Помещения</a><?php if($user):?><a href="<?=url('dashboard')?>">Мои заявки</a><a href="<?=url('new')?>">Новая заявка</a><?php if($user['is_admin']):?><a href="<?=url('admin')?>">Администратор</a><?php endif?><form method="post" action="<?=url('logout')?>"><?=csrf()?><button class="plain">Выйти</button></form><?php else:?><a href="<?=url('login')?>">Вход</a><a class="button" href="<?=url('register')?>">Регистрация</a><?php endif?></nav></header><main id="main"><?php if(isset($_SESSION['flash'])):?><p class="notice" role="status"><?=e($_SESSION['flash'])?></p><?php unset($_SESSION['flash']);endif?>
<?php if($route==='home'||$route==='rooms'):
$conditions=[];$args=[];$category=is_string($_GET['category']??null)?$_GET['category']:'';
if(in_array($category,['auditorium','coworking','cinema'],true)){$conditions[]='category=?';$args[]=$category;}
$rooms=$db->query('SELECT * FROM rooms'.($conditions?' WHERE '.implode(' AND ',$conditions):'').' ORDER BY id',$args)->fetchAll();
?><?php if($route==='home'):?><section class="hero"><div><p class="eyebrow">ПРОСТРАНСТВА ДЛЯ ВАШИХ ИДЕЙ</p><h1>Место, где начинается ваша конференция</h1><p>Аудитории, коворкинги и кинозалы. Выберите площадку и отправьте заявку — все статусы доступны в личном кабинете.</p><a class="button" href="<?=url('new')?>">Выбрать и забронировать</a></div><img src="static/img/auditorium-neva.webp" alt="Светлая аудитория для конференции"></section><?php else:?><h1>Каталог помещений</h1><?php endif?>
<form class="filter" method="get"><input type="hidden" name="r" value="rooms"><label for="category">Формат</label><select id="category" name="category"><?php foreach([''=>'Все форматы','auditorium'=>'Аудитория','coworking'=>'Коворкинг','cinema'=>'Кинозал'] as $key=>$text):?><option value="<?=e($key)?>" <?=$key===$category?'selected':''?>><?=e($text)?></option><?php endforeach?></select><button>Найти</button></form><div class="grid"><?php foreach($rooms as $room):?><article class="card"><img loading="lazy" src="static/img/<?=e(basename($room['image']))?>" alt="<?=e($room['name'])?>"><div><p class="muted"><?=e($room['city'])?></p><h2><?=e($room['name'])?></h2><p><?=e($room['description'])?></p><p>До <?=e($room['capacity'])?> человек · <?=e($room['hourly_rate'])?> ₽/ч</p><p><?=e($room['address'])?></p><a class="button" href="<?=url('new')?>&amp;room=<?=e($room['id'])?>">Выбрать помещение</a></div></article><?php endforeach?></div>
<?php elseif($route==='register'||$route==='login'):?><section class="form-card"><h1><?=e($titles[$route])?></h1><form method="post" novalidate><?=csrf()?><?php field('username','Логин',$values,$errors);field('password','Пароль',$values,$errors,'password');if($route==='register'){field('confirm','Повторите пароль',$values,$errors,'password');field('full_name','ФИО',$values,$errors);field('phone','Телефон',$values,$errors,'tel','placeholder="8(900)123-45-67"');field('email','E-mail',$values,$errors,'email');}?><button><?=$route==='register'?'Зарегистрироваться':'Войти'?></button></form><p><a href="<?=url($route==='register'?'login':'register')?>"><?=$route==='register'?'Уже зарегистрированы? Вход':'Ещё не зарегистрированы? Регистрация'?></a></p></section>
<?php elseif($route==='new'):$rooms=$db->query('SELECT * FROM rooms ORDER BY name')->fetchAll();?><section class="form-card"><h1>Новая заявка</h1><p>Помещение, дата и оплата — по условию КИМ. Название, время и число участников уточняют заявку.</p><form method="post" novalidate><?=csrf()?><?php field('conference_name','Название конференции',$values,$errors);?><label for="room_id">Помещение</label><select id="room_id" name="room_id" required><?php foreach($rooms as $room):?><option value="<?=e($room['id'])?>" <?=(string)$room['id']===($values['room_id']??(string)($_GET['room']??''))?'selected':''?>><?=e($room['name'])?> · до <?=e($room['capacity'])?> человек</option><?php endforeach?></select><?php if(isset($errors['room_id'])):?><p class="error"><?=e($errors['room_id'])?></p><?php endif?><?php field('event_date','Дата',$values,$errors,'date');field('start_time','Время начала',$values,$errors,'time');field('attendees','Количество участников',$values,$errors,'number','min="1"');?><label for="payment_method">Способ оплаты</label><select id="payment_method" name="payment_method"><?php foreach($payments as $key=>$text):?><option value="<?=$key?>" <?=($values['payment_method']??'')===$key?'selected':''?>><?=e($text)?></option><?php endforeach?></select><?php if(isset($errors['payment_method'])):?><p class="error"><?=e($errors['payment_method'])?></p><?php endif?><button>Отправить заявку</button></form></section>
<?php elseif($route==='dashboard'||$route==='admin'):
$sql='SELECT a.*,r.name AS room_name,u.full_name,rv.comment,rv.rating FROM applications a JOIN rooms r ON r.id=a.room_id JOIN users u ON u.id=a.user_id LEFT JOIN reviews rv ON rv.application_id=a.id';$args=[];$where=[];
if($route==='dashboard'){$where[]='a.user_id=?';$args[]=$user['id'];}
$filter=is_string($_GET['status']??null)?$_GET['status']:'';$search=is_string($_GET['q']??null)?mb_substr($_GET['q'],0,120):'';
if($route==='admin'&&isset($statusLabels[$filter])){$where[]='a.status=?';$args[]=$filter;}
if($route==='admin'&&$search!==''){$where[]='(a.conference_name LIKE ? OR u.full_name LIKE ?)';$args[]='%'.$search.'%';$args[]='%'.$search.'%';}
$apps=$db->query($sql.($where?' WHERE '.implode(' AND ',$where):'').' ORDER BY a.id DESC',$args)->fetchAll();
?><h1><?=e($titles[$route])?></h1><?php if($route==='admin'):?><form class="filter" method="get"><input type="hidden" name="r" value="admin"><label for="q">Название или ФИО</label><input id="q" name="q" value="<?=e($search)?>"><label for="status">Статус</label><select id="status" name="status"><option value="">Все</option><?php foreach($statusLabels as $key=>$text):?><option value="<?=$key?>" <?=$filter===$key?'selected':''?>><?=e($text)?></option><?php endforeach?></select><button>Применить</button></form><?php else:?><a class="button" href="<?=url('new')?>">Создать заявку</a><?php endif?><?php if(!$apps):?><p class="notice">Заявок пока нет или они не соответствуют фильтру.</p><?php endif?><div class="grid"><?php foreach($apps as $a):?><article class="card application"><span class="badge"><?=e($statusLabels[$a['status']])?></span><h2>№<?=e($a['id'])?> · <?=e($a['conference_name'])?></h2><p><?=e($a['room_name'])?></p><p><?=e($a['event_date'])?> · <?=e($a['start_time'])?> · <?=e($a['attendees'])?> участников</p><p><?=e($payments[$a['payment_method']])?></p><?php if($route==='admin'):?><p><?=e($a['full_name'])?></p><form method="post" action="<?=url('status')?>"><?=csrf()?><input type="hidden" name="id" value="<?=e($a['id'])?>"><label for="status-<?=e($a['id'])?>">Новый статус</label><select id="status-<?=e($a['id'])?>" name="status"><?php foreach($statusLabels as $key=>$text):?><option value="<?=$key?>" <?=$a['status']===$key?'selected':''?>><?=e($text)?></option><?php endforeach?></select><button>Сохранить статус</button></form><?php elseif($a['comment']!==null):?><h3>Ваш отзыв · <?=e($a['rating'])?> / 5</h3><p><?=e($a['comment'])?></p><?php elseif($a['status']==='completed'):?><form method="post" action="<?=url('review')?>"><?=csrf()?><input type="hidden" name="id" value="<?=e($a['id'])?>"><label for="rating-<?=e($a['id'])?>">Оценка</label><select id="rating-<?=e($a['id'])?>" name="rating"><?php for($n=5;$n>0;$n--):?><option><?=$n?></option><?php endfor?></select><label for="comment-<?=e($a['id'])?>">Отзыв</label><textarea id="comment-<?=e($a['id'])?>" name="comment" required minlength="10" maxlength="500"></textarea><button>Оставить отзыв</button></form><?php else:?><p class="muted">Отзыв доступен после завершения мероприятия.</p><?php endif?></article><?php endforeach?></div>
<?php endif?></main><footer>Конференции.РФ · Учебный пример PHP + MySQL · ДЭ БУ 2027</footer></body></html>
