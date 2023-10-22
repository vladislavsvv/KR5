from typing import Any
import psycopg2
import psycopg2.errors
import requests
import json


class HeadHunter:
    """
        Класс для доступа к api HeadHunter.
        """
    employers_dict = {}
    employers_data = []
    vacancies_data = []

    def __init__(self, employer):
        self.employer = employer

    def get_employer(self):
        """
        Функция для получения данных по работодателю
        """
        url_employers = "https://api.hh.ru/employers"
        params = {
            "text": {self.employer},
            "areas": 113,
            "per_page": 20
        }
        response = requests.get(url_employers, params=params)
        if response.status_code != 200:
            raise Exception(f"Ошибка получения данных по работодателю! Статус: {response.status_code}")
        employer = response.json().get('items', [])
        if employer is None:
            return "Данные не получены"
        else:
            self.employers_dict = {'id': employer[0]['id'], 'name': employer[0]['name'],
                                   'url': employer[0]['alternate_url']}
            self.employers_data.append(self.employers_dict)
            return self.employers_dict

    def get_page_vacancies(self, employer_id, page):
        """
        Функция для получения вакансий по id работодателя
        """
        self.employer_id = employer_id
        url_vacancies = "https://api.hh.ru/vacancies"
        params = {
            "employer_id": {self.employer_id},
            "areas": 113,
            "per_page": 100,
            "page": page
        }
        response = requests.get(url_vacancies, params=params)
        if response.status_code != 200:
            raise Exception(f"Ошибка получения вакансий! Статус: {response.status_code}")
        data = response.content.decode()
        response.close()
        return data

    def get_vacancies(self, employer_id):
        """
        Функция обработки данных по вакансиям
        """
        vacancies_employer_dicts = []
        for page in range(10):
            vacancies_data = json.loads(self.get_page_vacancies(employer_id, page))
            if 'errors' in vacancies_data:
                return vacancies_data['errors'][0]['value']
            for vacancy_data in vacancies_data['items']:
                if vacancy_data["salary"] is None:
                    vacancy_data["salary"] = {}
                    vacancy_data["salary"]["from"] = None
                    vacancy_data["salary"]["to"] = None

                vacancy_dict = {'id': vacancy_data['id'],
                                'name': vacancy_data['name'],
                                'url': vacancy_data['apply_alternate_url'],
                                'salary_from': vacancy_data['salary']['from'] if vacancy_data["salary"] else None,
                                'salary_to': vacancy_data['salary']['to'],
                                'employer_id': vacancy_data.get('employer', {}).get("id", 'N/A'),
                                'employer_name': vacancy_data['employer']['name']}
                if vacancy_dict['salary_to'] is None:
                    vacancy_dict['salary_to'] = vacancy_dict['salary_from']
                vacancies_employer_dicts.append(vacancy_dict)
        return vacancies_employer_dicts


class Add_to_DB(HeadHunter):
    """
    Класс для добавления из списка выбранных работодателей в базу данных
    """
    __employers_name = []

    def __init__(self, employers_list: list):
        """
        В инициализаторе список выбранных работодателей
        :param employers_list:
        """
        self.employers_list = employers_list
        for employer in self.employers_list:
            super().__init__(employer)
            self.__employers_name.append(self.employer)

    @classmethod
    def get_all_employers(cls):
        """
        Получает данные по работодателям и родительского класса
        :return:
        """
        for employer in cls.__employers_name:
            employer_info = HeadHunter(employer)
            employer_info.get_employer()
        return super().employers_data


class DBManager:
    """
    Класс для работы с данными БД
    """

    def __init__(self):
        self.conn = None


    @classmethod
    def connect_to_db(cls):
        conn = psycopg2.connect(
            database="postgres",
            user="postgres",
            password="ktnj2023",
            port="5432"
        )
        cls.conn = conn

    def create_database(self, database_name: str):
        """
        Создание базы данных и таблиц для сохранения данных о .
        """
        self.connect_to_db()
        self.conn.autocommit = True
        cur = self.conn.cursor()

        try:
            cur.execute(f"CREATE DATABASE {database_name}")
        except psycopg2.errors.DuplicateDatabase:
            print(f"ОШИБКА: база данных {database_name} уже существует")
        self.conn.close()


        try:
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute("""CREATE TABLE IF NOT EXISTS employers (
                                employer_id VARCHAR(255),
                                name VARCHAR(255) NOT NULL,                          
                                employer_url TEXT,

                                CONSTRAINT pk_employers_employer_id PRIMARY KEY(employer_id)
                                )
                                """)
        except psycopg2.errors.DuplicateTable:
            print(f"Таблица с таким именем есть")
        finally:
            self.conn.close()

        try:
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute("""
                                CREATE TABLE IF NOT EXISTS vacancies (
                                vacancy_id INTEGER,
                                name VARCHAR(255) NOT NULL,
                                vacancy_url TEXT,
                                salary_from INTEGER,
                                salary_to INTEGER,
                                employer_id VARCHAR(255),
                                employer_name VARCHAR(255),

                                CONSTRAINT pk_vacancies_vacancy_id PRIMARY KEY(vacancy_id),
                                CONSTRAINT fk_vacancies_employer_id FOREIGN KEY(employer_id) REFERENCES employers(employer_id)
                                )
                                """)
        except psycopg2.errors.DuplicateTable:
            print(f"Таблица с таким именем есть")
        finally:
            self.conn.close()

    def save_employers_to_database(self, data: list[dict[str, Any]], database_name: str):
        """
        Сохранение данных о работодателях в базу данных.
        :param self:
        :param data:
        :param database_name:
        :return:
        """

        self.connect_to_db()
        with self.conn.cursor() as cur:
            for employer in data:
                cur.execute(
                    """
                    INSERT INTO employers (employer_id, name, employer_url)
                    VALUES (%s, %s, %s)
                    """,
                    (employer['id'], employer['name'], employer['url'])
                )
        self.conn.commit()
        self.conn.close()

    def save_vacancies_to_database(self, data: list[dict[str, Any]], database_name: str):
        """
        Сохранение данных о вакансиях в базу данных.
        """

        self.connect_to_db()
        with self.conn.cursor() as cur:
            for vacancy in data:
                cur.execute(
                    """
                    INSERT INTO vacancies (vacancy_id, name, vacancy_url, salary_from, salary_to, employer_id, employer_name)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (vacancy['id'], vacancy['name'], vacancy['url'], vacancy['salary_from'], vacancy['salary_to'],
                     vacancy['employer_id'], vacancy['employer_name'])
                )
        self.conn.commit()
        self.conn.close()

    def get_companies_and_vacancies_count(self, database_name):
        """
        Получает список всех компаний и количество вакансий у каждой компании
        :return:
        """

        self.connect_to_db()
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(f"""
                            SELECT employer_id, COUNT(*)
                            FROM vacancies
                            GROUP BY employer_id
                            ORDER BY COUNT(*) DESC
                            """)
            data = cur.fetchall()

        self.conn.close()
        return data

    def get_all_vacancies(self, database_name):
        """
        Получает список всех вакансий
        :return:
        """

        self.connect_to_db()
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(f"""
                        SELECT *FROM vacancies
                            """)
            data = cur.fetchall()

        self.conn.close()
        return data

    def get_avg_salary(self, database_name):
        """
        Получает среднюю зарплату по вакансиям
        :return:
        """

        self.connect_to_db()
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(f"""
                            SELECT AVG(salary_from) FROM vacancies
                            """)
            data = cur.fetchone()

        self.conn.close()
        return round(data[0])

    def get_vacancies_with_higher_salary(self, database_name):
        """
        Получает список всех вакансий, у которых зарплата выше средней по всем вакансиям
        :return:
        """

        self.connect_to_db()
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(f"""
                            SELECT *FROM vacancies
                            WHERE salary_from > (SELECT AVG(salary_from) FROM vacancies)
                            """)
            data = cur.fetchall()

        self.conn.close()
        return data

    def get_vacancies_with_keyword(self, database_name, keyword):
        """
        Получает список всех вакансий в названии которых содержатся переданные в метод слова
        :return:
        """

        self.connect_to_db()
        self.conn.autocommit = True
        with self.conn.cursor() as cur:
            cur.execute(f"""
                            SELECT *FROM vacancies
                            WHERE employer_name LIKE '{keyword}'
                                    """)
            data = cur.fetchall()

        self.conn.close()
        return data