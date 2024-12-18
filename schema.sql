CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE roles (
    role_id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) NOT NULL,
    hashed_password TEXT NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_roles FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE CASCADE
);

CREATE TABLE locations (
    location_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL
);

CREATE TABLE scooters (
    scooter_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model VARCHAR(150) NOT NULL, -- Название модели
    battery_level INT NOT NULL CHECK (battery_level >= 0 AND battery_level <= 100), -- Уровень заряда
    battery_consumption NUMERIC(5, 2) DEFAULT 1.5, -- Расход заряда на км
    speed_limit NUMERIC(4, 2) DEFAULT 20.0, -- Максимальная скорость самоката 
    location_id UUID, -- Локация, где находится самокат
    status VARCHAR(50) DEFAULT 'available', -- Статус самоката ('available', 'reserved', 'in_use', 'maintenance')
    last_maintenance_date TIMESTAMP, -- Последнее обслуживание
    CONSTRAINT fk_scooters_locations FOREIGN KEY (location_id) REFERENCES locations(location_id) ON DELETE SET NULL
);

CREATE TABLE rentals (
    rental_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    scooter_id UUID NOT NULL,
    start_location_id UUID NOT NULL,
    end_location_id UUID, -- конечная локация
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    price_per_minute NUMERIC(10, 2) NOT NULL, -- Тариф аренды
    total_price NUMERIC(10, 2),
    distance_km NUMERIC(10, 2) DEFAULT 0.0,
    remaining_battery INT;
    status VARCHAR(50) DEFAULT 'active', -- Состояние поездки
    CONSTRAINT fk_rentals_start_location FOREIGN KEY (start_location_id) REFERENCES locations(location_id),
    CONSTRAINT fk_rentals_end_location FOREIGN KEY (end_location_id) REFERENCES locations(location_id),
    CONSTRAINT fk_rentals_scooter FOREIGN KEY (scooter_id) REFERENCES scooters(scooter_id),
    CONSTRAINT fk_rentals_user FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE rental_history (
    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL,
    user_id UUID NOT NULL,
    scooter_id UUID NOT NULL,
    start_location_id UUID NOT NULL,
    end_location_id UUID,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    total_price NUMERIC(10, 2),
    status VARCHAR(50),
    change_date TIMESTAMP DEFAULT NOW(), -- дата изменения
    summary TEXT, -- Краткий итог поездки
    ride_comment TEXT, -- Отзыв пользователя о поездке
    rating INT CHECK (rating >= 1 AND rating <= 5), -- Оценка (1-5)
    CONSTRAINT fk_rental_history_rentals FOREIGN KEY (rental_id) REFERENCES rentals(rental_id) ON DELETE CASCADE
);

CREATE TABLE reviews (
    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL, -- Привязка к аренде
    scooter_id UUID NOT NULL, -- Привязка к самокату
    user_id UUID NOT NULL, -- Привязка к пользователю
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5), -- Оценка от 1 до 5
    review_text TEXT, -- Текст отзыва (опционально)
    review_date TIMESTAMP DEFAULT NOW(), -- Дата создания отзыва
    CONSTRAINT fk_reviews_rentals FOREIGN KEY (rental_id) REFERENCES rental_history(history_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_scooters FOREIGN KEY (scooter_id) REFERENCES scooters(scooter_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);


---1. Представления
---2. Функции
---3. Процедуры
---4. Триггеры


CREATE OR REPLACE FUNCTION get_average_scooter_rating(scooter_id_param UUID)
RETURNS NUMERIC(3, 2) AS $$
BEGIN
    RETURN (
        SELECT COALESCE(AVG(rating), 0) -- Возвращает 0, если отзывов нет
        FROM reviews
        WHERE scooter_id = scooter_id_param
    );
END;
$$ LANGUAGE plpgsql;





CREATE OR REPLACE FUNCTION log_rental_history()
RETURNS TRIGGER AS $$
DECLARE
    history_id UUID := uuid_generate_v4();
    summary_text TEXT;
BEGIN
    -- Автоматическое формирование summary 
    summary_text := FORMAT(
        'Самокат %s. Поездка с %s до %s. Начало: %s, Конец: %s. Стоимость: %.2f ₽.',
        NEW.scooter_id,
        NEW.start_time,
        NEW.end_time,
        NEW.start_location_id,
        NEW.end_location_id,
        NEW.total_price
    );

    -- Вставка записи в rental_history
    INSERT INTO rental_history (
        history_id, rental_id, user_id, scooter_id, start_location_id,
        end_location_id, start_time, end_time, total_price, status, change_date, summary, review
    )
    VALUES (
        history_id, NEW.rental_id, NEW.user_id, NEW.scooter_id, NEW.start_location_id,
        NEW.end_location_id, NEW.start_time, NEW.end_time, NEW.total_price, 
        NEW.status, NOW(), summary_text, NULL -- review остаётся NULL по умолчанию
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для вставки завершённых поездок
CREATE TRIGGER rental_history_trigger
AFTER UPDATE OF status ON rentals
FOR EACH ROW
WHEN (NEW.status = 'completed')
EXECUTE FUNCTION log_rental_history();
