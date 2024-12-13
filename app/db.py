import asyncpg
import uuid
import bcrypt
import logging

logger = logging.getLogger(__name__)



######################################################################
                            #Roles
######################################################################


async def get_role_id_by_name(pool: asyncpg.pool.Pool, role_name: str) -> int:
    """
    Получить ID роли по её имени.
    """
    async with pool.acquire() as conn:
        role_id = await conn.fetchval("""
            SELECT role_id FROM roles WHERE name = $1
        """, role_name)
        if not role_id:
            logger.error(f"Роль с именем {role_name} не найдена.")
        return role_id

async def get_user_roles(pool: asyncpg.pool.Pool, user_id: str):
    """
    Получить список ролей пользователя.
    """
    async with pool.acquire() as conn:
        roles = await conn.fetch("""
            SELECT r.name
            FROM user_roles ur
            JOIN roles r ON ur.role_id = r.role_id
            WHERE ur.user_id = $1
        """, user_id)
        return [role['name'] for role in roles]

async def get_user_by_id(pool: asyncpg.pool.Pool, user_id: str):
    """
    Получить информацию о пользователе по user_id.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT username, email
            FROM users
            WHERE user_id = $1
        """, user_id)

async def create_user(pool: asyncpg.pool.Pool, username: str, hashed_password: str, email: str):
    """
    Создать нового пользователя и вернуть его user_id.
    """
    user_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, hashed_password, email)
            VALUES ($1, $2, $3, $4)
        """, user_id, username, hashed_password, email)

        role_id = await get_role_id_by_name(pool, "User")
        await conn.execute("""
            INSERT INTO user_roles (user_id, role_id)
            VALUES ($1, $2)
        """, user_id, role_id)
    return user_id

async def get_user_by_email(pool: asyncpg.pool.Pool, email: str):
    """
    Получить пользователя по email.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM users WHERE email = $1
        """, email)

### 1. Добавить админа при холодном старте

######################################################################
                            #Products - scooters
######################################################################

"""
0. Пойми, с чем взаимодействуют самокаты.
1. Копируй в гпт.
2. Получи это + измененное что-то на основе модели данных.



5. Взял связанные таблицы, относящиеся к данному классу. И проектируешь всю логику. Сначала меняешь подобные, затем добавляешь ещё.
Как должен выглядеть результат? Сложно это описать?

Страница, где тото тото.

Вот и "сделай под это логику".

6. Где хранятся статусы заказа?

"""

async def get_all_products(pool):
    """
    Получить список всех продуктов.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT product_id, name, description, price, stock, manufacturer
            FROM products
        """)

async def get_product_by_id(pool: asyncpg.pool.Pool, product_id: str):
    """
    Получить информацию о продукте по его ID.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM products WHERE product_id = $1
        """, product_id)

async def add_product(pool, name, description, price, stock, manufacturer, category_id=None):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO products (product_id, name, description, price, stock, manufacturer, category_id)
            VALUES (uuid_generate_v4(), $1, $2, $3, $4, $5, $6)
        """, name, description, price, stock, manufacturer, category_id)

async def update_product(pool, product_id, name, description, price, stock, manufacturer, category_id=None):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE products
            SET name = $1, description = $2, price = $3, stock = $4, manufacturer = $5, category_id = $6
            WHERE product_id = $7
        """, name, description, price, stock, manufacturer, category_id, product_id)

async def delete_product(pool, product_id):
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM products WHERE product_id = $1
        """, product_id)

## Заменится на что? Что делает этот запрос? продукт МБ без категории? Самокат без локации? Кажется, сама модель данных это устранит
## Это нужно для админ панели. зачем-то.. в каком виде это выводится админу на фронте? а в цифрах?

async def get_all_products_with_categories(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT p.*, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            ORDER BY p.name
        """)


async def get_product_by_id(pool: asyncpg.pool.Pool, product_id: str):
    """
    Получить информацию о продукте по его ID.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM products WHERE product_id = $1
        """, product_id)

## По каким критериям будем искать самокат?

async def search_products(pool: asyncpg.pool.Pool, query: str = '', category_id: str = '', manufacturer: str = ''):
    """
    Поиск товаров по названию, описанию, категории и производителю.
    """
    async with pool.acquire() as conn:
        sql = """
            SELECT p.product_id, p.name, p.description, p.price, p.stock, p.manufacturer, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.category_id
            WHERE TRUE
        """
        params = []
        param_index = 1

        if query:
            sql += f" AND (p.name ILIKE '%' || ${param_index} || '%' OR p.description ILIKE '%' || ${param_index} || '%')"
            params.append(query)
            param_index += 1

        if category_id:
            sql += f" AND p.category_id = ${param_index}"
            params.append(category_id)
            param_index += 1

        if manufacturer:
            sql += f" AND p.manufacturer = ${param_index}"
            params.append(manufacturer)
            param_index += 1

        sql += " ORDER BY p.name"

        return await conn.fetch(sql, *params)

## А тут? Список моделей?
async def get_all_manufacturers(pool: asyncpg.pool.Pool):
    """
    Получить список всех производителей.
    """
    async with pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT DISTINCT manufacturer
            FROM products
            WHERE manufacturer IS NOT NULL AND manufacturer != ''
            ORDER BY manufacturer
        """)
        # Преобразуем список записей в список строк
        return [record['manufacturer'] for record in records]


######################################################################
                            #Categories - locations. Основа бизнес-логики
######################################################################

"""

0. Пойми, с чем взаимодействуют локации.
1. Копируй в гпт.
2. Получи это + измененное что-то на основе модели данных.
3. Здесь будет объемно, т.к. на локации завязан фильтр на фронте. Отдельная страница. Первая пагинация - локации, вторая - самокаты.
или нет смысла что-то менять?

4. пагинация это часть логики бд или чья? страницы? в routes?




5. Взял связанные таблицы, относящиеся к данному классу. И проектируешь всю логику. Сначала меняешь подобные, затем добавляешь ещё.
Как должен выглядеть результат? Сложно это описать?

Страница, где тото тото.

Вот и "сделай под это логику".


"""

#////////////////////////////////////////////////////////////
# 1. Получить список доступных самокатов в локации
"""
SELECT scooter_id, model, battery_level, last_location
FROM Scooters
WHERE is_available = TRUE
AND last_location = %s;



SELECT *
FROM scooters
WHERE location_id = '123-location-id'
AND is_available = TRUE;



"""

# 2. Аренда: Создать запись и Обновить доступность самоката
"""
INSERT INTO Rentals (user_id, scooter_id, start_time)
VALUES (%s, %s, NOW());


UPDATE Scooters
SET is_available = FALSE
WHERE scooter_id = %s;

"""

# 3. Список всех категорий

"""
SELECT category_id, name
FROM categories;

"""

# 4. Вывод популярных товаров

"""
SELECT product_id, name, description, price, stock, manufacturer
FROM products
WHERE stock > 0
ORDER BY stock DESC -- По количеству на складе (популярность)
LIMIT 10;

"""

# 5. Фильтр по категории

"""
SELECT product_id, name, description, price, stock, manufacturer
FROM products
WHERE category_id = 'selected-category-id' AND stock > 0;

"""

# 6. Список доступных самокатов на локации

"""
SELECT scooter_id, model, battery_level, location_id
FROM scooters
WHERE is_available = TRUE;

"""


# 7. Список локаций
"""
SELECT location_id, name, latitude, longitude
FROM locations;

"""



# 3. Главная страница: сортировка по локации (это как: близость ко мне?)
# 4. Сортировка по числу самокатов
# 5. Сортировка по заряду самокатов
# 6. Сложный фильтр (1 и 2) - но это просто join? Но в нем нет смысла, поэтому по локации и по числу ближних рядом.
# 7. Кнопка перехода в профиль. Что будет в профиле? Там одна лишняя кнопка. Но что еще будет? история - logger!!
# 8. Последние 5 заказов в профиле. Это уже не локации, это ЗАКАЗЫ, профиль. профиль - заказы.
# 9. Фильтрация на основной странице уже сделана. Как именно? как её докрутить до моего требуемого состояния?



#////////////////////////////////////////////////////////////



async def get_all_categories(pool: asyncpg.pool.Pool):
    """
    Получить список всех категорий.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT category_id, name
            FROM categories
            ORDER BY name
        """)

async def add_category(pool: asyncpg.pool.Pool, name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO categories (category_id, name)
            VALUES (uuid_generate_v4(), $1)
        """, name)

async def update_category(pool: asyncpg.pool.Pool, category_id: str, name: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE categories
            SET name = $1
            WHERE category_id = $2
        """, name, category_id)

async def delete_category(pool: asyncpg.pool.Pool, category_id: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM categories WHERE category_id = $1
        """, category_id)



######################################################################
                            #Cart - будет устранена. а что взамен?
######################################################################



async def add_to_cart(pool: asyncpg.pool.Pool, user_id: str, product_id: str, quantity: int):
    """
    Добавить товар в корзину пользователя.
    """
    async with pool.acquire() as conn:
        # Проверяем, есть ли уже этот товар в корзине пользователя
        existing = await conn.fetchrow("""
            SELECT quantity FROM cart WHERE user_id = $1 AND product_id = $2
        """, user_id, product_id)

        if existing:
            # Обновляем количество товара в корзине
            await conn.execute("""
                UPDATE cart SET quantity = quantity + $1 WHERE user_id = $2 AND product_id = $3
            """, quantity, user_id, product_id)
        else:
            # Добавляем новый товар в корзину
            await conn.execute("""
                INSERT INTO cart (user_id, product_id, quantity)
                VALUES ($1, $2, $3)
            """, user_id, product_id, quantity)

async def get_cart_items(pool: asyncpg.pool.Pool, user_id: str):
    """
    Получить все товары в корзине пользователя.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT product_id, name, description, price, stock, quantity, total_cost
            FROM cart_details
            WHERE user_id = $1
        """, user_id)



async def remove_from_cart(pool: asyncpg.pool.Pool, user_id: str, product_id: str):
    """
    Удалить товар из корзины пользователя.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM cart WHERE user_id = $1 AND product_id = $2
        """, user_id, product_id)

async def update_cart_quantities(pool: asyncpg.pool.Pool, user_id: str, quantities: dict):
    """
    Обновить количество товаров в корзине пользователя.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            for product_id, quantity in quantities.items():
                quantity = int(quantity)
                if quantity <= 0:
                    # Удаляем товар из корзины, если количество <= 0
                    await conn.execute("""
                        DELETE FROM cart WHERE user_id = $1 AND product_id = $2
                    """, user_id, product_id)
                else:
                    # Проверяем доступность товара на складе
                    stock = await conn.fetchval("""
                        SELECT stock FROM products WHERE product_id = $1
                    """, product_id)
                    if quantity > stock:
                        raise ValueError(f"Недостаточно товара на складе для продукта {product_id}")
                    await conn.execute("""
                        UPDATE cart SET quantity = $1 WHERE user_id = $2 AND product_id = $3
                    """, quantity, user_id, product_id)


######################################################################
                            #Orders - rentals. Основа бизнес-логики
######################################################################

"""

0. Пойми, с чем взаимодействуют самокаты.
1. Копируй в гпт.
2. Получи это + измененное что-то на основе модели данных.

3. насколько сильно придется увеличить логику orders?

"""

#////////////////////////////////////////////////////////////

#1. Гарантия уникальности аренды
"""
ALTER TABLE rentals
ADD CONSTRAINT unique_active_rental_per_scooter
UNIQUE (scooter_id, end_time);

"""

# 2. Сколько раз был арендован конкретный самокат
"""
SELECT scooter_id, COUNT(*) AS rental_count
FROM rentals
GROUP BY scooter_id;

"""

# 3. Средняя продолжительность аренды

"""
SELECT AVG(EXTRACT(EPOCH FROM (end_time - start_time)) / 60) AS avg_duration
FROM rentals;

"""

# 4. Создание аренды

"""
INSERT INTO rentals (rental_id, user_id, scooter_id, rate_id, start_time)
VALUES (uuid_generate_v4(), 'user-id', 'scooter-id', 1, NOW());

"""

# 5. Завершение аренды

"""
UPDATE rentals
SET end_time = NOW(), total_price = TIMESTAMPDIFF(MINUTE, start_time, NOW()) * 0.10
WHERE rental_id = 'rental-id';

"""


# 6. Информация о текущей поездке (это аналог или не аналог корзины?)  
# Расчёт текущей стоимости (если аренда поминутная):

"""
SELECT (EXTRACT(EPOCH FROM NOW() - start_time) / 60) * r.price_per_minute AS current_price
FROM rentals re
JOIN rates r ON re.rate_id = r.rate_id
WHERE re.rental_id = 'current-rental-id';

"""

# 7. Общее время аренды

"""
SELECT NOW() - start_time AS duration
FROM rentals
WHERE rental_id = 'current-rental-id';

"""

# Информация:

#     Модель самоката: Xiaomi Mi Scooter 3
#     Уровень заряда: 85%
#     Начало аренды: 12:30 13/12/2024
#     Локация: ТЦ Москва
#     Текущая стоимость: 120.50 ₽
#     Время аренды: 15 минут


"""

SELECT s.model, s.battery_level, re.start_time, l.name AS location_name, 
       (EXTRACT(EPOCH FROM NOW() - re.start_time) / 60) * r.price_per_minute AS current_price,
       NOW() - re.start_time AS duration
FROM rentals re
JOIN scooters s ON re.scooter_id = s.scooter_id
JOIN locations l ON s.location_id = l.location_id
JOIN rates r ON re.rate_id = r.rate_id
WHERE re.user_id = 'current-user-id' AND re.end_time IS NULL;

"""

#////////////////////////////////////////////////////////////


async def get_last_orders(pool: asyncpg.pool.Pool, user_id: str):
    """
    Получить последние пять заказов пользователя.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT o.order_id, o.order_date, o.total_cost, ARRAY(
                SELECT p.name
                FROM order_items oi
                JOIN products p ON oi.product_id = p.product_id
                WHERE oi.order_id = o.order_id
            ) AS products
            FROM orders o
            WHERE o.user_id = $1
            ORDER BY o.order_date DESC
            LIMIT 5
        """, user_id)


async def process_order(pool: asyncpg.pool.Pool, user_id: str):
    async with pool.acquire() as conn:
        # Вызов хранимой процедуры, которая сама проведет все операции
        await conn.execute("CALL process_user_order($1)", user_id)

async def get_all_orders(pool):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT o.order_id, o.user_id, u.username, o.total_cost, o.order_date, o.status
            FROM orders o
            JOIN users u ON o.user_id = u.user_id
            ORDER BY o.order_date DESC
        """)

async def update_order_status(pool, order_id, new_status):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE orders SET status = $1 WHERE order_id = $2
        """, new_status, order_id)

######################################################################
                            #Reviews - оставим так же?
######################################################################

"""

0. Пойми, с чем взаимодействуют самокаты.
1. Копируй в гпт.
2. Получи это + измененное что-то на основе модели данных.

3. Если rental history и review содержат отзыв, то как быть с rental_history? сюда включить? Логика ведь та же? сохранять текст? 

4. Кажется, order-history нигде и не используется в БД. так же поступить?))))


9. А будет ли такая же аналитика по истории или это уже избыток? кажется, даже аналитика особо не нужна. для МВП хватит получить все отзывы.
.... но в перспективе допускается реализация дашбордов, аналитики. зимой.


"""

async def add_review(pool: asyncpg.pool.Pool, product_id: str, user_id: str, rating: int, comment: str):
    """
    Добавить отзыв к товару.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reviews (product_id, user_id, rating, comment)
            VALUES ($1, $2, $3, $4)
        """, product_id, user_id, rating, comment)

async def get_reviews_by_product_id(pool: asyncpg.pool.Pool, product_id: str):
    """
    Получить все отзывы для данного товара.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT r.*, u.username
            FROM reviews r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.product_id = $1
            ORDER BY r.review_date DESC
        """, product_id)

async def get_average_rating(pool: asyncpg.pool.Pool, product_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            SELECT get_average_product_rating($1)
        """, product_id)
