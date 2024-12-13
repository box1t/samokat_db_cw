from quart import Quart
from dotenv import load_dotenv
#from app.utils import create_admin
from app.utils import *

import asyncpg
import os
import logging
from datetime import timedelta

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
def create_app():
    app = Quart(__name__, template_folder="../templates", static_folder="../static")

    # Настройки приложения
    app.secret_key = os.getenv('SECRET_KEY', 'default_secret_key')

    @app.before_serving
    async def startup():
        """
        Создание пула соединений с базой данных при запуске приложения.
        """
        try:
            app.db_pool = await asyncpg.create_pool(
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT")),
                min_size=1,
                max_size=10,
            )
            logger.info("Пул соединений с базой данных успешно создан.")
            
            
            # Создание администратора при холодном запуске
            #admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            #admin_password = os.getenv("ADMIN_PASSWORD", "admin_password")
            #existing_user = await get_user_by_email(app.db_pool, admin_email)
            #if not existing_user:
                #await create_admin(app.db_pool, "admin", admin_password, admin_email)

        except Exception as e:
            logger.error(f"Ошибка при создании пула соединений: {e}")
            raise e

    @app.after_serving
    async def shutdown():
        """
        Закрытие пула соединений с базой данных.
        """
        try:
            await app.db_pool.close()
            logger.info("Пул соединений с базой данных закрыт.")
        except Exception as e:
            logger.error(f"Ошибка при закрытии пула соединений: {e}")

    # Импортируем Blueprints
    from .routes import main as main_blueprint
    from .admin_routes import admin as admin_blueprint

    # Регистрируем Blueprints
    app.register_blueprint(main_blueprint)
    app.register_blueprint(admin_blueprint)
    app.permanent_session_lifetime = timedelta(minutes=30)  


    return app