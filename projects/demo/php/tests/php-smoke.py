"""HTTP integration check. Creates synthetic test users/applications in the selected local PHP demo."""
import os,re,time,urllib.request,urllib.parse,urllib.error,http.cookiejar
from datetime import date,timedelta
BASE=os.environ.get('PHP_BASE','http://127.0.0.1/conference-rvpm-2027/index.php')
def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(c,route,values=None):
    try:
        r=c.open(BASE+'?r='+route,None if values is None else urllib.parse.urlencode(values).encode());return r.status,r.read().decode()
    except urllib.error.HTTPError as e:return e.code,e.read().decode()
def post(c,route,values,form=None):
    status,html=request(c,form or route);assert status==200,(route,status)
    token=re.search(r'name="csrf" value="([^"]+)"',html);assert token,route
    return request(c,route,{'csrf':token[1],**values})
def login(c,name,password):return post(c,'login',{'username':name,'password':password})
user=client();admin=client();other=client();suffix=str(time.time_ns())[-12:];name='student'+suffix
assert request(user,'home')[0]==200
assert request(user,'rooms')[0]==200
assert request(user,'register',{'username':'bad'})[0]==400
bad=post(user,'register',{'username':'x','password':'short','confirm':'x','full_name':'Ivan','phone':'0','email':'bad'})
assert 'Латиница и цифры' in bad[1] and 'Формат:' in bad[1]
data={'username':name,'password':'ExamplePass8','confirm':'ExamplePass8','full_name':'Тестовый Пользователь','phone':'8(900)123-45-67','email':name+'@example.test'}
assert 'Профиль создан' in post(user,'register',data)[1]
assert 'уже используется' in post(user,'register',data)[1]
assert 'Неверный логин' in login(user,name,'wrong')[1]
assert 'Мои заявки' in login(user,name,'ExamplePass8')[1]
assert request(user,'admin')[0]==403
title='Проверка '+suffix
data={'conference_name':title,'room_id':'1','event_date':(date.today()+timedelta(days=30)).isoformat(),'start_time':'12:00','attendees':'10','payment_method':'sbp'}
assert 'Дата' in post(user,'new',{**data,'event_date':'2027-02-30'})[1]
status,html=post(user,'new',data);assert status==200 and 'Заявка отправлена' in html
match=re.search(r'№(\d+) · '+title,html);assert match;ident=match[1]
assert post(user,'review',{'id':ident,'rating':'5','comment':'Проверка раннего отзыва'},'dashboard')[0]==403
othername='other'+suffix
post(other,'register',{'username':othername,'password':'ExamplePass8','confirm':'ExamplePass8','full_name':'Другой Пользователь','phone':'8(900)123-45-67','email':othername+'@example.test'})
login(other,othername,'ExamplePass8');assert title not in request(other,'dashboard')[1]
assert post(other,'review',{'id':ident,'rating':'5','comment':'Проверка чужой заявки'},'dashboard')[0]==404
assert 'Панель администратора' in login(admin,'Conf2027','Demo77')[1]
assert post(admin,'status',{'id':ident,'status':'scheduled'},'admin')[0]==200
assert 'Мероприятие назначено' in request(user,'dashboard')[1]
post(admin,'status',{'id':ident,'status':'completed'},'admin')
assert 'Оставить отзыв' in request(user,'dashboard')[1]
review={'id':ident,'rating':'5','comment':'Учебная проверка завершённого мероприятия.'}
assert 'Отзыв опубликован' in post(user,'review',review,'dashboard')[1]
assert 'Отзыв уже существует' in post(user,'review',review,'dashboard')[1]
assert request(user,'status',{'csrf':'invalid','id':ident,'status':'new'})[0]==403
assert request(user,'logout')[0]==405
print('PHP HTTP smoke passed: registration, validation, duplicates, auth, CSRF, ownership, booking, status and review.')
