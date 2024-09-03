import logging
import os
import sys
import time

from http import HTTPStatus

import requests

from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()

logger = logging.getLogger(__name__)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение конкретному пользователю."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Сообщение отправлено.')
    except Exception:
        logger.error('Сообщение не отправлено.')


def get_api_answer(timestamp):
    """Возвращает ответ на запрос к API."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=f'from_date={timestamp}'
        )
    except requests.RequestException as error:
        logger.error(error)
    else:
        if not response.status_code == HTTPStatus.OK:
            raise Exception('Ошибка сервера')

        return response.json()


def check_response(response):
    """Проверяет ответ, полученный в запросе к API."""
    if not isinstance(response, dict):
        raise TypeError('В ответе данные, которые невозможно обработать.')
    if 'current_date' not in response:
        raise KeyError('Ошибка получения текущего времени.')
    if 'homeworks' not in response:
        raise KeyError('Список домашних работ отсутствует.')
    if not isinstance(response['homeworks'], list):
        raise TypeError('В ответе данные, которые невозможно обработать.')


def parse_status(homework):
    """Возвращает сообщение об изменённом статусе проверки работы."""
    if 'homework_name' not in homework:
        raise KeyError('Не удалось найти название домашней работы.')
    homework_name = homework.get('homework_name')
    if 'status' not in homework:
        raise KeyError('Отсутсвует статус проверки работы.')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyError('Неизвестный статус.')
    verdict = HOMEWORK_VERDICTS.get(homework_status)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logger.setLevel(logging.DEBUG)
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(stdout_handler)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    )
    stdout_handler.setFormatter(formatter)

    if not check_tokens():
        logger.critical('Отсутствует переменная окружения.')
        sys.exit()

    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    current_status = None
    error_messages = []

    while True:
        try:
            api_answer = get_api_answer(timestamp)
            check_response(api_answer)
            homework = api_answer.get('homeworks')[0]
            homework_status = parse_status(homework)
            if current_status != homework_status:
                send_message(bot, homework_status)
                current_status = homework_status
            timestamp = api_answer.get('current_date')

        except IndexError:
            logger.debug('Статус не обновился.')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(error)
            if message not in error_messages:
                send_message(bot, message)
                error_messages.append(message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
