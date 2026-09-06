from pydantic import SecretStr
from redis.asyncio import Redis


def make_redis_client(
    *,
    host: str,
    port: int,
    db: int,
    password: SecretStr | None = None,
    max_connections: int = 20,
    socket_timeout_seconds: float = 5.0,
    socket_connect_timeout_seconds: float = 5.0,
    socket_keepalive: bool = True,
    health_check_interval_seconds: int = 30,
    decode_responses: bool = True,
) -> Redis:
    """
    Create async Redis client.
    """
    return Redis(
        host=host,
        port=port,
        db=db,
        password=password.get_secret_value() if password is not None else None,
        max_connections=max_connections,
        socket_timeout=socket_timeout_seconds,
        socket_connect_timeout=socket_connect_timeout_seconds,
        socket_keepalive=socket_keepalive,
        health_check_interval=health_check_interval_seconds,
        decode_responses=decode_responses,
    )
