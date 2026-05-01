import asyncio
import logging
import os
import aio_pika

from . import consumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://feedflow:feedflow@localhost:5672/")
EXCHANGE_NAME = "user.events"
QUEUE_NAME = "feature.update.queue"
DLQ_NAME = "feature.update.dlq"
ROUTING_KEY = "user.interaction"


async def main() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
    )
    await channel.declare_queue(DLQ_NAME, durable=True)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key=ROUTING_KEY)

    default_exchange = channel.default_exchange

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        await consumer.handle_message(message, exchange, default_exchange)

    await queue.consume(on_message)
    logger.info("Feature Worker started — consuming from %s", QUEUE_NAME)

    await asyncio.Future()  # run until cancelled


if __name__ == "__main__":
    asyncio.run(main())
