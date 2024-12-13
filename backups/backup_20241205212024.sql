--
-- PostgreSQL database dump
--

-- Dumped from database version 14.13 (Ubuntu 14.13-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.13 (Ubuntu 14.13-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
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


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: cart; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.cart (
    user_id uuid NOT NULL,
    product_id uuid NOT NULL,
    quantity integer NOT NULL
);


ALTER TABLE public.cart OWNER TO project_user;

--
-- Name: categories; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.categories (
    category_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(100) NOT NULL
);


ALTER TABLE public.categories OWNER TO project_user;

--
-- Name: order_history; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.order_history (
    history_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    order_id uuid NOT NULL,
    status character varying(50) NOT NULL,
    change_date timestamp without time zone DEFAULT now()
);


ALTER TABLE public.order_history OWNER TO project_user;

--
-- Name: order_items; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.order_items (
    order_id uuid NOT NULL,
    product_id uuid NOT NULL,
    quantity integer NOT NULL,
    price numeric(10,2) NOT NULL
);


ALTER TABLE public.order_items OWNER TO project_user;

--
-- Name: orders; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.orders (
    order_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    user_id uuid NOT NULL,
    order_date timestamp without time zone DEFAULT now(),
    status character varying(50) NOT NULL,
    total_cost numeric(10,2) NOT NULL
);


ALTER TABLE public.orders OWNER TO project_user;

--
-- Name: products; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.products (
    product_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    name character varying(150) NOT NULL,
    description text,
    category_id uuid,
    price numeric(10,2) NOT NULL,
    stock integer NOT NULL,
    manufacturer character varying(150)
);


ALTER TABLE public.products OWNER TO project_user;

--
-- Name: reviews; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.reviews (
    review_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    product_id uuid NOT NULL,
    user_id uuid NOT NULL,
    rating integer NOT NULL,
    comment text,
    review_date timestamp without time zone DEFAULT now(),
    CONSTRAINT reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


ALTER TABLE public.reviews OWNER TO project_user;

--
-- Name: roles; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.roles (
    role_id integer NOT NULL,
    name character varying(50) NOT NULL
);


ALTER TABLE public.roles OWNER TO project_user;

--
-- Name: roles_role_id_seq; Type: SEQUENCE; Schema: public; Owner: project_user
--

CREATE SEQUENCE public.roles_role_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.roles_role_id_seq OWNER TO project_user;

--
-- Name: roles_role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: project_user
--

ALTER SEQUENCE public.roles_role_id_seq OWNED BY public.roles.role_id;


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.user_roles (
    user_id uuid NOT NULL,
    role_id integer NOT NULL
);


ALTER TABLE public.user_roles OWNER TO project_user;

--
-- Name: users; Type: TABLE; Schema: public; Owner: project_user
--

CREATE TABLE public.users (
    user_id uuid DEFAULT public.uuid_generate_v4() NOT NULL,
    username character varying(50) NOT NULL,
    hashed_password text NOT NULL,
    email character varying(100) NOT NULL
);


ALTER TABLE public.users OWNER TO project_user;

--
-- Name: roles role_id; Type: DEFAULT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.roles ALTER COLUMN role_id SET DEFAULT nextval('public.roles_role_id_seq'::regclass);


--
-- Data for Name: cart; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.cart (user_id, product_id, quantity) FROM stdin;
\.


--
-- Data for Name: categories; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.categories (category_id, name) FROM stdin;
58ec2643-a385-4b72-9d5a-58b2bafba9f3	Шлема
d6f9cc87-fb33-48ef-84ab-1000f7cb851d	Бронежилеты
e5440dbf-2d74-4f0c-a083-8e8ae4270336	Прицельные комплексы
\.


--
-- Data for Name: order_history; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.order_history (history_id, order_id, status, change_date) FROM stdin;
22117e83-46da-4e05-a450-aa8e459c3a9c	abc7e945-2aab-4ab1-b7fb-598398da56be	Pending	2024-11-27 20:53:56.694733
2bda7267-b55a-4571-ab2f-f15edd8d330a	abc7e945-2aab-4ab1-b7fb-598398da56be	Cancelled	2024-11-27 20:56:52.766626
5df7ba7f-1c10-4697-9620-51a730202ecf	abc7e945-2aab-4ab1-b7fb-598398da56be	Cancelled	2024-11-27 20:56:54.196816
d113468d-c1dc-41d6-8c52-22d73bf9962e	abc7e945-2aab-4ab1-b7fb-598398da56be	Cancelled	2024-11-27 20:58:15.727885
fda89af9-f443-4446-9315-3fe80110c5fd	b3f3fd1f-7a55-4516-927e-5eb1508fbecb	Pending	2024-12-05 21:18:50.233301
\.


--
-- Data for Name: order_items; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.order_items (order_id, product_id, quantity, price) FROM stdin;
abc7e945-2aab-4ab1-b7fb-598398da56be	94ab27f1-ea29-4127-82a7-d3aa53338e8d	1	36400.00
b3f3fd1f-7a55-4516-927e-5eb1508fbecb	94ab27f1-ea29-4127-82a7-d3aa53338e8d	4	36400.00
\.


--
-- Data for Name: orders; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.orders (order_id, user_id, order_date, status, total_cost) FROM stdin;
abc7e945-2aab-4ab1-b7fb-598398da56be	768a943e-20bf-44cb-b055-4d97c67d3ff3	2024-11-27 20:53:56.694733	Cancelled	36400.00
b3f3fd1f-7a55-4516-927e-5eb1508fbecb	ddd9a141-afc3-4d4d-a527-c3972099922f	2024-12-05 21:18:50.233301	Pending	145600.00
\.


--
-- Data for Name: products; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.products (product_id, name, description, category_id, price, stock, manufacturer) FROM stdin;
03a97f3c-35c0-40fc-a9f8-cd93943a665b	А-18 "Голиаф-Г"	средний/тяжелый бронежилет, созданный для тех, кому нужна большая площадь защиты. Поддерживает систему StKSS и большую модульность. Площадь противоосколочной защиты: передний чехол - 20.3дм2, задний - 19.4дм2, камербанды - 11.4дм2.	d6f9cc87-fb33-48ef-84ab-1000f7cb851d	23750.00	10	Ars Arma
84e6a91c-75d0-4b8e-a094-1f363ae16978	LEAF FAST UPG	баллистический шлем класса А3 (БР1), умеющий безухое строение с возможностью крепления ПНВ на шрауд-крепление и рельсы для наушников и нашлемных фонарей. Вес МЛ - 1500гр. Вес ЛХЛ - 1700гр.	58ec2643-a385-4b72-9d5a-58b2bafba9f3	42000.00	10	Проект LEAF
94ab27f1-ea29-4127-82a7-d3aa53338e8d	Holosun Micro HS503CU	идеальный выбор для тех, кому важна точность и надёжность. Двойное электропитание: солнечная панель и батарейки, высокая/низкая установка, 10 уровней яркости и пожизненная гарантия.	e5440dbf-2d74-4f0c-a083-8e8ae4270336	36400.00	6	Holosun
\.


--
-- Data for Name: reviews; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.reviews (review_id, product_id, user_id, rating, comment, review_date) FROM stdin;
b53889ad-a117-419b-a9fc-a67092efdc63	94ab27f1-ea29-4127-82a7-d3aa53338e8d	ddd9a141-afc3-4d4d-a527-c3972099922f	5	Отличный прицел, держит СТП на калибре 7.62х54R	2024-12-02 19:37:53.567315
\.


--
-- Data for Name: roles; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.roles (role_id, name) FROM stdin;
1	User
2	Admin
\.


--
-- Data for Name: user_roles; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.user_roles (user_id, role_id) FROM stdin;
ddd9a141-afc3-4d4d-a527-c3972099922f	2
768a943e-20bf-44cb-b055-4d97c67d3ff3	1
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: project_user
--

COPY public.users (user_id, username, hashed_password, email) FROM stdin;
ddd9a141-afc3-4d4d-a527-c3972099922f	santa	$2b$12$w1ZNsQFEqjbQWQdmmPK1BeXQrHrOiUd2bQXPsOLlcJWHPKwFpcHR.	santa2024@yandex.ru
768a943e-20bf-44cb-b055-4d97c67d3ff3	user	$2b$12$aiRvW7rw7v1YM2OtsLCr/.E8aoPoNNRunpuowGnQLwk82Lwz6PcY6	user2024@yandex.ru
\.


--
-- Name: roles_role_id_seq; Type: SEQUENCE SET; Schema: public; Owner: project_user
--

SELECT pg_catalog.setval('public.roles_role_id_seq', 2, true);


--
-- Name: cart cart_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.cart
    ADD CONSTRAINT cart_pkey PRIMARY KEY (user_id, product_id);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (category_id);


--
-- Name: order_history order_history_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.order_history
    ADD CONSTRAINT order_history_pkey PRIMARY KEY (history_id);


--
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (order_id, product_id);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (order_id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (product_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (review_id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (role_id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: cart cart_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.cart
    ADD CONSTRAINT cart_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(product_id) ON DELETE CASCADE;


--
-- Name: cart cart_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.cart
    ADD CONSTRAINT cart_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: order_history fk_order_history_orders; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.order_history
    ADD CONSTRAINT fk_order_history_orders FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;


--
-- Name: orders fk_orders_users; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT fk_orders_users FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: products fk_products_categories; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT fk_products_categories FOREIGN KEY (category_id) REFERENCES public.categories(category_id) ON DELETE SET NULL;


--
-- Name: reviews fk_reviews_products; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT fk_reviews_products FOREIGN KEY (product_id) REFERENCES public.products(product_id) ON DELETE CASCADE;


--
-- Name: reviews fk_reviews_users; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT fk_reviews_users FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: user_roles fk_user_roles_roles; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_roles FOREIGN KEY (role_id) REFERENCES public.roles(role_id) ON DELETE CASCADE;


--
-- Name: user_roles fk_user_roles_users; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT fk_user_roles_users FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE CASCADE;


--
-- Name: order_items order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: project_user
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(product_id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

