import rnet, json, asyncio, traceback
from typing import Dict, Optional
from dataclasses import dataclass
from rnet import WebSocket, Message
from loguru import logger
from localization import t
import random

@dataclass
class ConnectionState:
    is_connected: bool = False
    reconnect_attempts: int = 0
    max_reconnect_attempts: int = 5

class KickWebSocket:
    def __init__(self, data: Dict[str, str]):
        self.ws: Optional[WebSocket] = None
        self.data = data
        self.state = ConnectionState()
        self.handshake_task: Optional[asyncio.Task] = None
        self.tracking_task: Optional[asyncio.Task] = None
        self._running = False

    async def connect(self) -> bool:
        if not self.data.get("token"):
            logger.error(t("token_must_not_be_empty"))
            return False

        try:
            logger.info(t("websocket_connecting", channel_id=self.data.get('channelId', 'unknown')))
            self.ws = await rnet.websocket(
                url=f"wss://websockets.kick.com/viewer/v1/connect?token={self.data['token']}",
                read_buffer_size=4096,
                write_buffer_size=4096,
                max_message_size=4096
            )
            
            logger.success(t("websocket_connected"))
            self.state.is_connected = True
            self.state.reconnect_attempts = 0
            
            await self._send_initial_messages()
            await self._start_background_tasks()
            await self._listen_for_messages()
            
            return True
            
        except Exception as e:
            logger.error(t("websocket_connection_failed", error=str(e)))
            logger.debug(t("connection_traceback", traceback=traceback.format_exc()))
            self.state.is_connected = False
            await self._handle_reconnection()
            return False

    async def _send_initial_messages(self):
        await self._send_handshake()
        await self._send_ping()

    async def _start_background_tasks(self):
        self._running = True
        
        self.handshake_task = asyncio.create_task(self._handshake_loop())
        self.tracking_task = asyncio.create_task(self._tracking_loop())

    async def _handshake_loop(self):
        while self._running and self.state.is_connected:
            try:
                await asyncio.sleep(random.uniform(25, 35))
                if self.state.is_connected:
                    await self._send_handshake()
                    await self._send_ping()
            except Exception as e:
                logger.error(t("handshake_loop_error", error=str(e)))
                logger.debug(t("handshake_traceback", traceback=traceback.format_exc()))
                break

    async def _tracking_loop(self):
        while self._running and self.state.is_connected:
            try:
                await asyncio.sleep(random.uniform(9.5, 12.5))
                if self.state.is_connected:
                    await self._send_user_event()
            except Exception as e:
                logger.error(t("tracking_loop_error", error=str(e)))
                logger.debug(t("tracking_traceback", traceback=traceback.format_exc()))
                break

    async def _listen_for_messages(self):
        try:
            logger.info(t("starting_websocket_listen"))
            while self.state.is_connected and self._running:
                message = await self.ws.recv()
                await self._handle_message(message)
        except Exception as e:
            logger.error(t("message_listening_error", error=str(e)))
            logger.debug(t("listening_traceback", traceback=traceback.format_exc()))
            self.state.is_connected = False
            await self._handle_reconnection()

    async def _handle_message(self, message):
        try:
            # Различные типы сообщений
            if isinstance(message, Message):
                message_str = message.text if hasattr(message, 'text') else str(message)
            else:
                message_str = str(message)
            
            # Пустое
            if not message_str or message_str.strip() == "":
                logger.debug(t("received_empty_message"))
                return
            
            # Ping
            if message_str.strip() == "ping":
                await self._send_pong()
                logger.debug(t("raw_ping_received"))
                return
            
            # Парсим жсон
            try:
                parsed_message = json.loads(message_str)
            except json.JSONDecodeError as e:
                logger.warning(t("non_json_message", message=message_str[:50]))
                logger.debug(t("json_decode_error", error=str(e)))
                return
            
            message_type = parsed_message.get("type", "unknown")
            logger.debug(t("received_message_type", type=message_type))
            
            # Другие типы
            if message_type == "channel_handshake":
                channel_id = parsed_message.get("data", {}).get("message", {}).get("channelId")
                if channel_id:
                    logger.info(t("channel_handshake_received", channel_id=channel_id))
            
            elif message_type == "ping":
                await self._send_pong()
                logger.debug(t("ping_received"))
            
            elif message_type == "pong":
                logger.debug(t("pong_received"))
            
            elif message_type == "error":
                error_msg = parsed_message.get("data", {}).get("message", "Unknown error")
                logger.error(t("websocket_error", error=error_msg))
            
            elif message_type == "user_event":
                event_name = parsed_message.get("data", {}).get("message", {}).get("name")
                logger.debug(t("user_event_received", event_name=event_name))
            
            else:
                if logger.level("DEBUG").no >= logger.level("DEBUG").no:
                    logger.debug(t("unknown_message_type", type=message_type))
            
        except Exception as e:
            logger.error(t("message_handling_error", error=str(e)))
            logger.debug(t("message_handling_traceback", traceback=traceback.format_exc()))

    async def _handle_reconnection(self):
        if self.state.reconnect_attempts < self.state.max_reconnect_attempts:
            self.state.reconnect_attempts += 1
            logger.info(t("attempting_reconnect", attempt=self.state.reconnect_attempts, max=self.state.max_reconnect_attempts))
            
            await self._cleanup_tasks()
            await asyncio.sleep(5)
            await self.connect()
        else:
            logger.error(t("max_reconnection_attempts"))
            await self.disconnect()

    async def _cleanup_tasks(self):
        self._running = False
        
        if self.handshake_task and not self.handshake_task.done():
            self.handshake_task.cancel()
            try:
                await self.handshake_task
            except asyncio.CancelledError:
                pass
            
        if self.tracking_task and not self.tracking_task.done():
            self.tracking_task.cancel()
            try:
                await self.tracking_task
            except asyncio.CancelledError:
                pass

    async def disconnect(self):
        logger.info(t("websocket_closed"))
        self.state.is_connected = False
        await self._cleanup_tasks()
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug(t("error_closing_websocket", error=str(e)))

    async def _send_handshake(self):
        if not self.state.is_connected:
            return
            
        payload = {
            "type": "channel_handshake",
            "data": {
                "message": {
                    "channelId": int(self.data.get("channelId", 0)),
                }
            }
        }

        try:
            await self.ws.send(Message.from_text(json.dumps(payload)))
            logger.debug(t("sent_handshake", channel_id=self.data.get('channelId', 'unknown')))
        except Exception as e:
            logger.error(t("failed_send_handshake", error=str(e)))
            logger.debug(t("handshake_traceback", traceback=traceback.format_exc()))
            self.state.is_connected = False

    async def _send_ping(self):
        if not self.state.is_connected:
            return
            
        payload = {"type": "ping"}

        try:
            await self.ws.send(Message.from_text(json.dumps(payload)))
            logger.debug(t("sent_ping"))
        except Exception as e:
            logger.error(t("failed_send_ping", error=str(e)))
            logger.debug(t("ping_traceback", traceback=traceback.format_exc()))
            self.state.is_connected = False

    async def _send_pong(self):
        if not self.state.is_connected:
            return
            
        payload = {
            "type": "pong"
        }

        try:
            await self.ws.send(Message.from_text(json.dumps(payload)))
            logger.debug(t("sent_pong"))
        except Exception as e:
            logger.error(t("failed_send_pong", error=str(e)))
            logger.debug(t("pong_traceback", traceback=traceback.format_exc()))

    async def _send_user_event(self):
        if not self.state.is_connected:
            return
            
        payload = {
            "type": "user_event",
            "data": {
                "message": {
                    "name": "tracking.user.watch.livestream",
                    "channel_id": int(self.data.get("channelId", 0)),
                    "livestream_id": int(self.data.get("streamId", 0)),
                }
            }
        }

        try:
            await self.ws.send(Message.from_text(json.dumps(payload)))
            logger.debug(t("sent_user_event", channel_id=self.data.get('channelId', 'unknown'), stream_id=self.data.get('streamId', 'unknown')))
        except Exception as e:
            logger.error(t("failed_send_user_event", error=str(e)))
            logger.debug(t("user_event_traceback", traceback=traceback.format_exc()))

            self.state.is_connected = False
