import logging
import os
import time
from contextlib import suppress
from http import HTTPStatus
from sys import stdout

import requests
from dotenv import load_dotenv
from telebot import TeleBot
from telebot.apihelper import ApiException

from exceptions import ApiStatusCodeError

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: всё отлично. Ура!',
    'reviewing': 'Работа взята на проверку.',
    'rejected': 'Работа проверена: есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
stdout_handler = logging.StreamHandler(stream=stdout)
logger.addHandler(stdout_handler)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
)
stdout_handler.setFormatter(formatter)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    logger.debug('Проверка переменных окружения...')
    tokens = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
    missing_tokens = [token for token in tokens if not globals()[token]]
    if missing_tokens:
        message = f'Отсутствует переменная окружения {missing_tokens[0]}!'
        logger.critical(message)
        raise ValueError(message)
    logger.debug('Проверка переменных окружения выполнена успешно.')


def send_message(bot, message):
    """Отправляет сообщение конкретному пользователю."""
    logger.debug('Отправляю сообщение...')
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    logger.debug('Сообщение успешно отправлено.')


def get_api_answer(timestamp):
    """Возвращает ответ на запрос к API."""
    logger.debug(f'Отправляю запрос к API {ENDPOINT} ...')
    message = f'(Unix-время {timestamp}) {ENDPOINT} недоступен.'
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=f'from_date={timestamp}'
        )
    except requests.RequestException as error:
        raise ConnectionError(f'{message} Ошибка: {error}')
    if not response.status_code == HTTPStatus.OK:
        raise ApiStatusCodeError(
            f'{message} Код ответа API: {response.status_code}')
    logger.debug('Запрос к API выполнен успешно.')

    return response.json()


def check_response(response):
    """Проверяет ответ, полученный в запросе к API."""
    logger.debug('Проверяю ответ от API...')
    if not isinstance(response, dict):
        raise TypeError(
            (f'В ответе API тип данных - {type(response)} '
             f'не соответствует ожидаемому {dict}.')
        )
    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ "homeworks".')
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            (f'В ответе API под ключом "homeworks" '
             f'тип данных - {type(response["homeworks"])} '
             f'не соответствует ожидаемому {list}.')
        )
    logger.debug('Проверка ответа от API выполнена успешно.')


def parse_status(homework):
    """Возвращает сообщение об изменённом статусе проверки работы."""
    logger.debug('Проверяю изменение статуса проверки работы...')
    if 'homework_name' not in homework:
        raise KeyError(
            ('Не удалось найти название домашней работы. '
             'Ключ "homework_name" отсутствует.')
        )
    homework_name = homework['homework_name']
    if 'status' not in homework:
        raise KeyError(
            ('Не удалось найти статус домашней работы. '
             'Ключ "status" отсутствует.')
        )
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус проверки - {homework_status}.')
    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug('Проверка изменения статуса проверки работы выполнена.')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_sent_message = ''

    while True:
        try:
            api_answer = get_api_answer(timestamp)
            check_response(api_answer)
            homeworks = api_answer['homeworks']
            if not homeworks:
                logger.info('Статус не обновился.')
                continue
            last_homework = homeworks[0]
            last_homework_status = parse_status(last_homework)
            send_message(bot, last_homework_status)
            last_sent_message = last_homework_status
            timestamp = api_answer.get('current_date', timestamp)
        except (ApiException, requests.RequestException) as error:
            logger.exception(f'Сбой при отправке сообщения: {error}')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.exception(error)
            if message != last_sent_message:
                with suppress(
                        ApiException, requests.RequestException):
                    send_message(bot, message)
                    last_sent_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
