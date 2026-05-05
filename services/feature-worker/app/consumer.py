import json
import logging
import time
import httpx
import aio_pika
from aio_pika import Message, DeliveryMode

from . import clients
from .mapping import EVENT_DELTA_MAP
from .metrics import (
    WORKER_PROCESSED_TOTAL,
    WORKER_FAILED_TOTAL,
    WORKER_RETRY_TOTAL,
    WORKER_DLQ_TOTAL,
    WORKER_LATENCY,
)

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "user.events"
ROUTING_KEY = "user.interaction"
DLQ_NAME = "feature.update.dlq"
MAX_RETRIES = 3


async def handle_message(
    message: aio_pika.IncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    default_exchange: aio_pika.abc.AbstractExchange,
) -> None:
    start = time.time()
    try:
        await _process_message(message, exchange, default_exchange)
    finally:
        WORKER_LATENCY.observe(time.time() - start)


async def _process_message(
    message: aio_pika.IncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    default_exchange: aio_pika.abc.AbstractExchange,
) -> None:
    try:
        body = json.loads(message.body)
        event_id = body["event_id"]
        user_id = body["user_id"]
        video_id = body["video_id"]
        event_type = body["event_type"]
        completion_rate = body.get("completion_rate")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error(json.dumps({"action": "skip", "reason": "invalid_schema", "error": str(exc)}))
        await message.ack()
        return

    delta = EVENT_DELTA_MAP.get(event_type)
    if delta is None:
        logger.error(json.dumps({
            "action": "skip", "reason": "unknown_event_type",
            "event_id": event_id, "event_type": event_type,
        }))
        await message.ack()
        return

    try:
        video = await clients.get_video(video_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.error(json.dumps({"action": "skip", "reason": "video_not_found", "event_id": event_id}))
            await message.ack()
            return
        if exc.response.status_code // 100 == 4:
            logger.error(json.dumps({
                "action": "skip", "reason": "video_client_error",
                "status": exc.response.status_code, "event_id": event_id,
            }))
            await message.ack()
            return
        await _handle_retry(message, exchange, default_exchange)
        return
    except httpx.HTTPError:
        await _handle_retry(message, exchange, default_exchange)
        return

    tags = video.get("tags", [])
    completion_rate_sample = completion_rate if delta.use_completion_rate else None

    needs_stats_patch = (
        delta.views_delta != 0
        or delta.likes_delta != 0
        or delta.skips_delta != 0
        or completion_rate_sample is not None
    )
    if needs_stats_patch:
        try:
            await clients.patch_video_stats(video_id, {
                "views_delta": delta.views_delta,
                "likes_delta": delta.likes_delta,
                "skips_delta": delta.skips_delta,
                "completion_rate_sample": completion_rate_sample,
            })
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code // 100 == 5:
                await _handle_retry(message, exchange, default_exchange)
                return
            logger.error(json.dumps({
                "action": "skip", "reason": "video_stats_error",
                "status": exc.response.status_code, "event_id": event_id,
            }))
            await message.ack()
            return
        except httpx.HTTPError:
            await _handle_retry(message, exchange, default_exchange)
            return

    for tag in tags:
        try:
            await clients.patch_user_interest(user_id, tag, delta.interest_delta)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.error(json.dumps({"action": "skip", "reason": "user_not_found", "event_id": event_id}))
                await message.ack()
                return
            if exc.response.status_code // 100 == 5:
                await _handle_retry(message, exchange, default_exchange)
                return
            logger.error(json.dumps({
                "action": "skip", "reason": "interest_error",
                "status": exc.response.status_code, "event_id": event_id,
            }))
            await message.ack()
            return
        except httpx.HTTPError:
            await _handle_retry(message, exchange, default_exchange)
            return

    await message.ack()
    WORKER_PROCESSED_TOTAL.inc()


async def _handle_retry(
    message: aio_pika.IncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    default_exchange: aio_pika.abc.AbstractExchange,
) -> None:
    retry_count = int(message.headers.get("x-retry-count", 0))
    if retry_count < MAX_RETRIES:
        new_message = Message(
            body=message.body,
            content_type=message.content_type,
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={"x-retry-count": retry_count + 1},
        )
        await exchange.publish(new_message, routing_key=ROUTING_KEY)
        logger.warning(json.dumps({"action": "retry", "x-retry-count": retry_count + 1}))
        WORKER_RETRY_TOTAL.inc()
    else:
        dead_message = Message(body=message.body, delivery_mode=DeliveryMode.PERSISTENT)
        await default_exchange.publish(dead_message, routing_key=DLQ_NAME)
        logger.error(json.dumps({"action": "dlq", "x-retry-count": retry_count}))
        WORKER_DLQ_TOTAL.inc()
        WORKER_FAILED_TOTAL.inc()
    await message.ack()
