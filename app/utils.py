from functools import wraps
from quart import session, redirect, url_for, flash, current_app
from app.db import *

def admin_required(func):
    @wraps(func)
    async def decorated_view(*args, **kwargs):
        try:
            user_id = session.get('user_id')
            if not user_id:
                await flash("Пожалуйста, войдите в систему.", "warning")
                return redirect(url_for('main.login'))
            
            # Проверяем роли пользователя
            roles = await get_user_roles(current_app.db_pool, user_id)
            if 'Admin' not in roles:
                await flash("У вас нет прав администратора. Доступ запрещен.", "danger")
                return redirect(url_for('main.home'))
            
            return await func(*args, **kwargs)
        except Exception as e:
            current_app.logger.error(f"Ошибка при проверке прав администратора: {e}")
            await flash("Произошла ошибка при проверке прав. Попробуйте позже или обратитесь к администратору.", "danger")
            return redirect(url_for('main.home'))
    return decorated_view

#async def create_admin(pool: asyncpg.pool.Pool, username: str, password: str, email: str):
#    """
#    Создать администратора при холодном запуске.
#    """
#    hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
#    user_id = await create_user(pool, username, hashed_password, email)
#
#    # Назначаем роль администратора
#    async with pool.acquire() as conn:
#        admin_role_id = await get_role_id_by_name(pool, "Admin")
#        await conn.execute("""
#            INSERT INTO user_roles (user_id, role_id)
#            VALUES ($1, $2)
#        """, user_id, admin_role_id)
#
#    logger.info(f"Администратор {username} успешно создан с ID: {user_id}.")