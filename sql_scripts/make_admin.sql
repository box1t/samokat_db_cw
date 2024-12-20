-- 1. Присваиваем роли User и Admin существующему пользователю
DO $$
DECLARE
    user_role_id INT;
    admin_role_id INT;
    user_to_assign UUID;
BEGIN
    -- Запрашиваем ID пользователя
    SELECT user_id INTO user_to_assign FROM users WHERE username = 'user';

    IF user_to_assign IS NULL THEN
        RAISE EXCEPTION 'User not found';
    END IF;

    SELECT role_id INTO user_role_id FROM roles WHERE name = 'User';
    SELECT role_id INTO admin_role_id FROM roles WHERE name = 'Admin';

    IF user_role_id IS NULL OR admin_role_id IS NULL THEN
        RAISE EXCEPTION 'Roles User and/or Admin not found';
    END IF;

    -- Присваиваем роли User и Admin пользователю
    INSERT INTO user_roles (user_id, role_id)
    VALUES (user_to_assign, user_role_id), (user_to_assign, admin_role_id)
    ON CONFLICT DO NOTHING; -- Для предотвращения дублирования записей
END $$;
