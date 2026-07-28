"""IPC protocol definitions for Blender<->Qt UI communication.

This module defines the message protocol used for inter-process communication
between Blender (server) and external Qt UI processes (clients).

Protocol is JSON-based with message types:
- hello: Session negotiation
- hello_ack: Acknowledgement of session
- request: Async request from client to Blender
- response: Response to request
- event: Event published by Blender
- ping/pong: Keep-alive
"""

import json
import uuid
from typing import Any, Dict, Optional
from enum import Enum


class MessageType(str, Enum):
    """Message types in the IPC protocol."""
    HELLO = "hello"
    HELLO_ACK = "hello_ack"
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


class Message:
    """Base class for IPC messages."""

    def __init__(self, msg_type: MessageType, **kwargs):
        self.type = msg_type
        self.data = kwargs

    def to_json(self) -> str:
        """Serialize message to JSON."""
        return json.dumps({
            "type": self.type.value,
            **self.data
        })

    @staticmethod
    def from_json(json_str: str) -> "Message":
        """Deserialize message from JSON."""
        data = json.loads(json_str)
        msg_type = MessageType(data.pop("type"))
        return Message(msg_type, **data)


class HelloMessage(Message):
    """Session negotiation message."""

    def __init__(self, session_token: str, version: str = "1.0", **kwargs):
        super().__init__(
            MessageType.HELLO,
            session_token=session_token,
            version=version,
            **kwargs
        )


class HelloAckMessage(Message):
    """Acknowledgement of session."""

    def __init__(self, session_id: str, **kwargs):
        super().__init__(
            MessageType.HELLO_ACK,
            session_id=session_id,
            **kwargs
        )


class RequestMessage(Message):
    """Request message from client to Blender."""

    def __init__(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout_sec: float = 30.0,
        **kwargs
    ):
        if request_id is None:
            request_id = str(uuid.uuid4())
        if params is None:
            params = {}

        super().__init__(
            MessageType.REQUEST,
            id=request_id,
            method=method,
            params=params,
            idempotency_key=idempotency_key,
            timeout_sec=timeout_sec,
            **kwargs
        )


class ResponseMessage(Message):
    """Response message from Blender to client."""

    def __init__(
        self,
        request_id: str,
        ok: bool = True,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            MessageType.RESPONSE,
            id=request_id,
            ok=ok,
            result=result,
            error=error,
            **kwargs
        )


class EventMessage(Message):
    """Event published by Blender."""

    def __init__(
        self,
        topic: str,
        payload: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        if payload is None:
            payload = {}

        super().__init__(
            MessageType.EVENT,
            topic=topic,
            payload=payload,
            **kwargs
        )


class PingMessage(Message):
    """Keep-alive ping message."""

    def __init__(self, **kwargs):
        super().__init__(MessageType.PING, **kwargs)


class PongMessage(Message):
    """Keep-alive pong message."""

    def __init__(self, **kwargs):
        super().__init__(MessageType.PONG, **kwargs)


class ErrorMessage(Message):
    """Error message."""

    def __init__(self, error: str, **kwargs):
        super().__init__(MessageType.ERROR, error=error, **kwargs)


def parse_message(json_str: str) -> Message:
    """Parse incoming JSON message and return appropriate message object."""
    try:
        data = json.loads(json_str)
        msg_type = MessageType(data.pop("type"))

        if msg_type == MessageType.HELLO:
            return HelloMessage(
                session_token=data.pop("session_token"),
                version=data.pop("version", "1.0"),
                **data
            )
        elif msg_type == MessageType.HELLO_ACK:
            return HelloAckMessage(session_id=data.pop("session_id"), **data)
        elif msg_type == MessageType.REQUEST:
            return RequestMessage(
                method=data.pop("method"),
                params=data.pop("params", {}),
                request_id=data.pop("id", None),
                idempotency_key=data.pop("idempotency_key", None),
                timeout_sec=data.pop("timeout_sec", 30.0),
                **data
            )
        elif msg_type == MessageType.RESPONSE:
            return ResponseMessage(
                request_id=data.pop("id"),
                ok=data.pop("ok", True),
                result=data.pop("result", None),
                error=data.pop("error", None),
                **data
            )
        elif msg_type == MessageType.EVENT:
            return EventMessage(
                topic=data.pop("topic"),
                payload=data.pop("payload", {}),
                **data
            )
        elif msg_type == MessageType.PING:
            return PingMessage(**data)
        elif msg_type == MessageType.PONG:
            return PongMessage(**data)
        elif msg_type == MessageType.ERROR:
            return ErrorMessage(error=data.pop("error"), **data)
        else:
            return Message(msg_type, **data)

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValueError(f"Failed to parse message: {e}")

