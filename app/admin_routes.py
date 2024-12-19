from quart import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, g
from app.db import *
import os

from app.utils import *
from dotenv import load_dotenv
import glob
import subprocess
from datetime import datetime

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

@admin.route('/manage_locations', methods=['GET', 'POST'])
@admin_required
async def manage_locations():
    """
    Управление локациями: просмотр, добавление, редактирование, удаление.
    """
    if request.method == 'POST':
        form = await request.form
        action = form.get('action')

        if action == 'add':
            name = form.get('name')
            latitude = float(form.get('latitude'))
            longitude = float(form.get('longitude'))
            if await is_duplicate_location(current_app.db_pool, name):
                await flash('Локация с таким именем уже существует.', 'danger')
                return redirect(url_for('admin.manage_locations'))
            await add_location(current_app.db_pool, name, latitude, longitude)
            await flash('Локация добавлена.', 'success')

        elif action == 'edit':
            location_id = form.get('location_id')
            name = form.get('name')
            latitude = float(form.get('latitude'))
            longitude = float(form.get('longitude'))
            if await is_duplicate_location(current_app.db_pool, name, location_id):
                await flash('Локация с таким именем уже существует.', 'danger')
                return redirect(url_for('admin.manage_locations'))
            await update_location(current_app.db_pool, location_id, name, latitude, longitude)
            await flash('Локация обновлена.', 'success')

        elif action == 'delete':
            location_id = form.get('location_id')
            await delete_location(current_app.db_pool, location_id)
            await flash('Локация удалена.', 'success')

        return redirect(url_for('admin.manage_locations'))

    # Получаем все локации для отображения
    locations = await get_all_locations(current_app.db_pool)
    return await render_template('admin/manage_locations.html', locations=locations)

@admin.route('/manage_scooters', methods=['GET', 'POST'])
@admin_required
async def manage_scooters():
    """
    Управление самокатами: просмотр, обслуживание и изменение статуса.
    """
    if request.method == 'POST':
        form = await request.form
        action = form.get('action')

        if action == 'service':
            # Обслужить все самокаты в выбранной локации
            location_id = form.get('location_id')
            await service_scooters_in_location(current_app.db_pool, location_id)
            await flash('Самокаты в локации обслужены и переведены в статус "on_maintenance".', 'success')
        
        elif action == 'update_status':
            # Обновить статус конкретного самоката
            scooter_id = form.get('scooter_id')
            status = form.get('status')  
            await update_scooter_status(current_app.db_pool, scooter_id, status)
            await flash(f'Статус самоката обновлен: {status}.', 'success')

        elif action == 'edit':
            # Редактирование существующего самоката
            scooter_id = form.get('scooter_id')
            model = form.get('model')
            battery_level = int(form.get('battery_level'))
            status = form.get('status', 'available')
            location_id = form.get('location_id') or None
            battery_consumption = float(form.get('battery_consumption', 1.5))
            speed_limit = float(form.get('speed_limit', 20.0))
            last_maintenance_date = form.get('last_maintenance_date') or None

            # Преобразование строки даты в объект datetime.date
            if last_maintenance_date:
                last_maintenance_date = datetime.strptime(last_maintenance_date, '%Y-%m-%d').date()


            if await is_duplicate_scooter_characteristics(
                current_app.db_pool, model, speed_limit, battery_consumption, scooter_id
            ):
                await flash('У этой модели уже существуют такие характеристики скорости и расхода электричества.', 'error')
                return redirect(url_for('admin.manage_scooters'))


            await update_scooter(
                current_app.db_pool, scooter_id, model, battery_level, status,
                location_id, last_maintenance_date, battery_consumption, speed_limit
            )
            await flash('Информация о самокате обновлена.', 'success')

        elif action == 'delete':
            # Удаление самоката
            scooter_id = form.get('scooter_id')
            await delete_scooter(current_app.db_pool, scooter_id)
            await flash('Самокат удален.', 'success')

        elif action == 'add':
            # Добавление нового самоката
            model = form.get('model')
            battery_level = int(form.get('battery_level'))
            status = form.get('status', 'available')
            location_id = form.get('location_id') or None
            battery_consumption = float(form.get('battery_consumption', 1.5))
            speed_limit = float(form.get('speed_limit', 20.0))
            last_maintenance_date = form.get('last_maintenance_date') or None

            # Преобразование строки даты в объект datetime.date
            if last_maintenance_date:
                last_maintenance_date = datetime.strptime(last_maintenance_date, '%Y-%m-%d').date()


            await add_scooter(
                current_app.db_pool, model, battery_level, status, location_id,
                battery_consumption, speed_limit, last_maintenance_date
            )
            await flash('Новый самокат добавлен.', 'success')

        return redirect(url_for('admin.manage_scooters'))

    # Получение всех самокатов с сортировкой по заряду и локации
    scooters = await get_all_scooters_sorted(current_app.db_pool)
    locations = await get_all_locations(current_app.db_pool)
    locations_battery_counts = await get_low_battery_scooters_by_location(current_app.db_pool)

    return await render_template(
        'admin/manage_scooters.html',
        scooters=scooters,
        locations=locations,
        locations_battery_counts=locations_battery_counts
    )

# вместо order - rental status
@admin.route('/manage_rentals', methods=['GET', 'POST'])
@admin_required
async def manage_rentals():
    if request.method == 'POST':
        form = await request.form
        order_id = form.get('order_id')
        new_status = form.get('status')

        if order_id and new_status:
            try:
                await update_rental_status(current_app.db_pool, order_id, new_status)
                await flash('Статус аренды обновлен.', 'success')
            except Exception as e:
                current_app.logger.error(f"Ошибка при обновлении статуса аренды: {e}")
                await flash('Ошибка при обновлении статуса аренды.', 'danger')
        return redirect(url_for('admin.manage_rentals'))

    # GET-запрос: отображаем список всех аренд
    orders = await get_all_rentals(current_app.db_pool)

    # Опционально: получение аналитики
    # Допустим, мы хотим видеть статистику по определенному самокату, если указан scooter_id в GET параметрах
    scooter_id = request.args.get('scooter_id')
    scooter_stats = None
    if scooter_id:
        rental_count = await get_rental_count_by_scooter(current_app.db_pool, scooter_id)
        avg_duration = await get_avg_rental_duration_by_scooter(current_app.db_pool, scooter_id)
        scooter_stats = {
            'scooter_id': scooter_id,
            'rental_count': rental_count,
            'avg_duration': round(avg_duration or 0, 2)
        }

    # Можно также вывести общую метрику: например, общее количество аренд:
    total_rentals = len(orders)  # Поскольку get_all_rentals возвращает список, можно взять длину

    return await render_template(
        'admin/manage_rentals.html',
        orders=orders,
        total_rentals=total_rentals,
        scooter_stats=scooter_stats
    )




######################################################################
                            #Backup/Restore db
######################################################################


@admin.route('/backup', methods=['GET'])
@admin_required
async def backup_database():
    """
    Резервное копирование базы данных.
    """
    import subprocess

    # Путь к резервной копии
    backup_dir = '/home/snowwy/Desktop/MAI/samokat_db_cw/samokat_db_cw/backups/'
    os.makedirs(backup_dir, exist_ok=True)
    backup_file = os.path.join(backup_dir, f'backup_{datetime.now().strftime("%Y%m%d%H%M%S")}.sql')

    # Команда для резервного копирования
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if not all([db_name, db_user, db_password]):
        await flash('Переменные окружения для базы данных не настроены.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    command = f'PGPASSWORD="{db_password}" pg_dump -h localhost -U {db_user} {db_name} > {backup_file}'

    try:
        result = subprocess.run(command, shell=True, check=True, stderr=subprocess.PIPE)
        logger.info(f'Резервная копия создана: {backup_file}')
        await flash(f'Резервная копия создана: {backup_file}', 'success')
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при создании резервной копии: {e.stderr.decode()}")
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
                logger.info(f'База данных успешно восстановлена из резервной копии.')
                await flash('База данных успешно восстановлена из резервной копии.', 'success')
            else:
                logger.error(f"Ошибка при восстановлении базы данных: {result.stderr}")
                await flash('Ошибка при восстановлении базы данных.', 'danger')
        except Exception as e:
            logger.error(f"Исключение при восстановлении базы данных: {e}")
            await flash('Исключение  при восстановлении базы данных.', 'danger')

        return redirect(url_for('admin.admin_dashboard'))

    # GET-запрос: отображаем список доступных резервных копий
    backup_files = sorted(os.listdir(backup_dir), reverse=True)
    backup_files = [f for f in backup_files if f.endswith('.sql')]
    return await render_template('admin/restore_database.html', backup_files=backup_files)