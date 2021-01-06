from collections import namedtuple, defaultdict
from itertools import product
from typing import List, Iterable

import requests

SUPPORTED_TASK_TYPES = frozenset(
    {'control-work', 'additional-3', 'individual-work', 'additional', 'classwork', 'homework'}
)

AUTHORIZATION_URL = 'https://passport.yandex.ru/auth?mode=auth'
PROFILE_URL = 'https://lyceum.yandex.ru/api/profile'
TASKS_API_URL = 'https://lyceum.yandex.ru/api/student/tasks'

TaskTypeInfo = namedtuple(
    'TaskTypeInfo', ('classwork', 'homework', 'additional', 'control_work', 'individual_work')
)

KNOWN_COEFFICIENTS = {
    TaskTypeInfo(36, 36, 41, 2, 3),  # Д  (1) (2019)
    TaskTypeInfo(35, 35, 33, 3, 0),  # Д  (2) (2019)
    TaskTypeInfo(21, 21, 21, 2, 4),  # ОБ (1) (2019)
}


def stop():
    input('тык')
    raise SystemExit


def get_authorized_session() -> requests.Session:
    login = input('Логин: ')
    password = input('Пароль: ')
    session = requests.Session()
    print('Авторизуюсь...')
    authorization_response = session.post(
        AUTHORIZATION_URL,
        data={
            'login': login,
            'passwd': password
        })
    if authorization_response.url == 'https://passport.yandex.ru/profile':
        print('Успешная авторизация.')
    else:
        print('Ошибка. Неправильно введён логин или пароль или вылезла капча.')
        stop()
    return session


def get_courses_json(session: requests.Session) -> List[dict]:
    courses_response = session.get(
        PROFILE_URL,
        params={
            'onlyActiveCourses': True,
            'withChildren': True,
            'withCoursesSummary': True,
            'withExpelled': True
        })
    return courses_response.json()['coursesSummary']['student']


def choose_course_json(courses_data: List[dict]) -> dict:
    print('Выберите номер курса.')
    while True:
        try:
            for num, course in enumerate(courses_data):
                print(num, course['title'])
            num = int(input('Номер курса: '))
            if num not in range(len(courses_data)):
                raise ValueError
        except ValueError:
            print('Введите номер курса.')
        else:
            return courses_data[num]


def get_tasks_json(session: requests.Session, course_json: dict) -> dict:
    tasks_json: dict = session.get(
        TASKS_API_URL,
        params={
            'courseId': course_json['id']
        }).json()
    return tasks_json


def calc_points_by_type_raw(tasks_json: Iterable[dict]) -> defaultdict:
    points_by_type = defaultdict(int)
    for json_task in tasks_json:
        task_type = json_task['tag']['type']
        if (sol := json_task['solution']) and sol['status']['type'] == 'accepted':
            points_by_type[task_type] += sol['score']
    if not set(points_by_type) <= SUPPORTED_TASK_TYPES:
        print('неподдерживаемые типы задач; не знаю, что делать')
        print(points_by_type)
        stop()
    return points_by_type


def points_by_type_convert(points_by_type_raw: defaultdict) -> TaskTypeInfo:
    classwork_points = points_by_type_raw['classwork']
    homework_points = points_by_type_raw['homework']
    additional_points = points_by_type_raw['additional']
    control_work_points = points_by_type_raw['control-work']
    control_work_points += points_by_type_raw['additional-3']
    individual_work_points = points_by_type_raw['individual-work']
    return TaskTypeInfo(classwork=classwork_points, homework=homework_points,
                        additional=additional_points, control_work=control_work_points,
                        individual_work=individual_work_points)


def calculate_rating(points: TaskTypeInfo, lessons_w_types: TaskTypeInfo) -> float:
    classwork_rating = \
        points.classwork / (10 * lessons_w_types.classwork) if lessons_w_types.classwork else 0
    homework_rating = \
        points.homework / (10 * lessons_w_types.homework) if lessons_w_types.homework else 0
    additional_rating = \
        (points.additional * 4) / (10 * lessons_w_types.additional) if lessons_w_types.additional else 0
    if lessons_w_types.individual_work:  # Д (2) (2019) и ещё что-то там
        individual_work_rating = \
            (points.individual_work * 2) / (10 * lessons_w_types.individual_work)
        control_work_rating = \
            (points.control_work * 4) / (10 * lessons_w_types.control_work) if lessons_w_types.control_work else 0
    else:
        control_work_rating = \
            (points.control_work * 6) / (10 * lessons_w_types.control_work) if lessons_w_types.control_work else 0
        individual_work_rating = 0
    return classwork_rating + homework_rating + additional_rating + control_work_rating + individual_work_rating


def generate_possible_coefficients():
    for indwrk, ctwrk, addwrk, clhmwrk in product(range(0, 5), range(2, 5), range(20, 51), range(20, 51)):
        yield TaskTypeInfo(classwork=clhmwrk, homework=clhmwrk, additional=addwrk,
                           control_work=ctwrk, individual_work=indwrk)


def approximate_coefficients(points: TaskTypeInfo, rating: float):
    best_known = min(KNOWN_COEFFICIENTS, key=lambda co: abs(rating - calculate_rating(points, co)))
    if abs(rating - calculate_rating(points, best_known)) < 0.0000000001:
        return best_known
    return min(generate_possible_coefficients(),
               key=lambda co: (abs(rating - calculate_rating(points, co)),
                               # It's likely that the number of lessons with classwork will be
                               # the same as the number of lessons with homework.
                               -min(co.classwork, co.homework) / max(co.classwork, co.homework),
                               # The numbers of lessons with classwork and lessons with
                               # additional work are generally pretty close.
                               -min(co.classwork, co.additional) / max(co.classwork, co.additional)))


def get_points_on_review(tasks_json: Iterable[dict]) -> defaultdict:
    pending_points_by_type = defaultdict(int)
    for json_task in tasks_json:
        task_type = json_task['tag']['type']
        if (sol := json_task['solution']) and sol['status']['type'] == 'review':
            pending_points_by_type[task_type] += json_task['scoreMax']
    if not set(pending_points_by_type) <= SUPPORTED_TASK_TYPES:
        print('неподдерживаемые типы задач; не знаю, что делать')
        print(pending_points_by_type)
        stop()
    return pending_points_by_type


if __name__ == '__main__':
    print('Для того, чтобы получить необходимые данные, требуется зайти в аккаунт, привязанный к Яндекс.Лицею.')
    session = get_authorized_session()

    courses_json = get_courses_json(session)
    course_json = choose_course_json(courses_json)
    print('Беру задания...')
    tasks_json = get_tasks_json(session, course_json)

    print('Подбираю коэффиценты...')
    primary_points_by_type_raw = calc_points_by_type_raw(tasks_json)
    bonus_rating = 5 * primary_points_by_type_raw['additional-3'] / 100
    bonus_rating += course_json['bonusScore']

    primary_points_by_type = points_by_type_convert(primary_points_by_type_raw)

    normal_rating = course_json['rating']
    true_rating = normal_rating - bonus_rating

    lessons_with_types = approximate_coefficients(primary_points_by_type, true_rating)

    on_review_prim_points_type = points_by_type_convert(get_points_on_review(tasks_json))

    rating_on_review = calculate_rating(on_review_prim_points_type, lessons_with_types)

    print()
    print('Внимание! Данная информация является лишь предположением на основе имеющихся данных.')
    print('Предполагается, что за все задачи, находящиеся на проверке, вы получите максимальный балл.')
    print('Если данных мало, то результаты могут быть крайне не точными.')
    print()
    print(f'Рейтинг: {normal_rating:.2f}')
    print(f'Рейтинг без прибавок: {true_rating:.2f}')
    print(f'Рейтинг на проверке: {rating_on_review:.2f}')
    print(f'Возможный рейтинг: {normal_rating + rating_on_review:.2f}')
    print()
    print('Предполагаемое кол-во уроков, в которых содержатся задачи каждого типа:')
    if lessons_with_types in KNOWN_COEFFICIENTS:
        for name, value in zip(('Классная работа', 'Домашняя работа', 'Дополнительные задачи',
                                'Контрольная работа', 'Самостоятельная работа'), lessons_with_types):
            print(f'{name}: {value}')
        print('Кол-во уроков с задачами разных типов в вашем курсе было известно изначально.')
    else:
        for name, value, key in zip(('Классная работа', 'Домашняя работа', 'Дополнительные задачи',
                                     'Контрольная работа / Проект', 'Самостоятельная работа'), lessons_with_types,
                                    ('classwork', 'homework', 'additional', 'control-work', 'individual-work')):
            points_for_type = primary_points_by_type_raw[key]
            if key == 'control-work':
                points_for_type += primary_points_by_type_raw['additional-3']
            print(f'{name}: {"Недостаточно данных" if points_for_type == 0 else value}')
        print('Кол-во уроков с задачами разных типов в вашем курсе не было известно изначально.\n'
              'Прошу обратную связь осуществлять в issues.')
              '(Если недостаточно данных по двум или более типам задач, скорее всего результат не верный.)')
    stop()

