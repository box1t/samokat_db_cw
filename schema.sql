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

-- Таблица locations вместо categories
CREATE TABLE locations (
    location_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL
);

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

-- Таблица rentals
CREATE TABLE rentals (
    rental_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    scooter_id UUID NOT NULL,
    location_id UUID NOT NULL,
    start_time TIMESTAMP DEFAULT NOW(),
    end_time TIMESTAMP,
    price_per_minute NUMERIC(10, 2) NOT NULL, -- Тариф аренды
    total_price NUMERIC(10, 2)
);

-- Таблица rental_history
CREATE TABLE rental_history (
    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL,
    user_id UUID NOT NULL,
    completion_date TIMESTAMP DEFAULT NOW(),
    duration INTERVAL NOT NULL,
    total_price NUMERIC(10, 2) NOT NULL,
    summary TEXT,
    CONSTRAINT fk_rental_history_rentals FOREIGN KEY (rental_id) REFERENCES rentals(rental_id) ON DELETE CASCADE,
    CONSTRAINT fk_rental_history_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);


--------------------------------------------------
---------------какую выбрать?---------------------
--------------------------------------------------
--------------------------------------------------
CREATE TABLE rental_history (
    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL,
    completion_date TIMESTAMP DEFAULT NOW(),
    duration INTERVAL NOT NULL,
    CONSTRAINT fk_rental_history_rentals FOREIGN KEY (rental_id) REFERENCES rentals(rental_id) ON DELETE CASCADE
);


CREATE TABLE rental_history (
    history_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL,
    completion_date TIMESTAMP DEFAULT NOW(),
    duration INTERVAL NOT NULL,
    summary TEXT,
    CONSTRAINT fk_rental_history_rentals FOREIGN KEY (rental_id) REFERENCES rentals(rental_id) ON DELETE CASCADE
);
--------------------------------------------------
---------------какую выбрать?---------------------
--------------------------------------------------
--------------------------------------------------
-- в истории комментарий не нужен, ибо это создаётся по триггеру


-- Таблица reviews
CREATE TABLE reviews (
    review_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rental_id UUID NOT NULL, -- Привязка к аренде
    scooter_id UUID NOT NULL, -- Привязка к самокату
    user_id UUID NOT NULL, -- Привязка к пользователю
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5), -- Оценка от 1 до 5
    comment TEXT, -- Текст отзыва (опционально)
    review_date TIMESTAMP DEFAULT NOW(), -- Дата создания отзыва
    CONSTRAINT fk_reviews_rentals FOREIGN KEY (rental_id) REFERENCES rental_history(history_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_scooters FOREIGN KEY (scooter_id) REFERENCES scooters(scooter_id) ON DELETE CASCADE,
    CONSTRAINT fk_reviews_users FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
-- в отзыве комментарий нужен.
-- нужно ли summary и коммент? где этот функционал будет автоматический?


---1. Представления
---2. Функции
---3. Процедуры
---4. Триггеры

