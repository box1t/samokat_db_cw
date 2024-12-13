-- Создание расширений
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Таблица roles
CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

-- Таблица users
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) NOT NULL,
    hashed_password TEXT NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL
);

-- Таблица user_roles
CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_roles FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE
);

-- Таблица categories
-- CREATE TABLE categories (
--     category_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     name VARCHAR(100) NOT NULL
-- );
----------------------


-- Таблица locations вместо categories
CREATE TABLE locations (
    location_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL
);

-- 1. не name, а location_name
-- 2. Как это будет встроено в бизнес-логику? 
-- 3. если длительность дальше, чем 1 километр, не показывать? нет. это значит, относим к такому-то району? 
-- 4. Я нажимаю арендовать, оно показывает координаты. А как фиксируется старт поездки?
-- 5. Есть период ожидания. Бизнес-логика в том, чтобы забронировать, а затем начать поездку. После начала поездки все идет.
-- 6. Есть несколько статусов. У заказа - статус pending. У самоката - статус pending, затем riding, когда поездка началась.
-- 7. Эта логика была прописана в админке управления заказами.
-- 8. Здесь админка будет в чем? 
-- 9. Админ может добавить самокаты? Или починить? и это аналог чему? добавлению категорий. Только там влияли на количество, тут же влияем на кол-во и на процент зарядки.
-- 10. Получается, имя локации динамично? У самоката меняется имя локациии и координаты? Корректен ли тип данных? А изменение динамически во время поездки происходит? 
-- 11. Является ли это частью бизнес-логики: выявление имени локации, координат, и обновление данных в таблице? Это куча запросов!


-- Таблица products
-- CREATE TABLE products (
--     product_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     name VARCHAR(150) NOT NULL,
--     description TEXT,
--     category_id UUID,
--     price NUMERIC(10, 2) NOT NULL,
--     stock INT NOT NULL,
--     manufacturer VARCHAR(150),
--     CONSTRAINT fk_products_categories FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE SET NULL
-- );


-- Таблица scooters
CREATE TABLE scooters (
    scooter_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model VARCHAR(150) NOT NULL, -- Название модели
    battery_level INT NOT NULL CHECK (battery_level >= 0 AND battery_level <= 100), -- Уровень заряда
    location_id UUID, -- Локация, где находится самокат
    is_available BOOLEAN DEFAULT TRUE, -- Доступен для аренды
    last_maintenance_date TIMESTAMP, -- Последнее обслуживание
    status VARCHAR(50) DEFAULT 'available', -- Статус: available, maintenance_needed, etc.
    CONSTRAINT fk_scooters_locations FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE SET NULL
);



-- -- Таблица cart
-- CREATE TABLE cart (
--     user_id UUID NOT NULL,
--     product_id UUID NOT NULL,
--     quantity INT NOT NULL,
--     PRIMARY KEY (user_id, product_id),
--     CONSTRAINT cart_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
--     CONSTRAINT cart_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
-- );


-- Таблица rentals вместо orders, cart просто не будет (спорно. сейчас это таблица Зарезервированные самокаты. а зачем нам это? нам нужны только доступные)
--CREATE TABLE old_rentals (
--     rental_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     user_id UUID NOT NULL,
--     scooter_id UUID NOT NULL,
--     start_time TIMESTAMP DEFAULT NOW(),
--     end_time TIMESTAMP,
--     rate_id INT NOT NULL,
--     total_price NUMERIC(10, 2),
--     CONSTRAINT fk_rentals_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
--     CONSTRAINT fk_rentals_scooters FOREIGN KEY (scooter_id) REFERENCES scooters(scooter_id) ON DELETE CASCADE
-- );

-- 1. Orders отображались в личном кабинете пользователя. А теперь главная страница это что? а тогда что? тогда это были order-items? а сейчас это тарифы? Что мы усложнили?
-- 2. При клике на локацию или на что-то я получу список самокатов, а на самокате есть возможность выбрать тариф?  
-- 3. почему недостаточно одного тарифа, но расчет по минутам?
-- 4. Бизнес-логика rentals просто в том, чтобы считать время, когда старт и начало? а это не делает сама бд? а как в питоне это сделал егор?
-- 5. Почему rate_id в rentals это int not null, а в rates это serial primary key?
-- 6. rentals с чем будет связана по аналогии с orders?

-- новый вариант
CREATE TABLE rentals (
    rental_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    scooter_id UUID NOT NULL,
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    price_per_minute NUMERIC(10, 2) NOT NULL, -- Тариф аренды
    total_price NUMERIC(10, 2)
);


-- -- Таблица orders
-- CREATE TABLE orders (
--    order_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--    user_id UUID NOT NULL,
--    order_date TIMESTAMP DEFAULT NOW(),
--    status VARCHAR(50) NOT NULL,
--    total_cost NUMERIC(10, 2) NOT NULL,
--    CONSTRAINT fk_orders_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
--);


---- Таблица order_items
--CREATE TABLE order_items (
--    order_id UUID NOT NULL,
--    product_id UUID NOT NULL,
--    quantity INT NOT NULL,
--    price NUMERIC(10, 2) NOT NULL,
--    PRIMARY KEY (order_id, product_id),
--    CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
--    CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
--);


-- 1. Что означают 2 последние строки в order_items?


---- Таблица rates вместо order_items
--CREATE TABLE rates (
--    rate_id SERIAL PRIMARY KEY,
--    name VARCHAR(50) NOT NULL,
--    price_per_minute NUMERIC(10, 2) NOT NULL
--);

-- отказался от тарифов

-- 1. Она менее полна чем order_items. Чем определяются полнота, наполнение таблиц? 
-- 2. Непонятно, что за name. Может, это rate_name?
-- 3. Почему серийный первичный ключ? 
-- 4. Почему не нужны constraint?
-- 5. С какой таблицей будет связь у rates (тарифов)? - с самокатами? с активными арендами, а активные аренды - уже с самокатами?


---- Таблица order_history
--CREATE TABLE order_history (
--    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--    order_id UUID NOT NULL,
--    status VARCHAR(50) NOT NULL,
--    change_date TIMESTAMP DEFAULT NOW(),
--    CONSTRAINT fk_order_history_orders FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
--);

-- 1. какие были доступны статусы в order_history
-- 2. что за change date?



-- Таблица rental_history вместо order_history
CREATE TABLE rental_history (
    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL,
    completion_date TIMESTAMP DEFAULT NOW(),
    summary TEXT,
    CONSTRAINT fk_rental_history_rentals FOREIGN KEY (rental_id) REFERENCES rentals(rental_id) ON DELETE CASCADE
);

-- 1. Чем summary отличается от reviews? 
-- 2. На что review делаем? На поездку? Самокат?


-- Таблица reviews
--CREATE TABLE reviews (
--    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--    product_id UUID NOT NULL,
--    user_id UUID NOT NULL,
--    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
--    comment TEXT,
--    review_date TIMESTAMP DEFAULT NOW(),
--    CONSTRAINT fk_reviews_products FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
--    CONSTRAINT fk_reviews_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
--);

-- Таблица reviews вместо reviews
CREATE TABLE reviews (
    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scooter_id UUID NOT NULL,
    user_id UUID NOT NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    review_date TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_reviews_scooters FOREIGN KEY (scooter_id) REFERENCES scooters(scooter_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- нужно ли summary и comment???


-- Заполнение таблиц тестовыми данными
INSERT INTO roles (name) VALUES ('User'), ('Admin');


-- 1. процедурка. это основная бизнес-логика. подумать надо. продумать краевые случаи. 
-- 2. Когда срабатывает процедурка? только на этапе заполнения таблиц скриптом?
-- 3. нужно ли несколько процедур? а как админовские процедуры сделаны? 
-- 4. почему админ работа не требует процедур?
-- 5. Процедура идет последовательно? Удаление по окончании процедуры? но если пользователь решил ничего не удалять? ну почему же. 
-- Если он выбрал в корзине оплатить, процедура завершена. а как это поняли?
-- то есть если один из критериев процедуры выполнился, идем на следующий этап процедуры? ведь сценарий продуман?


-- как поняли, что для обработки заказа нужна именно процедура? видимо, и мне нужна. потому что она максимально нестандартна? использует максимально шаблонные функции?

CREATE OR REPLACE PROCEDURE process_user_order(uid UUID)
LANGUAGE plpgsql
AS $$
DECLARE
    cart_item RECORD;
    total_cost NUMERIC := 0;
    order_id UUID := uuid_generate_v4();
BEGIN
    -- Получаем товары из корзины
    FOR cart_item IN
        SELECT product_id, quantity, price, stock
        FROM cart_details
        WHERE user_id = uid
    LOOP
        -- Проверяем наличие на складе
        IF cart_item.quantity > cart_item.stock THEN
            RAISE EXCEPTION 'Недостаточно товара на складе для продукта %', cart_item.product_id;
        END IF;
        -- Считаем итоговую стоимость
        total_cost := total_cost + (cart_item.price * cart_item.quantity);
    END LOOP;

    IF total_cost = 0 THEN
        RAISE EXCEPTION 'Корзина пуста.';
    END IF;

    -- Создаем новый заказ
    INSERT INTO orders (order_id, user_id, total_cost, order_date, status)
    VALUES (order_id, uid, total_cost, NOW(), 'Pending');

    -- Добавляем товары из корзины в order_items и обновляем остатки
    FOR cart_item IN
        SELECT product_id, quantity, price, stock
        FROM cart_details
        WHERE user_id = uid
    LOOP
        INSERT INTO order_items (order_id, product_id, quantity, price)
        VALUES (order_id, cart_item.product_id, cart_item.quantity, cart_item.price);

        UPDATE products SET stock = stock - cart_item.quantity WHERE product_id = cart_item.product_id;
    END LOOP;

    -- Очищаем корзину пользователя
    DELETE FROM cart WHERE user_id = uid;
END;
$$;


-- ок, оставим
CREATE OR REPLACE FUNCTION get_average_product_rating(product_id UUID)
RETURNS NUMERIC AS $$
BEGIN
    RETURN (SELECT AVG(rating)::NUMERIC FROM reviews WHERE product_id = product_id);
END;
$$ LANGUAGE plpgsql;



-- ок, оставим. это таблица уже заполнена по тригеру. это часть бизнес-логики? или для этого не нужна бизнес-логика? поэтому и не нужны отзывы там!!
-- очень умный ход - историю ЛОГИРОВАТЬ.
-- как до этого додуматься? промпт "сделай МВП"? минимум избыточности?


CREATE OR REPLACE FUNCTION log_order_history()
RETURNS TRIGGER AS $$
DECLARE
    history_id UUID := uuid_generate_v4();
BEGIN
    INSERT INTO order_history (history_id, order_id, status, change_date)
    VALUES (history_id, NEW.order_id, NEW.status, NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- повторяется? это ок?
CREATE OR REPLACE FUNCTION log_order_history()
RETURNS TRIGGER AS $$
DECLARE
    history_id UUID := uuid_generate_v4();
BEGIN
    INSERT INTO order_history (history_id, order_id, status, change_date)
    VALUES (history_id, NEW.order_id, NEW.status, NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ок?
CREATE TRIGGER order_history_trigger
   AFTER INSERT OR UPDATE ON orders
   FOR EACH ROW
   EXECUTE FUNCTION log_order_history();


-- тут подумаю. 1. как используется в коде?
-- какую вьюшку сделать мне, если нет корзины?
-- что-то с локациями связать? или, может, ...... определение понять?


-- возможно, это же будет, но к деталям каждой поездки. здесь корзина это шаг минус 1 до заказа. но у нас заказ будет таким.?
-- или это будет каждая секунда во время поездки? результат обновления поездки?
-- она будет объединять данные по локации, самокату, аренде ?
-- чем она будет отличаться от процедуры обработки заказа?
-- но там была связь с корзиной, а здесь её нет.




CREATE OR REPLACE VIEW cart_details AS
SELECT 
    c.user_id,
    c.product_id,
    p.name,
    p.description,
    p.price,
    p.stock,
    c.quantity,
    (p.price * c.quantity) AS total_cost
FROM cart c
JOIN products p ON c.product_id = p.product_id;



