from quart import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, g
from app.db import *
import os
import datetime
from app.utils import *
from dotenv import load_dotenv
import glob
import subprocess

admin = Blueprint('admin', __name__, url_prefix='/admin')

load_dotenv()


@admin.route('/')
@admin_required
async def admin_dashboard():
    """
    Главная страница админки.
    """
    return await render_template('admin/dashboard.html')

######################################################################
                            #Change/Update data
######################################################################


@admin.route('/products', methods=['GET', 'POST'])
@admin_required
async def manage_products():
    """
    Управление товарами: просмотр, добавление, редактирование, удаление.
    """
    if request.method == 'POST':
        form = await request.form
        action = form.get('action')
        if action == 'add':
            # Добавление нового товара
            name = form.get('name')
            description = form.get('description')
            category_id = form.get('category_id') or None
            price = float(form.get('price'))
            stock = int(form.get('stock'))
            manufacturer = form.get('manufacturer')
            await add_product(current_app.db_pool, name, description, price, stock, manufacturer, category_id)
            await flash('Товар добавлен.', 'success')
        elif action == 'edit':
            # Редактирование существующего товара
            product_id = form.get('product_id')
            name = form.get('name')
            description = form.get('description')
            category_id = form.get('category_id') or None
            price = float(form.get('price'))
            stock = int(form.get('stock'))
            manufacturer = form.get('manufacturer')
            await update_product(current_app.db_pool, product_id, name, description, price, stock, manufacturer, category_id)
            await flash('Товар обновлен.', 'success')
        elif action == 'delete':
            # Удаление товара
            product_id = form.get('product_id')
            await delete_product(current_app.db_pool, product_id)
            await flash('Товар удален.', 'success')
        return redirect(url_for('admin.manage_products'))

    # GET-запрос: отображаем список товаров и категорий
    products = await get_all_products_with_categories(current_app.db_pool)
    categories = await get_all_categories(current_app.db_pool)
    return await render_template('admin/manage_products.html', products=products, categories=categories)


@admin.route('/categories', methods=['GET', 'POST'])
@admin_required
async def manage_categories():
    """
    Управление категориями: просмотр, добавление, редактирование, удаление.
    """
    if request.method == 'POST':
        form = await request.form
        action = form.get('action')
        if action == 'add':
            name = form.get('name')
            await add_category(current_app.db_pool, name)
            await flash('Категория добавлена.', 'success')
        elif action == 'edit':
            category_id = form.get('category_id')
            name = form.get('name')
            await update_category(current_app.db_pool, category_id, name)
            await flash('Категория обновлена.', 'success')
        elif action == 'delete':
            category_id = form.get('category_id')
            await delete_category(current_app.db_pool, category_id)
            await flash('Категория удалена.', 'success')
        return redirect(url_for('admin.manage_categories'))

    categories = await get_all_categories(current_app.db_pool)
    return await render_template('admin/manage_categories.html', categories=categories)


@admin.route('/orders', methods=['GET', 'POST'])
@admin_required
async def manage_orders():
    """
    Управление заказами: просмотр и изменение статуса.
    """
    if request.method == 'POST':
        form = await request.form
        order_id = form.get('order_id')
        new_status = form.get('status')
        await update_order_status(current_app.db_pool, order_id, new_status)
        await flash('Статус заказа обновлен.', 'success')
        return redirect(url_for('admin.manage_orders'))

    # GET-запрос: отображаем список заказов
    orders = await get_all_orders(current_app.db_pool)
    return await render_template('admin/manage_orders.html', orders=orders)




######################################################################
                            #Backup/Restore db
######################################################################


@admin.route('/backup', methods=['GET'])
@admin_required
async def backup_database():
    """
    Резервное копирование базы данных.
    """
    # Путь к резервной копии
    backup_dir = 'backups'
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, f'backup_{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}.sql')

    # Команда для резервного копирования
    db_name = os.getenv("DB_NAME") 
    db_user = os.getenv("DB_USER")       
    db_password = os.getenv("DB_PASSWORD")  

    command = f'PGPASSWORD="{db_password}" pg_dump -U {db_user} {db_name} > {backup_file}'

    # Выполнение команды
    result = os.system(command)
    if result == 0:
        await flash(f'Резервная копия создана: {backup_file}', 'success')
    else:
        await flash('Ошибка при создании резервной копии.', 'danger')

    return redirect(url_for('admin.admin_dashboard'))


@admin.route('/restore', methods=['GET', 'POST'])
@admin_required
async def restore_database():
    """
    Восстановление базы данных из резервной копии.
    """
    backup_dir = 'backups'
    if request.method == 'POST':
        form = await request.form
        backup_file = form.get('backup_file')
        if not backup_file:
            await flash('Пожалуйста, выберите файл резервной копии.', 'warning')
            return redirect(url_for('admin.restore_database'))

        # Полный путь к файлу резервной копии
        backup_path = os.path.join(backup_dir, backup_file)
        if not os.path.exists(backup_path):
            await flash('Файл резервной копии не найден.', 'danger')
            return redirect(url_for('admin.restore_database'))

        # Подтверждение восстановления
        confirm = form.get('confirm')
        if confirm != 'yes':
            await flash('Вы должны подтвердить восстановление базы данных.', 'warning')
            return redirect(url_for('admin.restore_database'))

        # Выполнение команды для восстановления базы данных
        db_name = os.getenv('DB_NAME')  # Используем переменные окружения
        db_user = os.getenv('DB_USER')
        db_password = os.getenv('DB_PASSWORD')

        try:
            # Устанавливаем переменную окружения для пароля
            env = os.environ.copy()
            env['PGPASSWORD'] = db_password

            # Команда для восстановления базы данных
            command = [
                'psql',
                '-U', db_user,
                '-d', db_name,
                '-f', backup_path
            ]

            # Выполняем команду восстановления
            result = subprocess.run(command, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                await flash('База данных успешно восстановлена из резервной копии.', 'success')
            else:
                logger.error(f"Ошибка при восстановлении базы данных: {result.stderr}")
                await flash('Ошибка при восстановлении базы данных.', 'danger')
        except Exception as e:
            logger.error(f"Исключение при восстановлении базы данных: {e}")
            await flash('Ошибка при восстановлении базы данных.', 'danger')

        return redirect(url_for('admin.admin_dashboard'))

    # GET-запрос: отображаем список доступных резервных копий
    backup_files = sorted(os.listdir(backup_dir), reverse=True)
    backup_files = [f for f in backup_files if f.endswith('.sql')]
    return await render_template('admin/restore_database.html', backup_files=backup_files)