<?php
declare(strict_types=1);
// Initialization is CLI-only and refuses to change a nonempty database.
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require __DIR__.'/lib.php';
$db=new Database();
if($db->query('SHOW TABLES')->fetch()){fwrite(STDERR,"База не пуста. Создайте отдельную пустую базу.\n");exit(1);}
foreach(explode(';',file_get_contents(__DIR__.'/schema.sql')) as $sql)if(trim($sql)!=='')$db->query($sql);
$db->query('INSERT INTO users(username,password_hash,full_name,phone,email,is_admin) VALUES(?,?,?,?,?,1)',['Conf2027',password_hash('Demo77',PASSWORD_DEFAULT),'Администратор Портала','8(800)000-00-00','admin@conference.test']);
$catalogue=json_decode(file_get_contents(__DIR__.'/rooms.json'),true,512,JSON_THROW_ON_ERROR);
foreach($catalogue as $room){unset($room['id']);$columns=array_keys($room);$db->query('INSERT INTO rooms('.implode(',',$columns).') VALUES('.implode(',',array_fill(0,count($room),'?')).')',array_values($room));}
echo "Созданы таблицы, ".count($catalogue)." помещений и учебный администратор Conf2027.\n";
