import logging
import os
import sys
import time
from http import HTTPStatus
from logging import StreamHandler

import requests
from dotenv import load_dotenv
from telegram import Bot

# Переменные, описанные в файле .env,
# доступны в пространстве переменных окружения
load_dotenv()


# Береме "секретные" переменные из пространства переменных окружения
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    filename='my.log',
    filemode='w'
)
logger = logging.getLogger(__name__)
# Обработчик согласно ТЗ
handler = StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
# Создаем форматер и применяем его к обработчику
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] - '
    '(%(filename)s).%(funcName)s:%(lineno)d - %(message)s')
handler.setFormatter(formatter)


def check_tokens():
    """Функция проверяет доступность переменных окружения."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Cообщение отправлено')
    except Exception as error:
        message = f'Ошибка при отправке сообщения: {error}'
        logger.error(message)


def get_api_answer(timestamp):
    """Функция делает запрос к единственному эндпоинту API-сервиса.
    и проверяет статуса ответа.
    """
    try:
        payload = {'from_date': timestamp}
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException():
        message = f'''Сбой в работе программы: Эндпоинт {ENDPOINT}
                    недоступен. Код ответа API: {response.status_code}'''
        logger.error(message)
        send_message(Bot(TELEGRAM_TOKEN), message)
        raise requests.RequestException()
    if response.status_code != HTTPStatus.OK:
        message = (
            'Ответ сервера не является успешным:'
            f' request params = {payload}; {HEADERS}'
            f' http_code = {response.status_code};'
            f' reason = {response.reason}; content = {response.text}'
        )
        logger.error(message)
        send_message(Bot(TELEGRAM_TOKEN), message)
        raise requests.RequestException()
    return response.json()


def check_response(response):
    """Функция проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        message = (
            'Ошибка полученных данных:'
            'тип данных ответа не соответствует документации.'
            f'Получен тип {type(response)} вместо dict'
        )
        logger.error(message)
        send_message(Bot(TELEGRAM_TOKEN), message)
        raise TypeError()
    homeworks = response.get('homeworks')
    if homeworks is None:
        message = (
            'Ошибка полученных данных:'
            'В ответе отсутствует ключ homeworks.')
        send_message(Bot(TELEGRAM_TOKEN), message)
        raise Exception()
    elif not isinstance(homeworks, list):
        message = (
            'Ошибка полученных данных:'
            'тип данных ответа не соответствует документации.'
            f'Получен тип {type(homeworks)} вместо list')
        send_message(Bot(TELEGRAM_TOKEN), message)
        raise TypeError()
    else:
        if len(homeworks) == 0:
            return 'У домашки не появился новый статус'
        else:
            return homeworks[0]


def parse_status(homeworks):
    """Функция извлекает статус домашней работы."""
    if 'status' not in homeworks:
        message = ('В ответе сервера отсутствует ключ'
                   '"status" - "статус домашки"')
        logger.error(message)
        raise KeyError
    else:
        status = homeworks.get("status")
    if status not in HOMEWORK_VERDICTS:
        message = 'Полученный "status" не соответсвует документации'
        logger.error(message)
        raise KeyError
    else:
        verdict = HOMEWORK_VERDICTS.get(status)
    if 'homework_name' not in homeworks:
        message = ('В ответе сервера отсутствует ключ'
                   '"homework_name" - "название домашки"')
        logger.error(message)
        raise KeyError
    else:
        homework_name = homeworks.get("homework_name")
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    # Проверка наличия всех токенов
    if check_tokens():
        bot = Bot(token=TELEGRAM_TOKEN)
        previous_status = ''
        last_error = ''
        while True:
            timestamp = int(time.time())
            try:
                response = get_api_answer(timestamp)
                homework = check_response(response)
                # Проверка, что меняется статус и тогда отправка сообщения
                if not homework == 'У домашки не появился новый статус':
                    current_status = parse_status(homework)
                    if current_status != previous_status:
                        send_message(bot, current_status)
                        previous_status = current_status
                else:
                    send_message(bot, homework)
            except Exception as error:
                message = f'Сбой в работе программы: {error}'
                # Проверка, что ошибка не повтор и тогда отправка сообщения
                if last_error != message:
                    logger.error(message)
                    send_message(bot, message)
            time.sleep(RETRY_PERIOD)
    else:
        message = 'Отсутствует, как минимум, одна переменная окружения'
        logger.critical(message)
        SystemExit()


if __name__ == '__main__':
    main()
