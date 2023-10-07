import json
import os
import socketio
import logging.config

from aiogram import Bot, types, Router, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response

from subscribers import Subscribers

APP_LOCAL_HOSTNAME = os.getenv('APP_LOCAL_HOSTNAME')
APP_LOCAL_PORT = os.getenv('APP_LOCAL_PORT')

APP_GLOBAL_HOSTNAME = os.getenv('APP_GLOBAL_HOSTNAME')

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_WEBHOOK_PATH = f'/tghook'
TELEGRAM_WEBHOOK_SECRET = 'my_secret'

subscribers = Subscribers()

log_web_server = logging.getLogger('web_server')
log_socket_io_server = logging.getLogger('socket_io_server')
log_telegram_bot_server = logging.getLogger('telegram_bot_server')

# Routers
web_router = web.RouteTableDef()
telegram_router = Router()
socket_io_router = socketio.AsyncServer()


# =================== Telegram Bot ====================

async def on_startup(bot: Bot) -> None:
    await bot.set_webhook(url=f"{APP_GLOBAL_HOSTNAME}{TELEGRAM_WEBHOOK_PATH}", secret_token=TELEGRAM_WEBHOOK_SECRET)


async def on_shutdown(bot: Bot) -> None:
    await bot.delete_webhook()


@telegram_router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    subscribers.add_subscriber(message.bot, message.chat.id)
    await message.answer(f"Hello, {hbold(message.from_user.full_name)}!")


@telegram_router.message()
async def echo_handler(message: types.Message) -> None:
    try:
        # await message.send_copy(chat_id=message.chat.id)
        await socket_io_router.emit(
            event='tgmessage',
            data={
                'from': message.from_user.full_name,
                'msg': message.text
            }
        )
    except TypeError:
        log_telegram_bot_server.warning(f'Unknown command from {message.from_user.full_name}')
        await message.answer("Nice try!")


# ===================== Web server =====================

@web_router.get('/')
async def handler_home(request: Request) -> Response:
    return web.json_response({'state': 'ok'})


@web_router.get('/test')
@web_router.post('/test')
async def handler_test(request: Request) -> Response:
    if request.body_exists:
        data = await request.json()
        msg = data.get('msg', 'Message from web')
    else:
        msg = 'Message from web'

    await socket_io_router.emit(event='webmessage',
                                data={
                                    'from': 'web',
                                    'msg': msg
                                })
    await subscribers.send_message(msg)
    return web.json_response({'test': 'ok'})


# ======================= Socket.io ====================

@socket_io_router.event
async def connect(sid: str, environ) -> None:
    log_socket_io_server.debug(f'connected: {sid}')
    log_socket_io_server.debug(f'connect env type: {type(environ)}')
    await socket_io_router.emit(
        event='message',
        to=sid,
        data='hello'
    )


@socket_io_router.event
async def disconnect(sid: str) -> None:
    log_socket_io_server.debug(f'disconnected: {sid}')


@socket_io_router.on('send')
async def socket_io_send(sid: str, data) -> None:
    if not isinstance(data, dict):
        log_socket_io_server.debug(f'wrong data from {sid}')
        return

    msg = data.get('msg')

    if msg:
        await subscribers.send_message(msg)
        log_socket_io_server.debug(f'send {sid}')


def main() -> None:
    app = web.Application()

    # Dispatcher is a root router
    dp = Dispatcher()
    dp.include_router(telegram_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Initialize Bot instance with a default parse mode which will be passed to all API calls
    bot = Bot(TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)

    webhook_requests_handler = SimpleRequestHandler(
       dispatcher=dp,
       bot=bot,
       secret_token=TELEGRAM_WEBHOOK_SECRET,
    )

    # Attach routers to web server

    webhook_requests_handler.register(app, path=TELEGRAM_WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.add_routes(web_router)
    socket_io_router.attach(app)

    subscribers.attach_bot(bot)

    # Start web server
    web.run_app(app, host=APP_LOCAL_HOSTNAME, port=APP_LOCAL_PORT)


def load_log_config(file_name: str = 'log_config.json'):
    if os.path.exists(file_name):
        with open(
                file=file_name,
                mode='r',
                encoding='utf-8'
        ) as file:
            return json.load(file)


if __name__ == '__main__':
    logging.config.dictConfig(load_log_config())
    main()
