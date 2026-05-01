import os
import json
import logging
import aio_pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "")
EXCHANGE_NAME = "user.events"
ROUTING_KEY = "user.interaction"

_connection = None
_channel = None
_exchange = None


async def connect() -> None:
    global _connection, _channel, _exchange
    _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
    )


async def disconnect() -> None:
    global _connection, _channel, _exchange
    if _connection:
        await _connection.close()
        _connection = None
        _channel = None
        _exchange = None


async def publish_event(event_data: dict) -> None:
    if _exchange is None:
        logger.error("RabbitMQ not connected; skipping publish for event_id=%s", event_data.get("event_id"))
        return
    try:
        message = aio_pika.Message(
            body=json.dumps(event_data).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await _exchange.publish(message, routing_key=ROUTING_KEY)
    except Exception as exc:
        logger.error(
            "publish_failed event_id=%s idempotency_key=%s error=%s",
            event_data.get("event_id"),
            event_data.get("idempotency_key"),
            str(exc),
        )
