from quart import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from app.db import *
import bcrypt
import logging
from quart import g
from app.utils import *
logger = logging.getLogger(__name__)
main = Blueprint("main", __name__)

######################################################################
                            #Test_routes
######################################################################


@main.route("/long")
async def long_task():
    import asyncio
    await asyncio.sleep(10)  # Симулируем долгую задачу
    return "Long task done!"

@main.route("/quick")
async def quick_task():
    return "Quick task done!"

######################################################################
                    #Check_roles_before_any_request
######################################################################


@main.before_app_request
async def load_user_roles():
    user_id = session.get('user_id')
    if user_id:
        g.user_roles = await get_user_roles(current_app.db_pool, user_id)
    else:
        g.user_roles = []

######################################################################
                            #MAIN_route
######################################################################

@main.route("/", methods=["GET"])
async def home():
    """
    Главная страница сайта с возможностью поиска и фильтрации самокатов.
    """
    try:
        query = request.args.get('q', '').strip()  # Поиск по модели
        location_id = request.args.get('location', '')  # Фильтрация по локации
        status = request.args.get('status', '').strip()  # Фильтрация по статусу
        min_battery = int(request.args.get('min_battery', 0))  # Минимальный заряд батареи

        # Получение списка локаций
        locations = await get_all_locations(current_app.db_pool)

        # Поиск самокатов с фильтрацией
        scooters = await search_scooters(
            current_app.db_pool,
            query=query,
            location_id=location_id,
            status=status,
            min_battery=min_battery
        )

        # Определение сообщения поиска
        if query or location_id or status or min_battery > 0:
            search_message = "Результаты поиска"
        else:
            search_message = None

        return await render_template(
            "home.html",
            scooters=scooters,
            locations=locations,
            search_message=search_message
        )
    except Exception as e:
        logger.error(f"Ошибка при загрузке главной страницы: {e}")
        return f"Ошибка при загрузке главной страницы: {e}", 500


######################################################################
                            #User_routes
######################################################################


@main.route("/profile")
async def profile():
    """
    Страница профиля пользователя.
    
    1. Создаётся сессия с привязкой к user_id, иначе - сброс на логин страницу, warning.
    2. Поиск информации по user_id для вывода на странице профиля, иначе - сброс на home страницу, warning.
    3. Вызов get_last_rentals - 5 заказов на страницу.
    4. Рендер шаблона profile.html
    """

    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    try:
        # Получаем информацию о пользователе
        user = await get_user_by_id(current_app.db_pool, user_id)
        if not user:
            await flash("Информация о пользователе не найдена.", "danger")
            return redirect(url_for("main.login"))

        # Получаем последние пять заказов
        last_rentals = await get_last_rentals(current_app.db_pool, user_id)

        return await render_template(
            "profile.html",
            username=user["username"],
            email=user["email"],
            last_rentals=last_rentals
        )
    except Exception as e:
        current_app.logger.error(f"Ошибка при загрузке профиля пользователя {user_id}: {e}")
        await flash("Произошла ошибка при загрузке профиля.", "danger")
        return redirect(url_for("main.home"))


@main.route("/register", methods=["GET", "POST"])
async def register():
    """
    Регистрация нового пользователя.
    
    1. Форма запрашивает пользователя ввести username, email, password.
    1.1. Если заполнены не все поля - сброс страницы, warning.
    2. Создаётся хэш пароля для хранения в БД.
    3. Вызываем get_user_by_email для проверки уникальности пользователя, иначе - сброс страницы, warning.
    4. Вызываем create_user.
    5. Если успешно, переброс на страницу login, иначе - сброс страницы, warning.
    """

    if request.method == "POST":
        logger.info("Начат процесс регистрации.")
        form = await request.form
        username = form.get("username")
        email = form.get("email")
        password = form.get("password")

        if not username or not email or not password:
            logger.warning("Не все поля формы регистрации заполнены.")
            await flash("Все поля обязательны для заполнения!", "warning")
            return redirect(url_for("main.register"))

        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        async with current_app.db_pool.acquire():
            try:
                # Проверяем, существует ли пользователь с таким email
                existing_user = await get_user_by_email(current_app.db_pool, email)
                if existing_user:
                    logger.warning(f"Пользователь с email {email} уже существует.")
                    await flash("Пользователь с таким email уже существует.", "danger")
                    return redirect(url_for("main.register"))

                # Создаём пользователя
                user_id = await create_user(current_app.db_pool, username, hashed_password, email)
                logger.info(f"Пользователь {email} успешно зарегистрирован с ID: {user_id}.")

                await flash("Регистрация прошла успешно! Теперь вы можете войти.", "success")
                return redirect(url_for("main.login"))
            except Exception as e:
                logger.error(f"Ошибка при регистрации пользователя {email}: {e}")
                await flash("Произошла ошибка. Попробуйте ещё раз.", "danger")
                return redirect(url_for("main.register"))

    return await render_template("register.html")

@main.route("/login", methods=["GET", "POST"])
async def login():
    """
    Авторизация пользователя.
    
    1. Форма запрашивает пользователя ввести email, password.
    1.1. Если заполнены не все поля - сброс страницы, warning.
    2. Вызываем get_user_by_email для проверки существования пользователя, 
        иначе - сброс страницы, warning.
    3. Вызываем проверку соответствия пароля: bcrypt.checkpw(введенный пароль, хранящийся пароль), 
        иначе - сброс страницы, 2 вида warning (ошибка и ValueError).
    4. Использование session для сохранения user_id, переброс на страницу home.
    """

    if request.method == "POST":
        logger.info("Начат процесс авторизации.")
        form = await request.form
        email = form.get("email")
        password = form.get("password")

        if not email or not password:
            logger.warning("Не все поля формы авторизации заполнены.")
            await flash("Все поля обязательны для заполнения!", "warning")
            return redirect(url_for("main.login"))

        try:
            # Получаем пользователя из базы данных
            user = await get_user_by_email(current_app.db_pool, email)
            if not user:
                logger.warning(f"Не найден пользователь с email {email}.")
                await flash("Неверный email или пароль. Если проблема сохраняется, обратитесь к администратору.", "danger")
                return redirect(url_for("main.login"))

            # Проверяем пароль
            hashed_password = user["hashed_password"]
            if not bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8")):
                logger.warning(f"Неверный пароль для email {email}.")
                await flash("Неверный email или пароль. Если проблема сохраняется, обратитесь к администратору.", "danger")
                return redirect(url_for("main.login"))

        except ValueError as e:
            logger.error(f"Ошибка при проверке пароля: {e}")
            await flash("Возникла проблема с вашим аккаунтом. Обратитесь к администратору.", "danger")
            return redirect(url_for("main.login"))

        # Успешный вход
        logger.info(f"Пользователь {email} успешно авторизовался.")
        session["user_id"] = str(user["user_id"])  # Используем session для сохранения user_id
        
        # Ручная загрузка ролей
        roles = await get_user_roles(current_app.db_pool, user["user_id"])
        logger.info(f"Роли пользователя: {roles}")

        if "admin" in map(str.lower, roles):  # Проверяем роль "admin"
            logger.info(f"Перенаправление пользователя {email} на /admin/.")
            return redirect(url_for("admin.admin_dashboard"))

        #await flash(f"Добро пожаловать, {user['username']}!", "success")
        return redirect(url_for("main.home"))  # Перенаправляем на главную страницу после авторизации

    logger.info("Отображение страницы авторизации.")
    return await render_template("login.html")


@main.route("/logout")
async def logout():
    """
    Выход из системы.
    """
    logger.info("Пользователь вышел из системы.")
    session.pop("user_id", None)
    await flash("Вы вышли из системы.", "info")
    return redirect(url_for("main.login"))

######################################################################
                            #Scooter_route
######################################################################

@main.route("/scooter/<scooter_id>", methods=["GET", "POST"])
async def scooter_page(scooter_id):
    """
    Страница самоката с описанием, количеством аренд, средней продолжительностью и отзывами.
    """
    user_id = session.get("user_id")

    # Обработка POST-запроса для добавления отзыва
    if request.method == "POST":
        if not user_id:
            await flash("Пожалуйста, войдите в систему, чтобы оставить отзыв.", "warning")
            return redirect(url_for("main.login"))

        form = await request.form
        rating = int(form.get("rating"))
        review_text = form.get("review_text")
        rental_id = form.get("rental_id")  # rental_id из формы (заполняется автоматически)

        if not rental_id:
            await flash("Не указана аренда, к которой привязан отзыв.", "warning")
            return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

        if rating < 1 or rating > 5:
            await flash("Оценка должна быть от 1 до 5.", "warning")
            return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

        if not review_text:
            await flash("Комментарий не может быть пустым.", "warning")
            return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

        try:
            # Проверяем, завершил ли пользователь эту аренду
            rental = await get_rental_by_id(current_app.db_pool, rental_id, user_id, scooter_id)
            if not rental:
                await flash("Аренда не найдена или не завершена.", "danger")
                return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

            # Добавляем отзыв
            await add_scooter_review(current_app.db_pool, rental_id, scooter_id, user_id, rating, review_text)
            await flash("Ваш отзыв успешно добавлен.", "success")
        except Exception as e:
            logger.error(f"Ошибка при добавлении отзыва: {e}")
            await flash("Ошибка при добавлении отзыва.", "danger")

        return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

    # Обработка GET-запроса для загрузки данных
    try:
        product = await get_scooter_by_id(current_app.db_pool, scooter_id)
        if not product:
            await flash("Самокат не найден.", "danger")
            return redirect(url_for("main.home"))

        reviews = await get_reviews_by_scooter_id(current_app.db_pool, scooter_id)
        rental_count = await get_rental_count_by_scooter(current_app.db_pool, scooter_id)
        avg_duration = await get_avg_rental_duration_by_scooter(current_app.db_pool, scooter_id)
        
        # Получение последней завершенной аренды
        last_rental = await get_last_completed_rental(current_app.db_pool, user_id, scooter_id)

        return await render_template(
            "product.html",
            product=product,
            reviews=reviews,
            rental_count=rental_count or 0,
            avg_duration=round(avg_duration or 0, 2),
            last_rental=last_rental  # Передаем последнюю аренду в шаблон
        )

    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы самоката: {e}")
        await flash("Произошла ошибка при загрузке страницы самоката.", "danger")
        return redirect(url_for("main.home"))


######################################################################
                            #Order_route
######################################################################

@main.route("/rental_page", methods=["POST"])
async def rent_scooter():
    """
    Арендовать самокат.
    1. бронь. бронь можно сделать на основной странице. статус "занят". но можно и без брони. тогда старт, продолжение, завершение.
    2. старт
    3. продолжение
    4. завершение
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    try:
        await process_order(current_app.db_pool, user_id) # type: ignore
        await flash("аренда успешно оформлена!", "success")
    except Exception as e:
        logger.error(f"Ошибка при оформлении заказа: {e}")
        await flash(str(e), "danger")

    return redirect(url_for("main.home"))


@main.route("/rental_action", methods=["POST"])
async def rental_action():
    user_id = session.get("user_id")
    if not user_id:
        await flash("Войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    form = await request.form
    action = form.get("action")
    rental_id = form.get("rental_id")
    location_id = form.get("location_id")

    try:
        if action == "continue":
            await continue_rental(current_app.db_pool, rental_id, location_id)
            await flash("Маршрут обновлён. Продолжайте поездку!", "success")

        elif action == "complete":
            await complete_rental(current_app.db_pool, rental_id)
            await flash("Поездка завершена.", "success")

        else:
            raise ValueError("Неизвестное действие.")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await flash(str(e), "danger")

    return redirect(url_for("main.home"))


@main.route("/reserve", methods=["POST"])
async def reserve_scooter():
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    scooter_id = request.form.get("scooter_id")
    location_id = request.form.get("location_id")

    try:
        # Проверка активных аренд
        if await has_active_rental(current_app.db_pool, user_id):
            await flash("У вас уже есть активная аренда.", "warning")
            return redirect(url_for("main.home"))

        # Бронь самоката
        await reserve_scooter(current_app.db_pool, user_id, scooter_id, location_id, price_per_minute=5.0)
        await flash("Самокат забронирован. Начните аренду!", "success")
    except Exception as e:
        logger.error(f"Ошибка бронирования: {e}")
        await flash("Ошибка при бронировании самоката.", "danger")

    return redirect(url_for("main.scooter_page", scooter_id=scooter_id))



@main.route("/rental/<scooter_id>", methods=["GET", "POST"])
async def rental_page(scooter_id):
    """
    Унифицированная страница аренды.
    - GET: Отображает состояние самоката и аренды.
    - POST: Начинает аренду или обновляет маршрут.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    if request.method == "POST":
        action = request.form.get("action")
        rental_id = request.form.get("rental_id")
        location_id = request.form.get("location_id")

        try:
            if action == "start":
                # Начало аренды
                await start_rental(current_app.db_pool, rental_id)
                await flash("Аренда начата!", "success")
            elif action == "continue":
                # Продолжение маршрута
                await continue_rental(current_app.db_pool, rental_id, location_id)
                await flash("Маршрут обновлён.", "success")
            elif action == "complete":
                # Завершение аренды
                await complete_rental(current_app.db_pool, rental_id)
                await flash("Аренда завершена.", "success")
                return redirect(url_for("main.home"))
        except Exception as e:
            logger.error(f"Ошибка аренды: {e}")
            await flash(str(e), "danger")

    # GET-запрос: Отображение текущего состояния
    rental = await get_rental_details(current_app.db_pool, scooter_id)
    return await render_template("rental_page.html", rental=rental)



@main.route("/order", methods=["POST"])
async def place_order():
    """
    Оформить заказ.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    try:
        await process_order(current_app.db_pool, user_id)
        await flash("Заказ успешно оформлен!", "success")
    except Exception as e:
        logger.error(f"Ошибка при оформлении заказа: {e}")
        await flash(str(e), "danger")

    return redirect(url_for("main.home"))


## Вместо repeat order будет continue ride.
## а в ride будут считаться функции. это основной бэкенд.
## но где считаются локации? тоже в поездке?
## если список локаций заготовлен и на него плевать, то с самокатами как?
## допустим, самокат заспавнили в X локации.
## ну и?


@main.route("/repeat_order", methods=["POST"])
async def repeat_order():
    """
    Повторить заказ.
    ИЛИ ПОВТОРИТЬ ДОБАВЛЕНИЕ В КОРЗИНУ?
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    order_id = (await request.form).get("order_id")
    if not order_id:
        await flash("Неверный запрос.", "danger")
        return redirect(url_for("main.profile"))

    try:
        async with current_app.db_pool.acquire() as conn:
            # Получаем товары из заказа
            products = await conn.fetch("""
                SELECT product_id, quantity
                FROM order_items
                WHERE order_id = $1
            """, order_id)

            # Добавляем товары в корзину
            for product in products:
                await add_to_cart(current_app.db_pool, user_id, product["product_id"], product["quantity"])

        await flash("Заказ успешно добавлен в корзину.", "success")
    except Exception as e:
        current_app.logger.error(f"Ошибка при повторении заказа {order_id}: {e}")
        await flash("Произошла ошибка при повторении заказа.", "danger")

    return redirect(url_for("main.cart"))

