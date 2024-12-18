import asyncpg
import uuid
import bcrypt
import logging
from datetime import datetime
import math

logger = logging.getLogger(__name__)



######################################################################
                            #Roles (done)
######################################################################

# используется в функции create_user в route register, также могло бы использоваться при создании админа в холодном старте
async def get_role_id_by_name(pool: asyncpg.pool.Pool, role_name: str) -> int:
    """
    Получить ID роли по её имени.
    """
    async with pool.acquire() as conn:
        role_id = await conn.fetchval("""
            SELECT role_id 
            FROM roles 
            WHERE name = $1
        """, role_name)
        if not role_id:
            logger.error(f"Роль с именем {role_name} не найдена.")
        return role_id

# Используется в register
async def create_user(pool: asyncpg.pool.Pool, username: str, hashed_password: str, email: str):
    """
    Создать нового пользователя и вернуть его user_id.
    
    1. Генерация uuid
    2. Вставка в таблицу users введенных данных
    3. Получение user_id из таблицы user_roles по имени роли User (по умолчанию).
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

# Используется в login и register, поэтому допускается вывод *
async def get_user_by_email(pool: asyncpg.pool.Pool, email: str):
    """
    Получить пользователя по email.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * 
            FROM users 
            WHERE email = $1
        """, email)

### 1. Добавить админа при холодном старте
# используется в utils для доступа к админке + перед стартом приложения
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

# Используется в profile, поэтому во избежание утечек выводим не *
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


######################################################################
                        #Scooters - search
######################################################################

# Для поиска на главной странице home
async def search_scooters(
    pool: asyncpg.pool.Pool,
    query: str = '',
    location_id: str = '',
    status: str = '',  # Новый параметр для статуса (например, 'available')
    min_battery: int = 0
):
    """
    Поиск самокатов по модели, локации, статусу и уровню заряда.
    """
    async with pool.acquire() as conn:
        # Основной SQL-запрос
        sql = """
            SELECT 
                s.scooter_id, 
                s.model, 
                s.battery_level, 
                s.status, 
                l.name AS location_name
            FROM scooters s
            LEFT JOIN locations l ON s.location_id = l.location_id
        """
        
        # Условия поиска
        conditions = []
        params = []

        if query:
            conditions.append("s.model ILIKE $1")
            params.append(f"%{query}%")
        
        if location_id:
            conditions.append(f"s.location_id = ${len(params) + 1}")
            params.append(location_id)

        if status:
            conditions.append(f"s.status = ${len(params) + 1}")
            params.append(status)
        
        if min_battery > 0:
            conditions.append(f"s.battery_level >= ${len(params) + 1}")
            params.append(min_battery)
        
        # Добавляем WHERE и условия
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        # Сортировка по модели
        sql += " ORDER BY s.model"

        # Выполняем запрос
        return await conn.fetch(sql, *params)


# Для поиска на главной странице home
async def get_all_locations(pool: asyncpg.pool.Pool):
    """
    Получить список всех локаций.
    """
    async with pool.acquire() as conn:
        records = await conn.fetch("""
            SELECT location_id, name, latitude, longitude
            FROM locations
            ORDER BY name
        """)
        return [dict(record) for record in records]


# Получение информации на странице scooter
async def get_scooter_by_id(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Получить информацию о самокате по его ID.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT s.*, l.name AS location_name
            FROM scooters s
            LEFT JOIN locations l ON s.location_id = l.location_id
            WHERE s.scooter_id = $1
        """, scooter_id)


# это делает админ в manage_scooters
async def get_all_scooters(pool):
    """
    Получить список всех самокатов.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT *
            FROM scooters
            ORDER BY battery_level
        """)
    
###############################################################################################################
###############################################################################################################
###############################################################################################################

# возможно, это станет заменой    
async def get_scooters_with_options(pool, include_location: bool = True, order_by: str = 'model'):
    """
    Получить список самокатов с возможностью включения информации о локациях.

    :param pool: asyncpg пул соединений
    :param include_location: Флаг включения локаций в запрос
    :param order_by: Поле для сортировки (например, 'model', 'battery_level')
    """
    async with pool.acquire() as conn:
        base_query = """
            SELECT s.scooter_id, s.model, s.battery_level, s.is_available, s.last_maintenance_date,
                   s.battery_consumption, s.speed_limit
        """

        if include_location:
            base_query += ", l.name AS location_name, l.latitude, l.longitude"

        base_query += """
            FROM scooters s
        """

        if include_location:
            base_query += """
                LEFT JOIN locations l ON s.location_id = l.location_id
            """

        base_query += f"""
            ORDER BY s.{order_by}
        """

        return await conn.fetch(base_query)



## Пример с фильтрацией
async def get_scooters_with_options(pool, include_location: bool = True, order_by: str = 'model', is_available: bool = None):
    """
    Получить список самокатов с фильтрацией по доступности.
    """
    async with pool.acquire() as conn:
        sql = """
            SELECT s.scooter_id, s.model, s.battery_level, s.is_available, s.status, s.last_maintenance_date,
                   s.battery_consumption, s.speed_limit
        """
        if include_location:
            sql += ", l.name AS location_name"

        sql += " FROM scooters s"

        if include_location:
            sql += " LEFT JOIN locations l ON s.location_id = l.location_id"

        if is_available is not None:
            sql += " WHERE s.is_available = $1"

        sql += f" ORDER BY s.{order_by}"

        params = [is_available] if is_available is not None else []
        return await conn.fetch(sql, *params)


# для кого? админ и пользоватлеь?
async def get_all_scooters_sorted(pool):
    """
    Получить все самокаты, отсортированные по заряду и локации.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT s.scooter_id, s.model, s.battery_level, s.is_available, s.last_maintenance_date, 
                   l.name AS location_name
            FROM scooters s
            LEFT JOIN locations l ON s.location_id = l.location_id
            ORDER BY s.battery_level ASC, l.name ASC
        """)
###############################################################################################################
###############################################################################################################
###############################################################################################################


# для админа
async def service_scooters_in_location(pool, location_id):
    """
    Обслужить все самокаты в заданной локации: обновить дату обслуживания и сделать их недоступными.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scooters
            SET is_available = FALSE, 
                last_maintenance_date = $1
            WHERE location_id = $2
        """, datetime.utcnow(), location_id)

# либо админ, либо юзер
async def update_scooter_availability(pool, scooter_id, is_available: bool):
    """
    Обновить доступность самоката вручную.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scooters
            SET is_available = $1
            WHERE scooter_id = $2
        """, is_available, scooter_id)

# Это делает админ в manage_scooters
async def add_scooter(pool, model, battery_level, is_available=True, location_id=None,
                      battery_consumption=1.5, speed_limit=20.0, last_maintenance_date=None):
    """
    Добавить новый самокат в базу данных.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO scooters (scooter_id, model, battery_level, is_available, location_id, 
                                 battery_consumption, speed_limit, last_maintenance_date)
            VALUES (uuid_generate_v4(), $1, $2, $3, $4, $5, $6, $7)
        """, model, battery_level, is_available, location_id, 
        battery_consumption, speed_limit, last_maintenance_date)



# Это делает админ в manage_scooters
async def update_scooter(pool, scooter_id, model, battery_level, is_available, 
                         location_id=None, last_maintenance_date=None, 
                         battery_consumption=1.5, speed_limit=20.0):
    """
    Обновить информацию о самокате.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scooters
            SET model = $1, 
                battery_level = $2, 
                is_available = $3, 
                location_id = $4, 
                last_maintenance_date = $5, 
                battery_consumption = $6, 
                speed_limit = $7
            WHERE scooter_id = $8
        """, model, battery_level, is_available, 
            location_id, last_maintenance_date, 
            battery_consumption, speed_limit, scooter_id)



# Это делает админ в manage scooters
async def delete_scooter(pool, scooter_id):
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM scooters WHERE scooter_id = $1
        """, scooter_id)

######################################################################
                            #Reviews_on_scooters (last step)
######################################################################

# Для логики страницы scooter
async def add_scooter_review(pool: asyncpg.pool.Pool, rental_id: str, scooter_id: str, user_id: str, rating: int, review_text: str):
    """
    Добавить отзыв к самокату.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO reviews (rental_id, scooter_id, user_id, rating, review_text)
            VALUES ($1, $2, $3, $4, $5)
        """, rental_id, scooter_id, user_id, rating, review_text)


# для логики страницы продукта 
async def get_reviews_by_scooter_id(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Получить все отзывы для данного самоката.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT r.*, u.username
            FROM reviews r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.scooter_id = $1
            ORDER BY r.review_date DESC
        """, scooter_id)

# для процедурки/функции в schema.sql
async def get_average_rating_by_scooter(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Получить среднюю оценку для самоката.
    """
    async with pool.acquire() as conn:
        return await conn.fetchval("""
            SELECT get_average_scooter_rating($1)
        """, scooter_id)


######################################################################
                        #Locations (almost done)
######################################################################

# Для поиска на главной странице home, для админа в управлении продуктами; категориями
# а что еще с локациями можно сделать? будто бы ничего. делать надо что-то с самокатами или заказами.
async def get_all_locations(pool: asyncpg.pool.Pool):
    """
    Получить список всех локаций.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT location_id, name, latitude, longitude
            FROM locations
            ORDER BY name
        """)


# Для админа в управлении локациями
async def add_location(pool: asyncpg.pool.Pool, name: str, latitude: float, longitude: float):
    """
    Добавить новую локацию.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO locations (location_id, name, latitude, longitude)
            VALUES (uuid_generate_v4(), $1, $2, $3)
        """, name, latitude, longitude)

# Для админа в управлении локациями
async def update_location(pool: asyncpg.pool.Pool, location_id: str, name: str, latitude: float, longitude: float):
    """
    Обновить данные существующей локации.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE locations
            SET name = $1, latitude = $2, longitude = $3
            WHERE location_id = $4
        """, name, latitude, longitude, location_id)

# Для админа в управлении локациями
async def delete_location(pool: asyncpg.pool.Pool, location_id: str):
    """
    Удалить локацию по её ID.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM locations 
            WHERE location_id = $1
        """, location_id)



######################################################################
                            #Cart - будет устранена. а что взамен?
######################################################################


# для добавления в корзину; для повторения заказа
# но здесь нет проверки на общее кол-во товаров.
# здесь почему-то можно селектором увеличить кол-во
# но это неплохо, не так ли? 
# нигде нет проверки! но можно сделать запрет на покупку, если ч. превышает stock. но этого я делать не буду.
# как мне пригодится этот функционал?


async def add_to_cart(pool: asyncpg.pool.Pool, user_id: str, product_id: str, quantity: int):
    """
    Добавить товар в корзину пользователя.

    1. Проверяем, есть ли этот товар в корзине пользователя. (а разве тут есть проверка?)
    2. 

    3. Если товар существует, обновляем количество товара в корзине
    4. Иначе добавляем новый product_id в cart. 
    """

    async with pool.acquire() as conn:
        existing = await conn.fetchrow("""
            SELECT quantity 
            FROM cart 
            WHERE user_id = $1 AND product_id = $2
        """, user_id, product_id)
        if existing:
            await conn.execute("""
                UPDATE cart SET quantity = quantity + $1 WHERE user_id = $2 AND product_id = $3
            """, quantity, user_id, product_id)
        else:
            await conn.execute("""
                INSERT INTO cart (user_id, product_id, quantity)
                VALUES ($1, $2, $3)
            """, user_id, product_id, quantity)

# Для загрузки страницы корзины пользователя cart
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


# Для route - remove_item_from_cart
async def remove_from_cart(pool: asyncpg.pool.Pool, user_id: str, product_id: str):
    """
    Удалить товар из корзины пользователя.

    1. Какой вид удаления из корзины?
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM cart WHERE user_id = $1 AND product_id = $2
        """, user_id, product_id)

# Для загрузки страницы корзины пользователя cart. 
# Проверку на неотрицательность, видимо, проще делать в коде запросом.

# Это может быть переиспользовано для проверки уровня заряда или локации?
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
                        SELECT stock 
                        FROM products 
                        WHERE product_id = $1
                    """, product_id)
                    if quantity > stock:
                        raise ValueError(f"Недостаточно товара на складе для продукта {product_id}")
                    await conn.execute("""
                        UPDATE cart SET quantity = $1 WHERE user_id = $2 AND product_id = $3
                    """, quantity, user_id, product_id)


######################################################################
                            #Orders - rentals. (second step)
######################################################################


# Для создания страницы профиля пользователя
async def get_rental_count_by_scooter(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Возвращает количество аренд конкретного самоката.
    """
    sql = """
        SELECT COUNT(*) AS rental_count
        FROM rentals
        WHERE scooter_id = $1;
    """
    async with pool.acquire() as conn:
        result = await conn.fetchval(sql, scooter_id)
        return result
    
# Для создания страницы профиля пользователя
async def get_avg_rental_duration_by_scooter(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Возвращает среднюю продолжительность аренды самоката в минутах.
    """
    sql = """
        SELECT AVG(EXTRACT(EPOCH FROM (end_time - start_time)) / 60) AS avg_duration
        FROM rentals
        WHERE scooter_id = $1 AND end_time IS NOT NULL;
    """
    async with pool.acquire() as conn:
        result = await conn.fetchval(sql, scooter_id)
        return result

async def get_last_completed_rental(pool, user_id, scooter_id):
    """
    Возвращает последнюю завершенную аренду для указанного пользователя и самоката.
    """
    sql = """
        SELECT rental_id
        FROM rentals
        WHERE user_id = $1 AND scooter_id = $2 AND status = 'completed'
        ORDER BY end_time DESC
        LIMIT 1;
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(sql, user_id, scooter_id)


async def get_rental_by_id(pool, rental_id, user_id, scooter_id):
    """
    Проверяет, существует ли завершенная аренда для пользователя, самоката и rental_id.
    """
    sql = """
        SELECT 1
        FROM rentals
        WHERE rental_id = $1 AND user_id = $2 AND scooter_id = $3 AND status = 'completed';
    """
    async with pool.acquire() as conn:
        result = await conn.fetchval(sql, rental_id, user_id, scooter_id)
        return result


async def add_scooter_review(pool, rental_id, scooter_id, user_id, rating, review_text):
    """
    Добавляет отзыв в таблицу reviews.
    """
    sql = """
        INSERT INTO reviews (rental_id, scooter_id, user_id, rating, review_text, review_date)
        VALUES ($1, $2, $3, $4, $5, NOW());
    """
    async with pool.acquire() as conn:
        await conn.execute(sql, rental_id, scooter_id, user_id, rating, review_text)

async def get_completed_rentals_by_user_and_scooter(pool, user_id, scooter_id):
    """
    Возвращает список завершенных аренд пользователя для конкретного самоката.
    """
    sql = """
        SELECT rental_id, start_time, end_time, distance_km
        FROM rentals
        WHERE user_id = $1 AND scooter_id = $2 AND status = 'completed';
    """
    async with pool.acquire() as conn:
        return await conn.fetch(sql, user_id, scooter_id)


#////////////////////////////////////////////////////////////

# Для создания страницы профиля пользователя
async def get_last_rentals(pool: asyncpg.pool.Pool, user_id: str) -> list:
    """
    Получить последние пять аренд пользователя.
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT r.rental_id, r.start_time, r.end_time, r.total_price, r.status,
                   l1.location_name AS start_location, l2.location_name AS end_location
            FROM rentals r
            LEFT JOIN locations l1 ON r.start_location_id = l1.location_id
            LEFT JOIN locations l2 ON r.end_location_id = l2.location_id
            WHERE r.user_id = $1
            ORDER BY r.start_time DESC
            LIMIT 5
            """, user_id
        )

# логика обработки аренды. не факт, что хорошая.

##### Possible procedure

#////////////////////////////////////////////////////////////
#////////////////////////////////////////////////////////////
async def process_rental(pool: asyncpg.pool.Pool, user_id: str, scooter_id: str, start_location_id: str):
    """
    Вызов хранимой процедуры для старта аренды самоката.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "CALL process_user_rental($1, $2, $3)",
            user_id, scooter_id, start_location_id
        )
#////////////////////////////////////////////////////////////
#////////////////////////////////////////////////////////////

# для админа: логика управления всеми заказами
async def get_all_rentals(pool: asyncpg.pool.Pool) -> list:
    """
    Получить все аренды с информацией о пользователях и локациях для админа.
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT r.rental_id, r.user_id, u.username, r.scooter_id, 
                   l1.location_name AS start_location, l2.location_name AS end_location, 
                   r.start_time, r.end_time, r.total_price, r.status
            FROM rentals r
            JOIN users u ON r.user_id = u.user_id
            LEFT JOIN locations l1 ON r.start_location_id = l1.location_id
            LEFT JOIN locations l2 ON r.end_location_id = l2.location_id
            ORDER BY r.start_time DESC
            """
        )
    
# для админа: логика управления всеми заказами
async def update_rental_status(pool: asyncpg.pool.Pool, rental_id: str, new_status: str):
    """
    Обновить статус аренды.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE rentals SET status = $1 WHERE rental_id = $2
            """, new_status, rental_id
        )

## но добавился ride_comment. на странице поездки
## можно попробовать вставить в процедуру аренды, если тригер не сработает. но кажется, уже дописано. главное как-то запромптить это сделать.
## но уже есть инструкция от гпт, ты забыл!


def haversine(lat1, lon1, lat2, lon2):
    """
    Рассчитывает расстояние между двумя точками на Земле в км.
    """
    R = 6371  # Радиус Земли в километрах
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


async def continue_rental(pool, rental_id, new_location_id):
    """
    Продолжить аренду, предварительно проверяя возможность доехать с текущим зарядом.
    """
    async with pool.acquire() as conn:
        # Получаем текущую информацию об аренде и самокате
        rental = await conn.fetchrow("""
            SELECT r.scooter_id, r.distance_km, s.battery_level, s.battery_consumption, s.speed_limit, l.latitude, l.longitude
            FROM rentals r
            JOIN scooters s ON r.scooter_id = s.scooter_id
            JOIN locations l ON r.end_location_id = l.location_id
            WHERE r.rental_id = $1
        """, rental_id)

        if not rental:
            raise ValueError("Аренда не найдена.")

        # Получаем данные новой локации
        new_location = await conn.fetchrow("""
            SELECT latitude, longitude
            FROM locations
            WHERE location_id = $1
        """, new_location_id)

        if not new_location:
            raise ValueError("Локация не найдена.")

        # Рассчитываем расстояние до новой локации
        distance = haversine(
            rental['latitude'], rental['longitude'],
            new_location['latitude'], new_location['longitude']
        )

        # Проверяем, хватит ли заряда для поездки
        battery_needed = distance * rental['battery_consumption']
        if rental['battery_level'] < battery_needed:
            raise ValueError("Недостаточно заряда для поездки в выбранную локацию.")

        # Обновляем данные аренды: расстояние, заряд и локацию
        new_distance = rental['distance_km'] + distance
        new_battery_level = rental['battery_level'] - battery_needed

        # Обновляем аренду
        await conn.execute("""
            UPDATE rentals
            SET distance_km = $1, remaining_battery = $2, end_location_id = $3
            WHERE rental_id = $4
        """, new_distance, new_battery_level, new_location_id, rental_id)

        # Обновляем заряд самоката
        await conn.execute("""
            UPDATE scooters
            SET battery_level = $1, location_id = $2
            WHERE scooter_id = $3
        """, new_battery_level, new_location_id, rental['scooter_id'])

        await flash(f"Поездка обновлена. Заряда осталось: {new_battery_level}%.", "success")

async def complete_rental(pool, rental_id):
    """
    Завершает аренду и рассчитывает стоимость поездки.
    """
    async with pool.acquire() as conn:
        rental = await conn.fetchrow("""
            SELECT start_time, NOW() as current_time, price_per_minute, distance_km
            FROM rentals
            WHERE rental_id = $1 AND status = 'active'
        """, rental_id)

        if not rental:
            raise ValueError("Аренда не найдена или уже завершена.")

        # Рассчитываем длительность
        duration_minutes = (rental['current_time'] - rental['start_time']).total_seconds() / 60
        total_price = round(duration_minutes * rental['price_per_minute'], 2)

        # Завершаем аренду
        await conn.execute("""
            UPDATE rentals
            SET status = 'completed', end_time = NOW(), total_price = $1
            WHERE rental_id = $2
        """, total_price, rental_id)

        await flash(f"Аренда завершена. Итоговая стоимость: {total_price}₽.", "success")


