import asyncpg
import uuid
import bcrypt
import logging
from datetime import datetime, timezone
import math
from math import ceil
import matplotlib.pyplot as plt
import io
import base64
from uuid import UUID

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
async def search_scooters(pool: asyncpg.pool.Pool, user_id: str, **kwargs):
    async with pool.acquire() as conn:
        sql = """
            SELECT
                s.scooter_id,
                s.model,
                s.battery_level,
                s.status,
                s.last_maintenance_date,
                l.name AS location_name,
                s.reserved_by_user,
                CASE 
                    WHEN s.reserved_by_user = $1 THEN TRUE
                    ELSE FALSE
                END AS user_reserved
            FROM scooters s
            LEFT JOIN locations l ON s.location_id = l.location_id
            WHERE (s.status = 'available' AND s.reserved_by_user IS NULL)
               OR (s.status = 'reserved' AND s.reserved_by_user = $1)
        """
        rows = await conn.fetch(sql, user_id)
        scooters = [
            {
                "scooter_id": str(row["scooter_id"]),
                "model": row["model"],
                "battery_level": row["battery_level"],
                "status": row["status"],
                "location_name": row["location_name"],
                "reserved_by_user": str(row["reserved_by_user"]) if row["reserved_by_user"] else None,
                "user_reserved": row["user_reserved"]
            }
            for row in rows
        ]
        user_has_active_reservation = any(scooter["user_reserved"] for scooter in scooters)

    # Возвращаем два значения
    return scooters, user_has_active_reservation



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
    
async def get_scooter_by_id_second(pool: asyncpg.pool.Pool, scooter_id: str, user_id: str = None):
    async with pool.acquire() as conn:
        sql = """
            SELECT 
                s.scooter_id,
                s.model,
                s.battery_level,
                s.speed_limit,
                s.battery_consumption,
                s.status,
                s.last_maintenance_date,
                l.name AS location_name,
                CASE 
                    WHEN s.reserved_by_user = $2 THEN TRUE
                    ELSE FALSE
                END AS user_reserved
            FROM scooters s
            LEFT JOIN locations l ON s.location_id = l.location_id
            WHERE s.scooter_id = $1
        """
        return await conn.fetchrow(sql, scooter_id, user_id)

async def get_active_rental(pool: asyncpg.Pool, user_id: str, scooter_id: str):
    """
    Получить активную аренду для пользователя и самоката.
    """
    async with pool.acquire() as conn:
        rental = await conn.fetchrow("""
            SELECT * FROM rentals
            WHERE user_id = $1 AND scooter_id = $2 AND status = 'active'
        """, user_id, scooter_id)
        return rental

async def get_new_rental_by_id(pool: asyncpg.Pool, rental_id: str, user_id: str, scooter_id: str, status: str):
    """
    Получить аренду по ID с дополнительными фильтрами.
    """
    async with pool.acquire() as conn:
        rental = await conn.fetchrow("""
            SELECT * FROM rentals
            WHERE rental_id = $1 AND user_id = $2 AND scooter_id = $3 AND status = $4
        """, rental_id, user_id, scooter_id, status)
        return rental

#################################################################
                                #Admin_foos
#################################################################

# для админа
async def get_scooters_with_options(pool, include_location: bool = True, order_by: str = 'model'):
    """
    Получить список самокатов с возможностью включения информации о локациях.

    :param pool: asyncpg пул соединений
    :param include_location: Флаг включения локаций в запрос
    :param order_by: Поле для сортировки (например, 'model', 'battery_level')
    """
    async with pool.acquire() as conn:
        base_query = """
            SELECT s.scooter_id, s.model, s.battery_level, s.status, s.last_maintenance_date,
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

# для админа
async def get_all_scooters_sorted(pool, sort_by="battery_level", sort_order="ASC"):
    """
    Получить все самокаты, отсортированные по указанному полю.

    :param pool: Объект пула подключений к БД.
    :param sort_by: Поле для сортировки (battery_level, location_name, status, и т.д.).
    :param sort_order: Направление сортировки ("ASC" или "DESC").
    :return: Список словарей с данными самокатов.
    """
    valid_sort_fields = {"battery_level", "location_name", "status", "last_maintenance_date"}
    if sort_by not in valid_sort_fields:
        sort_by = "battery_level"
    if sort_order not in {"ASC", "DESC"}:
        sort_order = "ASC"

    query = f"""
        SELECT DISTINCT s.scooter_id, s.model, s.battery_level, s.status, 
                        s.last_maintenance_date, l.name AS location_name
        FROM scooters s
        LEFT JOIN locations l ON s.location_id = l.location_id
        ORDER BY {sort_by} {sort_order}, l.name ASC
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        # Преобразуем записи в список словарей
        return [dict(row) for row in rows] if rows else []

# для админа
async def service_scooters_in_location(pool, location_id):
    """
    Обслужить все самокаты в заданной локации: обновить дату обслуживания и установить статус 'on_maintenance'.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scooters
            SET status = 'on_maintenance', 
                last_maintenance_date = CURRENT_TIMESTAMP,
                battery_level = 100
            WHERE location_id = $1
        """, location_id)

# либо админ, либо юзер
async def update_scooter_status(pool, scooter_id, status: str):
    """
    Обновить статус самоката вручную.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scooters
            SET status = $1
            WHERE scooter_id = $2
        """, status, scooter_id)
    
async def get_reserved_scooters_with_users(pool: asyncpg.pool.Pool):
    """
    Получить список забронированных самокатов с информацией о пользователях.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT 
                s.scooter_id, 
                s.model, 
                s.status, 
                u.username AS reserved_by
            FROM scooters s
            LEFT JOIN users u ON s.reserved_by_user = u.user_id
            WHERE s.status = 'reserved';
        """)

        # Преобразуем результаты в список словарей для удобства работы
        return [
            {
                "scooter_id": row["scooter_id"],
                "model": row["model"],
                "status": row["status"],
                "reserved_by": row["reserved_by"]
            }
            for row in rows
        ]


# Это делает админ в manage_scooters
async def add_scooter(pool, model, battery_level, status='available', location_id=None,
                      battery_consumption=1.5, speed_limit=20.0, last_maintenance_date=None):
    """
    Добавить новый самокат в базу данных.
    """
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO scooters (scooter_id, model, battery_level, status, location_id, 
                                  battery_consumption, speed_limit, last_maintenance_date)
            VALUES (uuid_generate_v4(), $1, $2, $3, $4, $5, $6, $7)
        """, model, battery_level, status, location_id, 
        battery_consumption, speed_limit, last_maintenance_date)

# Это делает админ в manage_scooters
async def update_scooter(pool, scooter_id, model, battery_level, status, 
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
                status = $3, 
                location_id = $4, 
                last_maintenance_date = $5, 
                battery_consumption = $6, 
                speed_limit = $7
            WHERE scooter_id = $8
        """, model, battery_level, status, 
            location_id, last_maintenance_date, 
            battery_consumption, speed_limit, scooter_id)

# Это делает админ в manage scooters
async def delete_scooter(pool, scooter_id):
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM scooters WHERE scooter_id = $1
        """, scooter_id)

# ограничения для администратора
async def is_duplicate_location(pool, name, location_id=None):
    """
    Проверяет, существует ли локация с указанным именем.
    """
    async with pool.acquire() as conn:
        sql = """
            SELECT location_id
            FROM locations
            WHERE name = $1
        """
        params = [name]
        
        # Исключаем текущую локацию при редактировании
        if location_id:
            sql += " AND location_id != $2"
            params.append(location_id)
        
        result = await conn.fetchrow(sql, *params)
        return result is not None

# ограничения для администратора
async def is_duplicate_scooter_characteristics(pool, model, speed_limit, battery_consumption, scooter_id=None):
    """
    Проверяет, существуют ли разные характеристики для одной модели.
    """
    async with pool.acquire() as conn:
        sql = """
            SELECT scooter_id
            FROM scooters
            WHERE model = $1 AND speed_limit = $2 AND battery_consumption = $3
        """
        params = [model, speed_limit, battery_consumption]
        
        # Исключаем текущий самокат при редактировании
        if scooter_id:
            sql += " AND scooter_id != $4"
            params.append(scooter_id)
        
        result = await conn.fetchrow(sql, *params)
        return result is not None



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

async def get_rental_history_by_rental_id(pool: asyncpg.pool.Pool, rental_id: str):
    """
    Получить историю аренды по ID аренды.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM rental_history WHERE rental_id = $1
        """, rental_id)


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
                            #Locations
######################################################################

# Для поиска на главной странице home, для админа в управлении продуктами; категориями
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
                            # Rentals (Admin foos)
######################################################################

# для админа: логика управления всеми заказами
async def get_all_rentals(pool: asyncpg.pool.Pool) -> list:
    """
    Получить все аренды с информацией о пользователях и локациях для админа.
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT r.rental_id, r.user_id, u.username, r.scooter_id, 
                l1.name AS start_location, l2.name AS end_location, 
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


######################################################################
                            # Rentals
######################################################################

# Для создания страницы профиля пользователя
async def get_last_rentals(pool: asyncpg.pool.Pool, user_id: str, limit: int = 5, offset: int = 0):
    """
    Получить последние поездки пользователя с учетом пагинации.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT 
                r.rental_id,
                r.end_time,
                r.total_price,
                sl.name AS start_location_name,
                el.name AS end_location_name
            FROM rentals r
            LEFT JOIN locations sl ON r.start_location_id = sl.location_id
            LEFT JOIN locations el ON r.end_location_id = el.location_id
            WHERE r.user_id = $1 AND r.status != 'cancelled' AND r.status != 'reserved'  
            ORDER BY r.end_time DESC
            LIMIT $2 OFFSET $3
        """, user_id, limit, offset)


# объединить для создания представления и дашборда
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

# объединить для создания представления
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

# объединить для создания представления
async def get_last_completed_rental(pool, user_id, scooter_id):
    """
    Получает последнюю завершенную аренду для пользователя и самоката,
    а также проверяет, оставлен ли отзыв.
    """
    sql = """
        SELECT 
            r.rental_id AS id,
            EXISTS (
                SELECT 1 
                FROM reviews rv 
                WHERE rv.rental_id = r.rental_id
            ) AS has_review
        FROM rentals r
        WHERE r.user_id = $1 AND r.scooter_id = $2 AND r.status = 'completed'
        ORDER BY r.end_time DESC
        LIMIT 1;
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, user_id, scooter_id)


# Для создания страницы профиля пользователя
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

# пользовательское ограничение на другие аренды, пока есть незавершенная
async def get_rental_by_id(pool, rental_id, user_id, scooter_id, status):
    query = """
        SELECT *
        FROM rentals
        WHERE rental_id = $1 AND user_id = $2 AND scooter_id = $3 AND status = $4
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, rental_id, user_id, scooter_id, status)

async def get_review_by_rental_id(pool: asyncpg.pool.Pool, rental_id: str):
    """
    Проверяет, существует ли отзыв для указанной аренды.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT *
            FROM reviews
            WHERE rental_id = $1
        """, rental_id)

#######################################3
# процедура поездки
#async def process_rental(pool, user_id, scooter_id, action, end_location_id=None):
#    async with pool.acquire() as conn:
#        # Начинаем транзакцию
#        async with conn.transaction():
#            rental_id = await conn.fetchval(
#                "SELECT process_rental_action($1, $2, $3, $4)",
#                user_id, scooter_id, action, end_location_id
#            )
#        return rental_id

async def get_low_battery_scooters_by_location(pool):
    """
    Подсчитать количество самокатов по уровням заряда (< 20%, 20–50%, > 50%) для каждой локации.
    Добавить итоговую строку с общими суммами.

    :param pool: Объект пула подключений к базе данных.
    :return: Список словарей с данными о локациях и количестве самокатов по уровням заряда.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH battery_counts AS (
                SELECT
                    COALESCE(l.name, 'Без локации') AS location_name,
                    SUM(CASE WHEN COALESCE(s.battery_level, 0) < 20 THEN 1 ELSE 0 END) AS low_battery_count,
                    SUM(CASE WHEN COALESCE(s.battery_level, 0) BETWEEN 20 AND 50 THEN 1 ELSE 0 END) AS medium_battery_count,
                    SUM(CASE WHEN COALESCE(s.battery_level, 0) > 50 THEN 1 ELSE 0 END) AS high_battery_count
                FROM scooters s
                LEFT JOIN locations l ON s.location_id = l.location_id
                GROUP BY l.name
            )
            SELECT 
                location_name,
                low_battery_count,
                medium_battery_count,
                high_battery_count
            FROM battery_counts

            UNION ALL

            SELECT 
                'ИТОГО',
                COALESCE(SUM(low_battery_count), 0),
                COALESCE(SUM(medium_battery_count), 0),
                COALESCE(SUM(high_battery_count), 0)
            FROM battery_counts;
        """)

        # Преобразование результатов в список словарей
        result = [
            {
                "location_name": row["location_name"],
                "low_battery_count": row["low_battery_count"],
                "medium_battery_count": row["medium_battery_count"],
                "high_battery_count": row["high_battery_count"]
            }
            for row in rows
        ]

        # Если итоговая строка отсутствует (на случай некорректного SQL), добавляем вручную
        if not any(row["location_name"] == "ИТОГО" for row in result):
            result.append({
                "location_name": "ИТОГО",
                "low_battery_count": sum(r["low_battery_count"] for r in result),
                "medium_battery_count": sum(r["medium_battery_count"] for r in result),
                "high_battery_count": sum(r["high_battery_count"] for r in result)
            })

        return result



async def get_scooter_rental_status_on_selection(db_pool, user_id, scooter_id):
    query = """
        SELECT status
        FROM scooters
        WHERE scooter_id = $1 AND reserved_by_user = $2
    """
    async with db_pool.acquire() as conn:
        return await conn.fetchrow(query, scooter_id, user_id)

# вычисление расстояния между локациями
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


# async def continue_rental(pool, rental_id, new_location_id):
#     """
#     Продолжить аренду, предварительно проверяя возможность доехать с текущим зарядом.
#     """
#     async with pool.acquire() as conn:
#         # Получаем текущую информацию об аренде и самокате
#         rental = await conn.fetchrow("""
#             SELECT r.scooter_id, r.distance_km, s.battery_level, s.battery_consumption, s.speed_limit, l.latitude, l.longitude
#             FROM rentals r
#             JOIN scooters s ON r.scooter_id = s.scooter_id
#             JOIN locations l ON r.end_location_id = l.location_id
#             WHERE r.rental_id = $1
#         """, rental_id)

#         if not rental:
#             raise ValueError("Аренда не найдена.")

#         # Получаем данные новой локации
#         new_location = await conn.fetchrow("""
#             SELECT latitude, longitude
#             FROM locations
#             WHERE location_id = $1
#         """, new_location_id)

#         if not new_location:
#             raise ValueError("Локация не найдена.")

#         # Рассчитываем расстояние до новой локации
#         distance = haversine(
#             rental['latitude'], rental['longitude'],
#             new_location['latitude'], new_location['longitude']
#         )

#         # Проверяем, хватит ли заряда для поездки
#         battery_needed = distance * rental['battery_consumption']
#         if rental['battery_level'] < battery_needed:
#             raise ValueError("Недостаточно заряда для поездки в выбранную локацию.")

#         # Обновляем данные аренды: расстояние, заряд и локацию
#         new_distance = rental['distance_km'] + distance
#         new_battery_level = rental['battery_level'] - battery_needed

#         # Обновляем аренду
#         await conn.execute("""
#             UPDATE rentals
#             SET distance_km = $1, remaining_battery = $2, end_location_id = $3
#             WHERE rental_id = $4
#         """, new_distance, new_battery_level, new_location_id, rental_id)

#         # Обновляем заряд самоката
#         await conn.execute("""
#             UPDATE scooters
#             SET battery_level = $1, location_id = $2
#             WHERE scooter_id = $3
#         """, new_battery_level, new_location_id, rental['scooter_id'])

#         await flash(f"Поездка обновлена. Заряда осталось: {new_battery_level}%.", "success")


async def set_scooter_in_use(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Переводит статус скутера в 'in_use'.
    Предполагается, что скутер перед этим был в статусе 'reserved'.
    """
        
    logger.info(f"Setting scooter {scooter_id} to 'in_use'")
    async with pool.acquire() as conn:
        # Опционально можно проверить, что скутер действительно 'reserved'
        current_status = await conn.fetchval("""
            SELECT status FROM scooters WHERE scooter_id = $1
        """, scooter_id)
        logger.info(f"Update result: {current_status}")

        if current_status != 'reserved':
            raise Exception("Невозможно перевести скутер в статус 'in_use', так как он не забронирован.")

        res = await conn.execute("""
            UPDATE scooters
            SET status = 'in_use'
            WHERE scooter_id = $1
        """, scooter_id)
        logger.info(f"Update result: {res}")

# 1
async def reserve_scooter(pool: asyncpg.pool.Pool, user_id: str, scooter_id: str, start_location_id: str = None):
    async with pool.acquire() as conn:
        # Проверяем, что самокат доступен для бронирования:
        # Должен быть status='available' и reserved_by_user=NULL
        scooter = await conn.fetchrow("""
            SELECT scooter_id 
            FROM scooters 
            WHERE scooter_id = $1 AND status = 'available' AND reserved_by_user IS NULL
        """, scooter_id)

        if not scooter:
            raise Exception("Самокат не найден или уже забронирован другим пользователем.")

        # Устанавливаем бронь
        await conn.execute("""
            UPDATE scooters
            SET status = 'reserved', reserved_by_user = $1
            WHERE scooter_id = $2
        """, user_id, scooter_id)


# 2
async def cancel_reservation(pool: asyncpg.pool.Pool, user_id: str, scooter_id: str):
    async with pool.acquire() as conn:
        reserved_by_user = await conn.fetchval("""
            SELECT reserved_by_user::TEXT 
            FROM scooters 
            WHERE scooter_id = $1 AND status = 'reserved'
        """, scooter_id)

        if str(reserved_by_user) != str(user_id):
            raise Exception("Вы не можете отменить бронь, созданную другим пользователем.")

        await conn.execute("""
            UPDATE scooters
            SET status = 'available', reserved_by_user = NULL
            WHERE scooter_id = $1 AND reserved_by_user = $2
        """, scooter_id, user_id)


def convert_uuid_to_str(data):
    """
    Рекурсивное преобразование UUID в строки.
    :param data: dict, list или другой объект.
    :return: Преобразованные данные.
    """
    if isinstance(data, dict):
        return {key: str(value) if isinstance(value, UUID) else value for key, value in data.items()}
    elif isinstance(data, list):
        return [{key: str(value) if isinstance(value, UUID) else value for key, value in item.items()} for item in data]
    return data

# 3
async def get_all_destinations_with_status(pool: asyncpg.pool.Pool, scooter_id: str):
    """
    Получить список доступных локаций для самоката.

    :param pool: Пул соединений.
    :param scooter_id: ID самоката.
    :return: Список доступных локаций.
    """
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT * FROM get_all_destinations_with_status($1)
        """, scooter_id)

# 4
async def calculate_distance_and_battery_needed(pool: asyncpg.Pool, scooter_id: str, end_location_id: str):
    """
    Рассчитать расстояние и необходимый заряд батареи для достижения end_location_id
    из текущего местоположения самоката.
    """
    async with pool.acquire() as conn:
        # Получаем данные самоката и его текущую локацию
        row = await conn.fetchrow("""
            SELECT sc.battery_level, sc.battery_consumption,
                   sl.latitude AS start_lat, sl.longitude AS start_lon,
                   l.latitude AS end_lat, l.longitude AS end_lon
            FROM scooters sc
            JOIN locations sl ON sc.location_id = sl.location_id
            JOIN locations l ON l.location_id = $2
            WHERE sc.scooter_id = $1
        """, scooter_id, end_location_id)

        if not row:
            raise ValueError("Невозможно получить данные для расчёта.")

        battery_level = row["battery_level"]
        battery_consumption = row["battery_consumption"]
        start_lat = row["start_lat"]
        start_lon = row["start_lon"]
        end_lat = row["end_lat"]
        end_lon = row["end_lon"]

        distance_km = await conn.fetchval("""
            SELECT haversine($1, $2, $3, $4)
        """, start_lat, start_lon, end_lat, end_lon)

        battery_needed = distance_km * battery_consumption

        return distance_km, battery_needed, battery_level, battery_consumption



# 5

async def process_rental(pool: asyncpg.Pool, user_id: str, scooter_id: str, action: str, end_location_id: str) -> str:
    logger.info(f"Processing rental: User {user_id}, Scooter {scooter_id}, Action {action}, End Location {end_location_id}")
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Получаем данные о самокате
            scooter = await conn.fetchrow("SELECT * FROM scooters WHERE scooter_id = $1 FOR UPDATE", scooter_id)
            logger.info(f"Scooter data: {scooter}")
            if not scooter:
                raise ValueError("Самокат не найден.")

            # Проверяем статус аренды
            if action == "rent":
                active_rental = await conn.fetchrow("""
                    SELECT * FROM rentals 
                    WHERE user_id = $1 AND scooter_id = $2 AND status = 'active'
                """, user_id, scooter_id)
                logger.info(f"Active rental check: {active_rental}")

                if active_rental:
                    raise ValueError("У вас уже есть активная аренда этого самоката.")

                if scooter["status"] not in ("available", "reserved"):
                    raise ValueError("Самокат недоступен для аренды.")

                # Расчёт расстояния и батареи
                try:
                    distance_km, battery_needed, battery_level, battery_consumption = await calculate_distance_and_battery_needed(
                        pool, scooter_id, end_location_id
                    )
                except Exception as e:
                    logger.error(f"Error in distance calculation: {e}")
                    raise

                logger.info(f"Distance: {distance_km}, Battery needed: {battery_needed}, Battery level: {battery_level}")

                if battery_needed > battery_level:
                    raise ValueError("Недостаточно заряда батареи для поездки до выбранной локации.")

                # Создание аренды
                price_per_minute = 5.00
                start_location_id = scooter["location_id"]
                rental_id = await conn.fetchval("""
                    INSERT INTO rentals (
                        user_id, scooter_id, start_location_id, end_location_id, 
                        price_per_minute, distance_km, remaining_battery, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'active')
                    RETURNING rental_id
                """, user_id, scooter_id, start_location_id, end_location_id, price_per_minute, distance_km, battery_level - battery_needed)
                logger.info(f"Rental created with ID: {rental_id}")

                # Обновление статуса самоката
                new_battery_level = battery_level - battery_needed
                await conn.execute("""
                    UPDATE scooters
                    SET status = 'in_use', location_id = $1, battery_level = $2
                    WHERE scooter_id = $3
                """, end_location_id, new_battery_level, scooter_id)
                logger.info(f"Scooter updated: Battery level {new_battery_level}, Location ID {end_location_id}")

                return rental_id


# # 6

# async def continue_rental(pool, rental_id, new_location_id):
#     """
#     Продолжить аренду, проверяя возможность доехать с текущим зарядом.
#     """
#     async with pool.acquire() as conn:
#         async with conn.transaction():
#             # Получаем текущую информацию об аренде и самокате
#             rental = await conn.fetchrow("""
#                 SELECT r.scooter_id, r.distance_km, s.battery_level, s.battery_consumption, s.speed_limit, l.latitude, l.longitude
#                 FROM rentals r
#                 JOIN scooters s ON r.scooter_id = s.scooter_id
#                 JOIN locations l ON r.end_location_id = l.location_id
#                 WHERE r.rental_id = $1 AND r.status = 'active'
#             """, rental_id)

#             if not rental:
#                 raise ValueError("Активная аренда не найдена.")

#             # Получаем данные новой локации
#             new_location = await conn.fetchrow("""
#                 SELECT latitude, longitude
#                 FROM locations
#                 WHERE location_id = $1
#             """, new_location_id)

#             if not new_location:
#                 raise ValueError("Локация не найдена.")

#             # Рассчитываем расстояние до новой локации
#             distance = haversine(
#                 rental['latitude'], rental['longitude'],
#                 new_location['latitude'], new_location['longitude']
#             )

#             # Проверяем, хватит ли заряда для поездки
#             battery_needed = distance * rental['battery_consumption']
#             if rental['battery_level'] < battery_needed:
#                 raise ValueError("Недостаточно заряда для поездки в выбранную локацию.")

#             # Обновляем данные аренды: расстояние, заряд и локацию
#             new_distance = rental['distance_km'] + distance
#             new_battery_level = rental['battery_level'] - battery_needed

#             # Обновляем аренду
#             await conn.execute("""
#                 UPDATE rentals
#                 SET distance_km = $1, remaining_battery = $2, end_location_id = $3
#                 WHERE rental_id = $4
#             """, new_distance, new_battery_level, new_location_id, rental_id)

#             # Обновляем заряд и статус самоката
#             await conn.execute("""
#                 UPDATE scooters
#                 SET battery_level = $1, location_id = $2
#                 WHERE scooter_id = $3
#             """, new_battery_level, new_location_id, rental['scooter_id'])

#             # Возвращаем обновлённые данные
#             return {
#                 "new_distance": new_distance,
#                 "new_battery_level": new_battery_level,
#                 "new_location_id": new_location_id
#             }


# 7
async def complete_rental(pool: asyncpg.pool.Pool, user_id: str, scooter_id: str, end_location_id: str, comment: str = None):
    async with pool.acquire() as conn:
        async with conn.transaction():
            rental = await conn.fetchrow("""
                SELECT * FROM rentals 
                WHERE user_id = $1 AND scooter_id = $2 AND status = 'active'
                FOR UPDATE
            """, user_id, scooter_id)

            if not rental:
                raise ValueError("Активная аренда не найдена.")

            await conn.execute("""
                UPDATE rentals
                SET status = 'completed', end_time = NOW(), end_location_id = $1, ride_comment = $2
                WHERE rental_id = $3
            """, end_location_id, comment, rental["rental_id"])

            await conn.execute("""
                UPDATE scooters
                SET status = 'available', reserved_by_user = NULL, location_id = $1
                WHERE scooter_id = $2
            """, end_location_id, scooter_id)

            return rental["rental_id"]



