--
-- PostgreSQL database dump
--

-- Dumped from database version 16.4 (Debian 16.4-1.pgdg120+1)
-- Dumped by pg_dump version 17.2 (Ubuntu 17.2-1.pgdg22.04+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: get_all_destinations_with_status(uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.get_all_destinations_with_status(scooter_id uuid) RETURNS TABLE(location_id uuid, location_name text, distance_km numeric, battery_needed numeric, is_accessible boolean)
    LANGUAGE plpgsql
    AS $_$
BEGIN
    RETURN QUERY
    SELECT 
        l.location_id,
        l.name::TEXT AS location_name, -- Явное приведение к TEXT
        haversine(sl.latitude, sl.longitude, l.latitude, l.longitude) AS distance_km,
        haversine(sl.latitude, sl.longitude, l.latitude, l.longitude) * sc.battery_consumption AS battery_needed,
        haversine(sl.latitude, sl.longitude, l.latitude, l.longitude) * sc.battery_consumption <= sc.battery_level AS is_accessible
    FROM locations l
    JOIN scooters sc ON sc.scooter_id = $1
    JOIN locations sl ON sc.location_id = sl.location_id;
END;
$_$;


ALTER FUNCTION public.get_all_destinations_with_status(scooter_id uuid) OWNER TO postgres;

--
-- Name: get_average_scooter_rating(uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.get_average_scooter_rating(scooter_id_param uuid) RETURNS numeric
    LANGUAGE plpgsql
    AS $$
BEGIN
    RETURN (
        SELECT COALESCE(AVG(rating), 0) -- Возвращает 0, если отзывов нет
        FROM reviews
        WHERE scooter_id = scooter_id_param
    );
END;
$$;


ALTER FUNCTION public.get_average_scooter_rating(scooter_id_param uuid) OWNER TO postgres;

--
-- Name: haversine(numeric, numeric, numeric, numeric); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.haversine(lat1 numeric, lon1 numeric, lat2 numeric, lon2 numeric) RETURNS numeric
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
    R CONSTANT NUMERIC := 6371; -- Радиус Земли в километрах
    dlat NUMERIC;
    dlon NUMERIC;
    a NUMERIC;
    c NUMERIC;
BEGIN
    dlat := radians(lat2 - lat1);
    dlon := radians(lon2 - lon1);

    a := sin(dlat / 2) ^ 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ^ 2;
    c := 2 * atan2(sqrt(a), sqrt(1 - a));

    RETURN R * c; -- Расстояние в километрах
END;
$$;


ALTER FUNCTION public.haversine(lat1 numeric, lon1 numeric, lat2 numeric, lon2 numeric) OWNER TO postgres;

--
-- Name: log_rental_history(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.log_rental_history() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    history_id UUID := uuid_generate_v4();
    summary_text TEXT;
BEGIN
    summary_text := FORMAT(
        'Самокат %s. Поездка с %s до %s. Начало: %s, Конец: %s. Стоимость: %s ₽.',
        NEW.scooter_id,
        NEW.start_time::text,
        NEW.end_time::text,
        NEW.start_location_id,
        NEW.end_location_id,
        TO_CHAR(NEW.total_price, 'FM9999990.00')
    );

    INSERT INTO rental_history (
        history_id, rental_id, user_id, scooter_id, start_location_id,
        end_location_id, start_time, end_time, total_price, status, change_date,
        summary, ride_comment
    )
    VALUES (
        history_id, NEW.rental_id, NEW.user_id, NEW.scooter_id, NEW.start_location_id,
        NEW.end_location_id, NEW.start_time, NEW.end_time, NEW.total_price,
        NEW.status, NOW(), summary_text, NEW.ride_comment
    );

    RETURN NEW;
END;
$$;


ALTER FUNCTION public.log_rental_history() OWNER TO postgres;

--
-- Name: process_rental(uuid, uuid, text, uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.process_rental(in_uid uuid, in_scooter_id uuid, in_action text, in_end_location uuid) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    scooter_record scooters%ROWTYPE;
    rental_record rentals%ROWTYPE;
    trip_distance_km NUMERIC;
    battery_needed NUMERIC;
    out_rental_id UUID;
BEGIN
    SELECT s.*
      INTO scooter_record
      FROM scooters s
     WHERE s.scooter_id = in_scooter_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Самокат не найден.';
    END IF;

    IF in_action = 'rent' THEN
        SELECT r.*
          INTO rental_record
          FROM rentals r
         WHERE r.user_id = in_uid
           AND r.scooter_id = in_scooter_id
           AND r.status = 'reserved';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Самокат не забронирован текущим пользователем.';
        END IF;

        UPDATE rentals
           SET status = 'active',
               start_time = NOW()
         WHERE rental_id = rental_record.rental_id;

        UPDATE scooters
           SET status = 'in_use'
         WHERE scooter_id = in_scooter_id;

        out_rental_id := rental_record.rental_id;

    ELSIF in_action = 'continue' THEN
        SELECT r.*
          INTO rental_record
          FROM rentals r
         WHERE r.user_id = in_uid
           AND r.scooter_id = in_scooter_id
           AND r.status = 'active';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Активная аренда не найдена.';
        END IF;

        IF in_end_location IS NULL THEN
            RAISE EXCEPTION 'Не указана конечная локация для продолжения поездки.';
        END IF;

        SELECT haversine(l1.latitude, l1.longitude, l2.latitude, l2.longitude)
          INTO trip_distance_km
          FROM locations l1, locations l2
         WHERE l1.location_id = rental_record.end_location_id
           AND l2.location_id = in_end_location;

        battery_needed := trip_distance_km * scooter_record.battery_consumption;

        IF scooter_record.battery_level < battery_needed THEN
            RAISE EXCEPTION 'Недостаточно заряда для поездки.';
        END IF;

        UPDATE rentals
           SET distance_km = COALESCE(distance_km, 0) + trip_distance_km,
               end_location_id = in_end_location,
               remaining_battery = scooter_record.battery_level - battery_needed
         WHERE rental_id = rental_record.rental_id;

        UPDATE scooters
           SET battery_level = battery_level - battery_needed,
               location_id = in_end_location
         WHERE scooter_id = in_scooter_id;

        out_rental_id := rental_record.rental_id;

    ELSE
        RAISE EXCEPTION 'Неизвестное действие: %', in_action;
    END IF;

    RETURN out_rental_id;
END;
$$;


ALTER FUNCTION public.process_rental(in_uid uuid, in_scooter_id uuid, in_action text, in_end_location uuid) OWNER TO postgres;

--
-- Name: process_rental_action(uuid, uuid, text, uuid); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.process_rental_action(uid uuid, scooter_id uuid, action text, end_location uuid) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE
    scooter scooters%ROWTYPE;
    rental rentals%ROWTYPE;
    distance_km NUMERIC;
    battery_needed NUMERIC;
    rental_id UUID;
BEGIN
    -- Получаем и блокируем запись о самокате для исключения конкурентных изменений
    SELECT * INTO scooter
    FROM scooters s
    WHERE s.scooter_id = scooter_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Самокат не найден.';
    END IF;

    IF action = 'rent' THEN
        SELECT * INTO rental
        FROM rentals
        WHERE user_id = uid AND scooter_id = scooter.scooter_id AND status = 'reserved';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Самокат не забронирован текущим пользователем.';
        END IF;

        -- Переводим аренду в активное состояние
        UPDATE rentals
        SET status = 'active',
            start_time = NOW(),
            end_location_id = CASE WHEN end_location IS NOT NULL THEN end_location_id ELSE end_location_id END
        WHERE rental_id = rental.rental_id;

        -- Обновляем статус самоката
        UPDATE scooters SET status = 'in_use' WHERE scooter_id = scooter.scooter_id;

        rental_id := rental.rental_id;

    ELSIF action = 'continue' THEN
        SELECT * INTO rental
        FROM rentals
        WHERE user_id = uid AND scooter_id = scooter.scooter_id AND status = 'active';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Активная аренда не найдена.';
        END IF;

        IF end_location IS NULL THEN
            RAISE EXCEPTION 'Не указана конечная локация для продолжения поездки.';
        END IF;

        -- Рассчитываем расстояние от предыдущей конечной точки до новой конечной точки
        SELECT haversine(l1.latitude, l1.longitude, l2.latitude, l2.longitude) INTO distance_km
        FROM locations l1, locations l2
        WHERE l1.location_id = rental.end_location_id AND l2.location_id = end_location;

        battery_needed := distance_km * scooter.battery_consumption;
        IF scooter.battery_level < battery_needed THEN
            RAISE EXCEPTION 'Недостаточно заряда для поездки.';
        END IF;

        -- Обновляем аренду, увеличивая пройденную дистанцию и меняя конечную локацию
        UPDATE rentals
        SET distance_km = COALESCE(distance_km, 0) + distance_km,
            end_location_id = end_location,
            remaining_battery = scooter.battery_level - battery_needed
        WHERE rental_id = rental.rental_id;

        -- Обновляем самокат: уменьшаем заряд, меняем его текущую локацию
        UPDATE scooters
        SET battery_level = battery_level - battery_needed,
            location_id = end_location
        WHERE scooter_id = scooter.scooter_id;

        rental_id := rental.rental_id;

    ELSE
        RAISE EXCEPTION 'Неизвестное действие: %', action;
    END IF;

    RETURN rental_id;
END;
$$;


ALTER FUNCTION public.process_rental_action(uid uuid, scooter_id uuid, action text, end_location uuid) OWNER TO postgres;

--
-- Name: process_rental_action(uuid, uuid, character varying, uuid); Type: PROCEDURE; Schema: public; Owner: postgres
--

CREATE PROCEDURE public.process_rental_action(OUT rental_id uuid, IN uid uuid, IN scooter_id uuid, IN action character varying, IN end_location uuid DEFAULT NULL::uuid)
    LANGUAGE plpgsql
    AS $$
DECLARE
    scooter RECORD;
    rental RECORD;
    distance_km NUMERIC;
    battery_needed NUMERIC;
BEGIN
    -- Получаем информацию о самокате
    SELECT * INTO scooter
    FROM scooters s
    WHERE s.scooter_id = scooter_id FOR UPDATE;

    IF scooter IS NULL THEN
        RAISE EXCEPTION 'Самокат не найден.';
    END IF;

    -- Если действие - "rent"
    IF action = 'rent' THEN
        SELECT * INTO rental
        FROM rentals
        WHERE user_id = uid AND scooter_id = scooter.scooter_id AND status = 'reserved';

        IF rental IS NULL THEN
            RAISE EXCEPTION 'Самокат не забронирован текущим пользователем.';
        END IF;

        UPDATE rentals
        SET status = 'active', start_time = NOW()
        WHERE rental_id = rental.rental_id;

        UPDATE scooters SET status = 'in_use' WHERE scooter_id = scooter.scooter_id;

        rental_id := rental.rental_id;

    -- Если действие - "continue"
    ELSIF action = 'continue' THEN
        SELECT * INTO rental
        FROM rentals
        WHERE user_id = uid AND scooter_id = scooter.scooter_id AND status = 'active';

        IF rental IS NULL THEN
            RAISE EXCEPTION 'Активная аренда не найдена.';
        END IF;

        SELECT haversine(l1.latitude, l1.longitude, l2.latitude, l2.longitude) INTO distance_km
        FROM locations l1, locations l2
        WHERE l1.location_id = rental.end_location_id AND l2.location_id = end_location;

        battery_needed := distance_km * scooter.battery_consumption;
        IF scooter.battery_level < battery_needed THEN
            RAISE EXCEPTION 'Недостаточно заряда для поездки.';
        END IF;

        UPDATE rentals
        SET distance_km = distance_km + COALESCE(rental.distance_km, 0),
            end_location_id = end_location,
            remaining_battery = scooter.battery_level - battery_needed
        WHERE rental_id = rental.rental_id;

        UPDATE scooters
        SET battery_level = battery_level - battery_needed,
            location_id = end_location
        WHERE scooter_id = scooter.scooter_id;

        rental_id := rental.rental_id;

    ELSE
        RAISE EXCEPTION 'Неизвестное действие: %', action;
    END IF;
END;
$$;


ALTER PROCEDURE public.process_rental_action(OUT rental_id uuid, IN uid uuid, IN scooter_id uuid, IN action character varying, IN end_location uuid) OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: locations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.locations (
    location_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(100) NOT NULL,
    latitude numeric(9,6) NOT NULL,
    longitude numeric(9,6) NOT NULL
);


ALTER TABLE public.locations OWNER TO postgres;

--
-- Name: rental_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rental_history (
    history_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    rental_id uuid NOT NULL,
    user_id uuid NOT NULL,
    scooter_id uuid NOT NULL,
    start_location_id uuid NOT NULL,
    end_location_id uuid,
    start_time timestamp without time zone,
    end_time timestamp without time zone,
    total_price numeric(10,2),
    status character varying(50),
    change_date timestamp without time zone DEFAULT now(),
    summary text,
    ride_comment text,
    rating integer,
    CONSTRAINT rental_history_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


ALTER TABLE public.rental_history OWNER TO postgres;

--
-- Name: rentals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rentals (
    rental_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    scooter_id uuid NOT NULL,
    start_location_id uuid NOT NULL,
    end_location_id uuid,
    start_time timestamp without time zone DEFAULT now(),
    end_time timestamp without time zone,
    price_per_minute numeric(10,2) NOT NULL,
    total_price numeric(10,2),
    distance_km numeric(10,2) DEFAULT 0.0,
    remaining_battery integer,
    ride_comment text,
    status character varying(50) DEFAULT 'active'::character varying
);


ALTER TABLE public.rentals OWNER TO postgres;

--
-- Name: reviews; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reviews (
    review_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    rental_id uuid NOT NULL,
    scooter_id uuid NOT NULL,
    user_id uuid NOT NULL,
    rating integer NOT NULL,
    review_text text,
    review_date timestamp without time zone DEFAULT now(),
    CONSTRAINT reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


ALTER TABLE public.reviews OWNER TO postgres;

--
-- Name: roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.roles (
    role_id integer NOT NULL,
    name character varying(50) NOT NULL
);


ALTER TABLE public.roles OWNER TO postgres;

--
-- Name: roles_role_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.roles_role_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.roles_role_id_seq OWNER TO postgres;

--
-- Name: roles_role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.roles_role_id_seq OWNED BY public.roles.role_id;


--
-- Name: scooters; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scooters (
    scooter_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    model character varying(150) NOT NULL,
    battery_level integer NOT NULL,
    battery_consumption numeric(5,2) DEFAULT 1.5,
    speed_limit numeric(4,2) DEFAULT 20.0,
    location_id uuid,
    status character varying(50) DEFAULT 'available'::character varying,
    last_maintenance_date timestamp without time zone,
    reserved_by_user uuid,
    CONSTRAINT scooters_battery_level_check CHECK (((battery_level >= 0) AND (battery_level <= 100)))
);


ALTER TABLE public.scooters OWNER TO postgres;

--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    role_id integer NOT NULL
);


ALTER TABLE public.user_roles OWNER TO postgres;

--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    user_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    username character varying(50) NOT NULL,
    hashed_password text NOT NULL,
    email character varying(100) NOT NULL
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: roles role_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.roles ALTER COLUMN role_id SET DEFAULT nextval('public.roles_role_id_seq'::regclass);


--
-- Data for Name: locations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.locations (location_id, name, latitude, longitude) FROM stdin;
efe787fb-2daa-4d8d-93d7-13c51ff7b990	Север	30.000000	30.000000
03905791-ef2f-4f24-ac1f-b3b9a58fdfd9	Юг	30.300000	30.300000
d62d2152-f4ce-47fd-a6db-c8804e59026f	Запад	30.400000	30.400000
197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	Восток	30.100000	30.100000
\.


--
-- Data for Name: rental_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.rental_history (history_id, rental_id, user_id, scooter_id, start_location_id, end_location_id, start_time, end_time, total_price, status, change_date, summary, ride_comment, rating) FROM stdin;
cb3e9731-fafd-4fea-999c-ed71f5b270a3	817bf88d-8415-4475-9766-b704c18cf13f	0ed039f0-0cb4-4130-ba11-ce79e352c5a5	a0e9fc78-96fe-46d9-9af6-81e05c6306a4	efe787fb-2daa-4d8d-93d7-13c51ff7b990	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	2024-12-20 13:37:41.410557	2024-12-20 13:38:25.288046	\N	completed	2024-12-20 13:38:25.288046	Самокат a0e9fc78-96fe-46d9-9af6-81e05c6306a4. Поездка с 2024-12-20 13:37:41.410557 до 2024-12-20 13:38:25.288046. Начало: efe787fb-2daa-4d8d-93d7-13c51ff7b990, Конец: 197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3. Стоимость:  ₽.	123	\N
\.


--
-- Data for Name: rentals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.rentals (rental_id, user_id, scooter_id, start_location_id, end_location_id, start_time, end_time, price_per_minute, total_price, distance_km, remaining_battery, ride_comment, status) FROM stdin;
817bf88d-8415-4475-9766-b704c18cf13f	0ed039f0-0cb4-4130-ba11-ce79e352c5a5	a0e9fc78-96fe-46d9-9af6-81e05c6306a4	efe787fb-2daa-4d8d-93d7-13c51ff7b990	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	2024-12-20 13:37:41.410557	2024-12-20 13:38:25.288046	5.00	\N	14.71	29	123	completed
\.


--
-- Data for Name: reviews; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reviews (review_id, rental_id, scooter_id, user_id, rating, review_text, review_date) FROM stdin;
e94a27f3-fac0-4f47-b64f-6f354843c01f	817bf88d-8415-4475-9766-b704c18cf13f	a0e9fc78-96fe-46d9-9af6-81e05c6306a4	0ed039f0-0cb4-4130-ba11-ce79e352c5a5	5	rrr	2024-12-20 13:38:30.600831
\.


--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.roles (role_id, name) FROM stdin;
1	User
2	Admin
\.


--
-- Data for Name: scooters; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.scooters (scooter_id, model, battery_level, battery_consumption, speed_limit, location_id, status, last_maintenance_date, reserved_by_user) FROM stdin;
d8083123-a6d2-41b7-bc7b-6a0d81ccee4c	43	70	2.00	44.00	03905791-ef2f-4f24-ac1f-b3b9a58fdfd9	in_use	2024-12-09 00:00:00	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
de86aefa-f044-4224-835f-bb617d6be2c8	Model D	100	1.70	22.00	efe787fb-2daa-4d8d-93d7-13c51ff7b990	on_maintenance	2024-12-20 07:49:20.576898	\N
edf28443-7384-4dea-9905-923d4aadfef3	Model C	100	1.60	24.00	efe787fb-2daa-4d8d-93d7-13c51ff7b990	on_maintenance	2024-12-20 07:49:20.576898	\N
e759db84-7c51-4f17-af14-86a11a05a5b4	Model H	100	1.60	24.50	efe787fb-2daa-4d8d-93d7-13c51ff7b990	on_maintenance	2024-12-20 07:49:20.576898	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
fd2efa93-c67c-4d48-a656-837bd102520a	42	100	3.00	54.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	on_maintenance	2024-12-20 13:36:59.915145	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
31b53b23-2162-44e3-a551-e21c4878ec94	Model F	100	1.30	26.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	on_maintenance	2024-12-20 13:36:59.915145	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
c79fcb3a-0a03-49b6-b72b-1afabe454643	132	100	1.00	44.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	on_maintenance	2024-12-20 13:36:59.915145	\N
7dd186bb-e8b1-4ee9-bc35-49c4e31f254d	Model G	100	1.40	23.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	on_maintenance	2024-12-20 13:36:59.915145	\N
93623b51-1cc7-4251-a58f-591c58f9bb23	Model I	100	1.70	21.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	on_maintenance	2024-12-20 13:36:59.915145	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
fd871239-8aa9-4c08-b9d2-8adbdb8c3546	Model E	100	1.50	20.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	on_maintenance	2024-12-20 13:36:59.915145	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
4bf5231b-427d-4cb9-929a-0c0bac508b31	23	100	1.00	44.00	d62d2152-f4ce-47fd-a6db-c8804e59026f	available	2024-12-20 13:36:59.915145	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
5a2a2a32-4f3d-4bbb-b2f3-ae9af5662101	Model B	100	1.40	23.00	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	on_maintenance	2024-12-20 13:45:27.043645	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
8141cf08-ac67-4f39-a2d5-ba3e8566f12e	Model A	100	1.50	25.00	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	on_maintenance	2024-12-20 13:45:27.043645	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
e0305cef-07f5-499a-b036-4a46f8e38b55	424	100	12.00	44.00	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	on_maintenance	2024-12-20 13:45:27.043645	\N
9eff769b-29c4-43db-bb3e-3b4ecc9503d9	Model3	100	3.00	31.00	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	on_maintenance	2024-12-20 13:45:27.043645	\N
a0e9fc78-96fe-46d9-9af6-81e05c6306a4	54	100	4.00	24.00	197ef1e7-4cd3-4e63-8cfa-e1e388e16ec3	available	2024-12-20 13:45:27.043645	\N
330d6031-5563-424e-967d-0d062ac37ee3	Model J	77	1.50	25.00	efe787fb-2daa-4d8d-93d7-13c51ff7b990	on_maintenance	2024-12-20 07:39:31.489238	0ed039f0-0cb4-4130-ba11-ce79e352c5a5
\.


--
-- Data for Name: user_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_roles (user_id, role_id) FROM stdin;
0ed039f0-0cb4-4130-ba11-ce79e352c5a5	1
0ed039f0-0cb4-4130-ba11-ce79e352c5a5	2
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (user_id, username, hashed_password, email) FROM stdin;
0ed039f0-0cb4-4130-ba11-ce79e352c5a5	user	$2b$12$B1gpyhjuXxgrDx76Yxz.lORUOz9BC1nelPQq6kAE/hEFyDfhHjo92	user@mail
\.


--
-- Name: roles_role_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.roles_role_id_seq', 2, true);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (location_id);


--
-- Name: rental_history rental_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rental_history
    ADD CONSTRAINT rental_history_pkey PRIMARY KEY (history_id);


--
-- Name: rentals rentals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT rentals_pkey PRIMARY KEY (rental_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (review_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (role_id);


--
-- Name: scooters scooters_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scooters
    ADD CONSTRAINT scooters_pkey PRIMARY KEY (scooter_id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: rentals rental_history_trigger; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER rental_history_trigger AFTER UPDATE OF status ON public.rentals FOR EACH ROW WHEN (((new.status)::text = 'completed'::text)) EXECUTE FUNCTION public.log_rental_history();


--
-- Name: rental_history fk_rental_history_rentals; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rental_history
    ADD CONSTRAINT fk_rental_history_rentals FOREIGN KEY (rental_id) REFERENCES public.rentals(rental_id) ON DELETE CASCADE;


--
-- Name: rentals fk_rentals_end_location; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_end_location FOREIGN KEY (end_location_id) REFERENCES public.locations(location_id) ON DELETE CASCADE;


--
-- Name: rentals fk_rentals_scooter; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_scooter FOREIGN KEY (scooter_id) REFERENCES public.scooters(scooter_id) ON DELETE CASCADE;


--
-- Name: rentals fk_rentals_start_location; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_start_location FOREIGN KEY (start_location_id) REFERENCES public.locations(location_id) ON DELETE CASCADE;


--
-- Name: rentals fk_rentals_user; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_user FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: reviews fk_reviews_rentals; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT fk_reviews_rentals FOREIGN KEY (rental_id) REFERENCES public.rentals(rental_id) ON DELETE CASCADE;


--
-- Name: reviews fk_reviews_scooters; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT fk_reviews_scooters FOREIGN KEY (scooter_id) REFERENCES public.scooters(scooter_id) ON DELETE CASCADE;


--
-- Name: reviews fk_reviews_users; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT fk_reviews_users FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: scooters fk_scooters_locations; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scooters
    ADD CONSTRAINT fk_scooters_locations FOREIGN KEY (location_id) REFERENCES public.locations(location_id) ON DELETE SET NULL;


--
-- Name: user_roles fk_user_roles_roles; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_roles FOREIGN KEY (role_id) REFERENCES public.roles(role_id) ON DELETE CASCADE;


--
-- Name: user_roles fk_user_roles_users; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_users FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: scooters scooters_reserved_by_user_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scooters
    ADD CONSTRAINT scooters_reserved_by_user_fkey FOREIGN KEY (reserved_by_user) REFERENCES public.users(user_id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

