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
        query = request.args.get('q', '').strip()
        location_id = request.args.get('location', '')
        status = request.args.get('status', '').strip()
        min_battery = int(request.args.get('min_battery', 0))

        user_id = session.get('user_id')  # Получаем ID текущего пользователя
        locations = await get_all_locations(current_app.db_pool)

        scooters = await search_scooters(
            current_app.db_pool,
            query=query,
            location_id=location_id,
            status=status,
            min_battery=min_battery,
            user_id=user_id
        )

        search_message = "Результаты поиска" if query or location_id or status or min_battery > 0 else None
        return await render_template(
            "home.html",
            scooters=scooters,
            locations=locations,
            search_message=search_message,
            selected_location_id=location_id
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
    Страница профиля пользователя с поддержкой пагинации.
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

        # Параметры пагинации
        page = int(request.args.get("page", 1))
        limit = 5
        offset = (page - 1) * limit

        # Получаем поездки с учетом пагинации
        last_rentals = await get_last_rentals(current_app.db_pool, user_id, limit=limit, offset=offset)

        # Проверяем, есть ли следующая страница
        has_more = len(last_rentals) == limit
        has_previous = page > 1


        return await render_template(
            "profile.html",
            username=user["username"],
            email=user["email"],
            last_rentals=last_rentals,
            page=page,
            has_more=has_more,
            has_previous=has_previous
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
    user_id = session.get("user_id")

    if request.method == "POST":
        if not user_id:
            await flash("Пожалуйста, войдите в систему, чтобы оставить отзыв.", "warning")
            return redirect(url_for("main.login"))

        form = await request.form
        rental_id = form.get("rental_id")
        rating = int(form.get("rating"))
        review_text = form.get("review_text")

        if not rental_id:
            await flash("Не указана аренда, к которой привязан отзыв.", "warning")
            return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

        try:
            rental = await get_rental_by_id(current_app.db_pool, rental_id, user_id, scooter_id, status='completed')
            if not rental:
                await flash("Аренда не найдена или не завершена.", "danger")
                return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

            existing_review = await get_review_by_rental_id(current_app.db_pool, rental_id)
            if existing_review:
                await flash("Вы уже оставили отзыв для этой аренды.", "warning")
                return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

            await add_scooter_review(current_app.db_pool, rental_id, scooter_id, user_id, rating, review_text)
            await flash("Ваш отзыв успешно добавлен.", "success")
        except Exception as e:
            logger.error(f"Ошибка при добавлении отзыва: {e}")
            await flash("Ошибка при добавлении отзыва.", "danger")

        return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

    try:
        scooter = await get_scooter_by_id_second(current_app.db_pool, scooter_id, user_id)
        if not scooter:
            await flash("Самокат не найден.", "danger")
            return redirect(url_for("main.home"))

        reviews = await get_reviews_by_scooter_id(current_app.db_pool, scooter_id)
        rental_count = await get_rental_count_by_scooter(current_app.db_pool, scooter_id)
        avg_duration = await get_avg_rental_duration_by_scooter(current_app.db_pool, scooter_id)
        last_rental = await get_last_completed_rental(current_app.db_pool, user_id, scooter_id)

        logger.debug(f"Last rental: {last_rental}")

        return await render_template(
            "scooter_page.html",
            scooters=scooter,
            reviews=reviews,
            rental_count=rental_count or 0,
            avg_duration=round(avg_duration or 0, 2),
            last_rental=last_rental
        )
    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы самоката: {e}")
        await flash("Произошла ошибка при загрузке страницы самоката.", "danger")
        return redirect(url_for("main.home"))



######################################################################
                            #Order_route
######################################################################


# 1. home/scooter_page
@main.route("/rental/reserve_scooter", methods=["POST"])
async def reserve_scooter_route():
    """
    Забронировать или отменить бронь самоката.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему, чтобы забронировать самокат.", "warning")
        return redirect(url_for("main.login"))

    form = await request.form
    scooter_id = form.get("scooter_id")
    start_location_id = form.get("start_location_id")
    action = form.get("action")  # Добавлено поле для действия
    redirect_url = form.get("redirect_url", url_for("main.home"))  # Получаем URL для редиректа

    try:
        if action == "reserve":
            # Вызов функции бронирования
            rental_id = await reserve_scooter(
                current_app.db_pool,
                user_id=user_id,
                scooter_id=scooter_id,
                start_location_id=start_location_id
            )
            await flash(f"Самокат успешно забронирован. ID бронирования: {rental_id}", "success")
        elif action == "cancel":
            # Вызов функции отмены бронирования
            await cancel_reservation(
                current_app.db_pool,
                user_id=user_id,
                scooter_id=scooter_id
            )
            await flash("Бронь успешно отменена.", "success")
        else:
            await flash("Неверное действие.", "danger")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await flash("Ошибка при обработке запроса.", "danger")

    return redirect(redirect_url)

# 2. home/header -> trip_details.html
@main.route("/rental/select_destination/<scooter_id>", methods=["GET"])
async def select_destination(scooter_id):
    """
    Загрузка страницы выбора пункта назначения.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    try:
        # Получаем самокат и доступные локации
        scooter = await get_scooter_by_id(current_app.db_pool, scooter_id)
        if not scooter:
            await flash("Самокат не найден.", "danger")
            return redirect(url_for("main.home"))

        destinations = await get_all_destinations_with_status(current_app.db_pool, scooter_id)
        #print(destinations)  # Отладка: проверить, что возвращается из функции

        rental = await get_active_rental(current_app.db_pool, user_id, scooter_id)

        return await render_template(
            "trip_details.html",
            scooter=scooter,
            destinations=destinations,
            rental=rental
        )
    except Exception as e:
        logger.error(f"Ошибка при загрузке страницы выбора пункта назначения для самоката {scooter_id}: {e}")
        await flash("Произошла ошибка при загрузке данных.", "danger")
        return redirect(url_for("main.home"))

# 3. trip_details.html
@main.route("/rental/confirm/<scooter_id>", methods=["POST"])
async def confirm_rental(scooter_id):
    """
    Подтверждение аренды с выбором конечной локации.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    form = await request.form
    end_location_id = form.get("end_location_id")

    if not end_location_id:
        await flash("Пункт назначения не выбран.", "warning")
        return redirect(url_for("main.trip_details", scooter_id=scooter_id))

    try:
        rental_id = await process_rental(
            pool=current_app.db_pool,
            user_id=user_id,
            scooter_id=scooter_id,
            action="rent",
            end_location_id=end_location_id
        )

        # Получаем обновленную аренду
        rental = await get_rental_by_id(
            current_app.db_pool, rental_id, user_id, scooter_id, status='active'
        )
        scooter = await get_scooter_by_id(current_app.db_pool, scooter_id)
        destinations = await get_all_destinations_with_status(current_app.db_pool, scooter_id)



        await flash(f"Аренда начата. ID аренды: {rental_id}", "success")
        return await render_template(
            "trip_details.html",
            rental=rental,
            scooter=scooter,
            destinations=destinations
        )
    except Exception as e:
        logger.error(f"Ошибка при начале аренды самоката {scooter_id}: {e}")
        await flash(str(e), "danger")
        return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

# 4. trip_details.html
@main.route("/rental/continue", methods=["POST"])
async def continue_rental():
    """
    Продолжить аренду самоката.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему.", "warning")
        return redirect(url_for("main.login"))

    form = await request.form
    scooter_id = form.get("scooter_id")
    end_location_id = form.get("end_location_id")

    if not scooter_id or not end_location_id:
        await flash("Не указаны необходимые данные для продолжения аренды.", "danger")
        return redirect(url_for("main.home"))

    try:
        rental_id = await process_rental(
            pool=current_app.db_pool,
            user_id=user_id,
            scooter_id=scooter_id,
            action="continue",
            end_location_id=end_location_id
        )
        await flash(f"Поездка продолжается. ID аренды: {rental_id}", "success")
    except Exception as e:
        logger.error(f"Ошибка при продолжении аренды самоката {scooter_id}: {e}")
        await flash(str(e), "danger")

    return redirect(url_for("main.trip_details"))

# 5. trip_details.html
@main.route("/rental/complete", methods=["POST"])
async def complete_rental_route():
    """
    Завершить аренду самоката.
    """
    user_id = session.get("user_id")
    if not user_id:
        await flash("Пожалуйста, войдите в систему, чтобы завершить аренду.", "warning")
        return redirect(url_for("main.login"))

    form = await request.form
    scooter_id = form.get("scooter_id")
    end_location_id = form.get("end_location_id")
    comment = form.get("comment")

    try:

        if end_location_id == '':
            end_location_id = None


        # Завершаем аренду
        rental_id = await complete_rental(
            current_app.db_pool,
            user_id=user_id,
            scooter_id=scooter_id,
            end_location_id=end_location_id,
            comment=comment
        )
        await flash(f"Аренда завершена. ID аренды: {rental_id}", "success")
    except Exception as e:
        logger.error(f"Ошибка при завершении аренды: {e}")
        await flash("Ошибка при завершении аренды.", "danger")

    return redirect(url_for("main.scooter_page", scooter_id=scooter_id))

