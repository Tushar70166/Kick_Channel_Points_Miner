import cloudscraper
import json
import re
from urllib.parse import unquote
from loguru import logger
import time
import random
import traceback
import brotli
import zlib
import gzip
from io import BytesIO
from localization import t

class KickPoints:
    def __init__(self, token: str):
        self.token = token
        # Используем cloudscraper с brotli
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
                'mobile': False
            },
            delay=10,
            interpreter='nodejs'
        )
        
        #необходимые заголовки
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://kick.com",
            "Referer": "https://kick.com/",
            "Sec-Ch-Ua": '"Chromium";v="120", "Google Chrome";v="120", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "X-Client-Token": "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823",
            "X-Requested-With": "XMLHttpRequest",
            "Authorization": f"Bearer {self.token}",
            "Connection": "keep-alive"
        })
        
        self._initialize_session()
    
    def _initialize_session(self):
        """Сессия с обходом клоудфлеер"""
        try:
            logger.info(t("initializing_session"))
            response = self.session.get("https://kick.com")
            
            logger.debug(t("base_page_status", status=response.status_code))
            if response.status_code == 200:
                logger.success(t("bypass_success"))
                logger.debug(t("cookies_after_bypass", cookies=dict(self.session.cookies)))
            else:
                logger.error(t("failed_bypass", status=response.status_code))
                logger.debug(t("response_content", content=response.text[:500]))
            
            # Куки
            essential_cookies = {
                "cookie_preferences_set_v1": "%7B%22state%22%3A%7B%22preferences%22%3A%7B%22necessary%22%3Atrue%2C%22functional%22%3Atrue%2C%22performance%22%3Atrue%2C%22targeting%22%3Atrue%2C%22userHasMadeChoice%22%3Atrue%7D%2C%22functionalEnabled%22%3Atrue%2C%22performanceEnabled%22%3Atrue%2C%22targetingEnabled%22%3Atrue%7D%2C%22version%22%3A0%7D",
                "showMatureContent": "true",
                "USER_LOCALE": "en"
            }
            
            for name, value in essential_cookies.items():
                self.session.cookies.set(name, value, domain="kick.com")
            
            time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            logger.error(t("session_init_error", error=str(e)))
            logger.debug(t("init_traceback", traceback=traceback.format_exc()))
    
    def _decompress_response(self, response):
        """Ручная распаковка сжатых ответов"""
        content_encoding = response.headers.get('content-encoding', '').lower()
        content = response.content
        
        try:
            # Данные распакованны или нет
            try:
                json.loads(content.decode('utf-8', errors='ignore'))
                return content.decode('utf-8', errors='ignore')
            except:
                pass
            
            if 'br' in content_encoding and len(content) > 0:
                # Распаковка brotli
                try:
                    return brotli.decompress(content).decode('utf-8')
                except Exception as e:
                    logger.warning(t("brotli_decompression_failed", error=str(e)))
            elif 'gzip' in content_encoding and len(content) > 0:
                # Распаковка gzip
                try:
                    buf = BytesIO(content)
                    with gzip.GzipFile(fileobj=buf) as f:
                        return f.read().decode('utf-8')
                except Exception as e:
                    logger.warning(t("gzip_decompression_failed", error=str(e)))
            elif 'deflate' in content_encoding and len(content) > 0:
                # Распаковка deflate
                try:
                    return zlib.decompress(content, -zlib.MAX_WBITS).decode('utf-8')
                except Exception as e:
                    logger.warning(t("deflate_decompression_failed", error=str(e)))
            
            # если не получилось пытаемся так 
            return content.decode('utf-8', errors='ignore')
                
        except Exception as e:
            logger.error(t("decompression_failed", error=str(e)))
            try:
                return content.decode('utf-8', errors='ignore')
            except:
                return str(content)
    
    def get_ws_token(self, streamer_name: str) -> str:
        """Получаем Вебсокет токен с обходом"""
        
        # Есть ли критические куки
        if "cf_clearance" not in self.session.cookies and "__cf_bm" not in self.session.cookies:
            logger.warning(t("no_cloudflare_cookies"))
            self._initialize_session()
        
        try:
            logger.info(t("getting_channel_data", streamer=streamer_name))
            
            # Инфа о канале
            channel_url = f"https://kick.com/api/v2/channels/{streamer_name}"
            channel_headers = {
                "Referer": f"https://kick.com/{streamer_name}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br"
            }
            
            channel_response = self.session.get(channel_url, headers=channel_headers)
            logger.debug(t("channel_api_status", status=channel_response.status_code))
            
            if channel_response.status_code != 200:
                logger.error(t("failed_get_channel_data", status=channel_response.status_code))
                logger.debug(t("response_headers", headers=dict(channel_response.headers)))
                logger.debug(t("channel_response_content", content=channel_response.text[:500]))
                return None
            
            # Распаковываем и парсим ответ
            try:
                response_text = self._decompress_response(channel_response)
                channel_data = json.loads(response_text)
                logger.debug(t("channel_data_structure", data=json.dumps(channel_data, indent=2)[:300]))
            except Exception as e:
                logger.error(t("json_parsing_error", error=str(e)))
                logger.debug(t("response_text", text=response_text[:500]))
                return None
            
            # структура ответа
            if 'data' in channel_data:
                # Старая структура
                channel_info = channel_data['data']
            elif 'id' in channel_data:
                # Новая структура
                channel_info = channel_data
            else:
                logger.error(t("unexpected_structure"))
                return None
            
            channel_id = channel_info.get('id')
            user_id = channel_info.get('user_id') or channel_info.get('user', {}).get('id')
            
            if not channel_id:
                logger.error(t("channel_id_not_found"))
                return None
            
            if not user_id:
                logger.warning(t("user_id_not_found"))
                user_id = channel_id
            
            logger.info(t("channel_ids_info", channel_id=channel_id, user_id=user_id))
            
            # получаем токен для WebSocket
            ws_url = "https://websockets.kick.com/viewer/v1/token"
            ws_headers = {
                "Referer": f"https://kick.com/{streamer_name}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip, deflate, br",
                "X-Chatroom": str(channel_id),
                "X-User-Id": str(user_id)
            }
            
            ws_response = self.session.get(
                ws_url,
                headers=ws_headers
            )
            
            logger.debug(t("websocket_token_api_status", status=ws_response.status_code))
            
            if ws_response.status_code != 200:
                logger.error(t("failed_get_websocket_token", status=ws_response.status_code))
                logger.debug(t("response", response=self._decompress_response(ws_response)))
                return None
            
            # Распаковываем и парсим ответ
            try:
                ws_response_text = self._decompress_response(ws_response)
                ws_data = json.loads(ws_response_text)
                logger.debug(t("websocket_token_response", data=json.dumps(ws_data, indent=2)[:300]))
            except Exception as e:
                logger.error(t("websocket_json_parsing_error", error=str(e)))
                logger.debug(t("websocket_response_text", text=ws_response_text[:500]))
                return None
            
            # Извлекаем токен
            ws_token = None
            if 'data' in ws_data:
                if 'token' in ws_data['data']:
                    ws_token = ws_data['data']['token']
                elif 'websocket_token' in ws_data['data']:
                    ws_token = ws_data['data']['websocket_token']
            elif 'token' in ws_data:
                ws_token = ws_data['token']
            elif 'websocket_token' in ws_data:
                ws_token = ws_data['websocket_token']
            
            if ws_token:
                logger.success(t("websocket_success", token=ws_token))
                return ws_token
            
            logger.error(t("websocket_not_found"))
            return None
            
        except Exception as e:
            logger.error(t("critical_error", error=str(e)))
            logger.debug(t("critical_traceback", traceback=traceback.format_exc()))

            return None
