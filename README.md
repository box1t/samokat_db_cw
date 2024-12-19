## Инструкция по запуску проекта

1. Находясь в папке проекта, введи в терминале IDE следующие команды:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# deactivate
```

2. В папке app создай .env файл и заполни его своими переменными окружения:

```sh
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=mysecretpassword
DB_NAME=scooters
```


3. Запусти __**docker-container с postgres**__ и подключись к серверу через клиент __**psql**__:



- Если контейнер существует:
```sh
docker start my_postgres
psql -h localhost -p 5432 -U postgres -d scooters
```

- Если БД только создана, в psql необходимо заполнить её тестовыми данными:
```sh
CREATE DATABASE NEW;
\c NEW
\l
```

- Очистка всей бд:
```sh
DO $$ DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

```

- Если ошибка "Address already in use"
```sh
sudo lsof -i :5000
kill -9 PID
```

- Если контейнер не существует:
- Теги: имя контейнера, порт, extend, версия docker-образа

```sh
docker run --name my_postgres -p 5432:5432 -e POSTGRES_PASSWORD=mysecretpassword -d postgres
docker ps -a
```


- Если что-то пошло не так:

```sh
docker stop my_postgres
docker rm my_postgres
docker ps -a
```


```sh
\l  # чтобы проверить доступные базы данных
\du # чтобы проверить доступных пользователей
```

- Для работы с postgres напрямую
```sh
sudo systemctl status postgresql
sudo systemctl start postgresql
```


4. Запусти **main.py** файл для теста веб-приложения.


5. Введи эту команду в терминале (или CTRL + ПКМ на ссылку хоста в IDE):


```sh

curl http://127.0.0.1:5000

```
## Тестирование функционала

1. Проверить асинхронность работы фреймворка этой командой (или через другой клиент браузера - через другого пользователя):

```sh

wrk -t10 -c100 -d30s http://127.0.0.1:5000/long

```

Команда запустит 100 параллельных процессов, каждый с задержкой в 10 секунд. 


2. Протестируй следующие routes в адресной строке:

- http://127.0.0.1:5000/login
- http://127.0.0.1:5000/register
- http://127.0.0.1:5000/cart
- http://127.0.0.1:5000/profile
- http://127.0.0.1:5000/admin
- http://127.0.0.1:5000/logout
- http://127.0.0.1:5000/short
- http://127.0.0.1:5000/long


