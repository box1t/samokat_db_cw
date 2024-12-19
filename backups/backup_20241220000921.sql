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
    status character varying(50) DEFAULT 'active'::character varying,
    ride_comment text
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
ee1433fe-e6f7-4522-8a77-5da3cca11c4d	Central Park	40.785091	-73.968285
d4d70fee-f084-44d1-b974-a0a62c2ea07c	Times Square	40.758896	-73.985130
0ef6d10f-b066-4428-b6ea-a27a5c85605a	Brooklyn Bridge	40.706086	-73.996864
\.


--
-- Data for Name: rental_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.rental_history (history_id, rental_id, user_id, scooter_id, start_location_id, end_location_id, start_time, end_time, total_price, status, change_date, summary, ride_comment, rating) FROM stdin;
614a6467-36aa-4a01-ba42-1d4b3b68d488	e74452ca-fd16-48e0-955f-62199f7f2ef6	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	ee1433fe-e6f7-4522-8a77-5da3cca11c4d	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-18 19:47:09.438541	2024-12-18 20:47:09.438541	30.00	completed	2024-12-18 20:47:09.438541	Поездка завершена успешно.	Отличная поездка, самокат был в порядке!	5
967c524d-22f5-4042-b8bd-bb0cbc0e9eb8	e74452ca-fd16-48e0-955f-62199f7f2ef6	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	ee1433fe-e6f7-4522-8a77-5da3cca11c4d	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-18 19:46:52.120429	2024-12-18 20:46:52.120429	30.00	completed	2024-12-18 20:48:26.216864	Поездка завершена и добавлена в историю.	\N	\N
72d46d77-fee7-4fd3-b3a4-36c8907a6ad2	beaad8f1-57f5-4a1d-b798-003b7407c31c	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	0ef6d10f-b066-4428-b6ea-a27a5c85605a	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-19 19:01:58.917669	2024-12-19 19:13:11.214738	956.02	completed	2024-12-19 19:13:11.214738	Самокат 286fbf5a-5fad-4acf-8ab3-2cc5a30f953c. Поездка с 2024-12-19 19:01:58.917669 до 2024-12-19 19:13:11.214738. Начало: 0ef6d10f-b066-4428-b6ea-a27a5c85605a, Конец: d4d70fee-f084-44d1-b974-a0a62c2ea07c. Стоимость: 956.02 ₽.		\N
1868bb59-759e-46b7-864b-98d412ed77bc	18d0749c-e329-4b19-ad44-2b60e6a392d1	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-19 20:36:59.97529	2024-12-19 20:39:27.996629	912.34	completed	2024-12-19 20:39:27.996629	Самокат bf1044b4-f658-4568-a372-4a35dc7ae809. Поездка с 2024-12-19 20:36:59.97529 до 2024-12-19 20:39:27.996629. Начало: 0ef6d10f-b066-4428-b6ea-a27a5c85605a, Конец: d4d70fee-f084-44d1-b974-a0a62c2ea07c. Стоимость: 912.34 ₽.	hj	\N
\.


--
-- Data for Name: rentals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.rentals (rental_id, user_id, scooter_id, start_location_id, end_location_id, start_time, end_time, price_per_minute, total_price, distance_km, remaining_battery, status, ride_comment) FROM stdin;
e74452ca-fd16-48e0-955f-62199f7f2ef6	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	ee1433fe-e6f7-4522-8a77-5da3cca11c4d	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-18 19:46:52.120429	2024-12-18 20:46:52.120429	0.50	30.00	20.00	60	completed	\N
efd21de4-814f-412f-9366-e30a1464d5c1	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	6e6a3e53-2ce6-4c1b-8521-c88c9440eddf	d4d70fee-f084-44d1-b974-a0a62c2ea07c	\N	2024-12-18 20:46:52.120429	\N	0.80	\N	\N	70	active	\N
cdae883c-fda1-4672-bbdc-9ebe19af5cf0	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:03:24.285293	2024-12-19 16:21:39.444232	5.00	\N	0.00	\N	cancelled	\N
70dc7a05-c11a-4315-84e2-a0c3938fbd3e	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:21:40.838274	2024-12-19 16:21:47.686401	5.00	\N	0.00	\N	cancelled	\N
10fea402-39bb-4c56-9d92-19c04b8edace	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:21:59.366658	2024-12-19 16:22:05.535922	5.00	\N	0.00	\N	cancelled	\N
c17109b6-321f-4483-9b3b-4cf95d51de03	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:23:50.820594	2024-12-19 16:23:56.998498	5.00	\N	0.00	\N	cancelled	\N
be5eee24-98ec-465b-b38e-07ab562ed5f9	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:24:24.651209	2024-12-19 16:29:11.81022	5.00	\N	0.00	\N	cancelled	\N
8f645731-ffbc-42d8-a3d8-c781b941d9c1	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:29:12.714028	2024-12-19 16:29:13.316729	5.00	\N	0.00	\N	cancelled	\N
7d49bc5e-f7fa-4b6f-bf85-8a11e7f90880	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:29:15.444094	2024-12-19 16:29:16.909901	5.00	\N	0.00	\N	cancelled	\N
e5b914fb-8d76-4345-b540-a1ec73cde651	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:29:19.125894	2024-12-19 16:29:20.016607	5.00	\N	0.00	\N	cancelled	\N
395666a0-a3f1-44e8-96fb-6bbc28c1ef71	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:29:21.12469	2024-12-19 16:29:23.013768	5.00	\N	0.00	\N	cancelled	\N
8196be74-41f4-44ab-96a5-bb6cb3447aa3	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:29:30.410913	2024-12-19 16:29:31.680043	5.00	\N	0.00	\N	cancelled	\N
1221c201-890c-4280-88db-034dd88de309	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:30:51.526789	2024-12-19 16:31:00.136937	5.00	\N	0.00	\N	cancelled	\N
cfb9ef54-5afb-474a-84ab-84db408440d9	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 16:31:01.151856	2024-12-19 16:31:22.443173	5.00	\N	0.00	\N	cancelled	\N
531cd7ae-b2ad-4f3b-a77f-55a55b86509f	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	ee1433fe-e6f7-4522-8a77-5da3cca11c4d	\N	2024-12-18 22:23:49.580012	2024-12-19 16:51:35.907834	5.00	\N	0.00	\N	cancelled	\N
3f877e91-7353-4386-bd51-bd1b97ccdcde	9c785979-3277-439a-967a-dd4de554e419	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	ee1433fe-e6f7-4522-8a77-5da3cca11c4d	\N	2024-12-19 17:28:43.749992	\N	5.00	\N	0.00	\N	reserved	\N
69763335-deab-4f95-942e-32217a679625	9c785979-3277-439a-967a-dd4de554e419	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	ee1433fe-e6f7-4522-8a77-5da3cca11c4d	0ef6d10f-b066-4428-b6ea-a27a5c85605a	2024-12-19 18:57:02.484408	\N	5.00	\N	9.11	76	active	\N
33e62fdb-c159-49b5-a583-d9d2ed955905	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 19:01:44.568855	2024-12-19 19:08:58.820902	5.00	\N	0.00	\N	cancelled	\N
b163dafe-4e7f-4140-9b2d-d16c98ae535d	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	d4d70fee-f084-44d1-b974-a0a62c2ea07c	\N	2024-12-19 19:09:01.19828	\N	5.00	\N	0.00	\N	reserved	\N
beaad8f1-57f5-4a1d-b798-003b7407c31c	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	0ef6d10f-b066-4428-b6ea-a27a5c85605a	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-19 19:01:58.917669	2024-12-19 19:13:11.214738	5.00	956.02	5.95	67	completed	
c3f96c2d-1fb1-4fc9-ab30-ed18a0e47eb9	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	d4d70fee-f084-44d1-b974-a0a62c2ea07c	\N	2024-12-19 20:36:50.931208	\N	5.00	\N	0.00	\N	reserved	\N
e2efbb55-41ae-4b17-9b47-7a83a6637cf2	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	d4d70fee-f084-44d1-b974-a0a62c2ea07c	\N	2024-12-19 19:08:55.049115	2024-12-19 20:36:52.276049	5.00	\N	0.00	\N	cancelled	\N
2d98ef0d-e1b1-4089-8028-88291340503b	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	d774d73b-2909-4caa-bca7-524580dede76	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 20:36:53.383537	2024-12-19 20:36:54.457998	5.00	\N	0.00	\N	cancelled	\N
18a1c0dc-ac44-40be-b8b8-5a6153e70bb4	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 20:36:55.152616	\N	5.00	\N	0.00	\N	reserved	\N
5f0141a9-2a67-4020-8efc-785cd0b5d8ca	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	bf1044b4-f658-4568-a372-4a35dc7ae809	d4d70fee-f084-44d1-b974-a0a62c2ea07c	\N	2024-12-19 20:39:19.152262	\N	5.00	\N	0.00	\N	reserved	\N
18d0749c-e329-4b19-ad44-2b60e6a392d1	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	bf1044b4-f658-4568-a372-4a35dc7ae809	0ef6d10f-b066-4428-b6ea-a27a5c85605a	d4d70fee-f084-44d1-b974-a0a62c2ea07c	2024-12-19 20:36:59.97529	2024-12-19 20:39:27.996629	5.00	912.34	5.95	9	completed	hj
16401bb6-f1c2-4c26-bdc5-8c73981ba9e4	9c785979-3277-439a-967a-dd4de554e419	bf1044b4-f658-4568-a372-4a35dc7ae809	d4d70fee-f084-44d1-b974-a0a62c2ea07c	\N	2024-12-19 20:53:33.05255	2024-12-19 20:53:45.143863	5.00	\N	0.00	\N	cancelled	\N
4834edc3-eb54-411a-8243-c28ed9b6ed0f	9c785979-3277-439a-967a-dd4de554e419	d774d73b-2909-4caa-bca7-524580dede76	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 20:53:54.408671	2024-12-19 20:54:04.59186	5.00	\N	0.00	\N	cancelled	\N
a5cd4be2-9047-42f2-9e5c-a73a84a96f94	9c785979-3277-439a-967a-dd4de554e419	d774d73b-2909-4caa-bca7-524580dede76	0ef6d10f-b066-4428-b6ea-a27a5c85605a	\N	2024-12-19 20:54:07.853349	2024-12-19 20:54:16.295693	5.00	\N	0.00	\N	cancelled	\N
\.


--
-- Data for Name: reviews; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reviews (review_id, rental_id, scooter_id, user_id, rating, review_text, review_date) FROM stdin;
88d50827-a564-4294-85c8-76f0a0635e0e	614a6467-36aa-4a01-ba42-1d4b3b68d488	286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	5	Самокат был отличный, заряд хороший.	2024-12-18 20:49:21.774629
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

COPY public.scooters (scooter_id, model, battery_level, battery_consumption, speed_limit, location_id, status, last_maintenance_date) FROM stdin;
6e6a3e53-2ce6-4c1b-8521-c88c9440eddf	Model Y	75	1.80	25.00	d4d70fee-f084-44d1-b974-a0a62c2ea07c	on_maintenance	2024-12-18 20:45:56.821865
286fbf5a-5fad-4acf-8ab3-2cc5a30f953c	Model X	67	1.50	20.00	d4d70fee-f084-44d1-b974-a0a62c2ea07c	on_maintenance	2024-12-18 20:45:56.821865
bf1044b4-f658-4568-a372-4a35dc7ae809	1	9	4.00	44.00	d4d70fee-f084-44d1-b974-a0a62c2ea07c	available	2024-12-19 17:02:49.189354
d774d73b-2909-4caa-bca7-524580dede76	Model Z	50	2.00	15.00	0ef6d10f-b066-4428-b6ea-a27a5c85605a	available	2024-12-19 17:02:49.189354
d1a8a496-a7ed-4756-abe6-8a7d989f6199	1	32	12.00	31.00	0ef6d10f-b066-4428-b6ea-a27a5c85605a	available	2024-12-11 00:00:00
65187c7a-6f24-439c-b3d6-c1c7a9db200a	1	31	3.00	14.00	0ef6d10f-b066-4428-b6ea-a27a5c85605a	available	2024-12-19 00:00:00
\.


--
-- Data for Name: user_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_roles (user_id, role_id) FROM stdin;
fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	1
fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	2
9c785979-3277-439a-967a-dd4de554e419	1
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (user_id, username, hashed_password, email) FROM stdin;
fe8f8a9b-a60c-4033-9cb3-4d4c0230f4dd	kalik	$2b$12$7cG48Dol8ijSPtMhykLqhep6BA5D5Zs538uaDbbt./UJR/27T/4gW	kalik@mail
9c785979-3277-439a-967a-dd4de554e419	vova	$2b$12$7XxM2Q2pD2YHBQiRXse2Y.75emXUIHDoHxhuE6BUX.gst5FcfJ7Mu	vova@mail
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
    ADD CONSTRAINT fk_rentals_end_location FOREIGN KEY (end_location_id) REFERENCES public.locations(location_id);


--
-- Name: rentals fk_rentals_scooter; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_scooter FOREIGN KEY (scooter_id) REFERENCES public.scooters(scooter_id);


--
-- Name: rentals fk_rentals_start_location; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_start_location FOREIGN KEY (start_location_id) REFERENCES public.locations(location_id);


--
-- Name: rentals fk_rentals_user; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rentals
    ADD CONSTRAINT fk_rentals_user FOREIGN KEY (user_id) REFERENCES public.users(user_id);


--
-- Name: reviews fk_reviews_rentals; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT fk_reviews_rentals FOREIGN KEY (rental_id) REFERENCES public.rental_history(history_id) ON DELETE CASCADE;


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
-- PostgreSQL database dump complete
--

