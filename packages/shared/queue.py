from redis import Redis
from rq import Queue

from packages.shared.config import settings

redis_conn = Redis.from_url(settings.REDIS_URL.replace("redis://", "redis://"))
task_queue = Queue("nexus_tasks", connection=redis_conn)
