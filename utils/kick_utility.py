import cloudscraper
import json
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

class KickUtility:
    def __init__(self, username: str):
        self.username = username
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
        
        # Необходимые заголовки
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://kick.com",
            "Referer": f"https://kick.com/{username}/",
            "Sec-Ch-Ua": '"Chromium";v="120", "Google Chrome";v="120", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "X-Client-Token": "e1393935a959b4020a4491574f6490129f678acdaa92760471263db43487f823",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive"
        })
        
        self._initialize_session()
    
    def _initialize_session(self):
        """Сессия с обходом клоудфлеер"""
        try:
            logger.info(t("initializing_utility_session"))
            response = self.session.get("https://kick.com")
            
            logger.debug(t("base_page_status", status=response.status_code))
            if response.status_code == 200:
                logger.success(t("utility_bypass_success"))
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
    
    def get_stream_id(self, token: str) -> int:
        """Получаем ID живого стрима"""
        self.session.headers["Authorization"] = f"Bearer {token}"
        
        try:
            logger.info(t("getting_livestream_info", username=self.username))
            
            headers = {
                "Referer": f"https://kick.com/{self.username}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br"
            }
            
            response = self.session.get(
                f"https://kick.com/api/v2/channels/{self.username}/livestream",
                headers=headers
            )
            
            logger.debug(t("livestream_api_status", status=response.status_code))
            
            if response.status_code != 200:
                logger.warning(t("no_active_livestream", status=response.status_code))
                # Тру получить ID из общих данных канала
                return self._get_stream_id_from_channel(token)
            
            # Распаковываем и парсим ответ
            try:
                response_text = self._decompress_response(response)
                data = json.loads(response_text)
                logger.debug(t("livestream_data", data=json.dumps(data, indent=2)[:300]))
            except Exception as e:
                logger.error(t("json_parsing_error", error=str(e)))
                return None
            
            # ID стрима
            if 'data' in data and 'id' in data['data']:
                stream_id = data['data']['id']
                logger.success(t("livestream_id_success", stream_id=stream_id))
                return stream_id
            elif 'id' in data:
                stream_id = data['id']
                logger.success(t("livestream_id_success", stream_id=stream_id))
                return stream_id
            
            logger.warning(t("no_livestream_found"))
            return None
            
        except Exception as e:
            logger.error(t("error_getting_livestream", error=str(e)))
            logger.debug(t("livestream_traceback", traceback=traceback.format_exc()))
            return None
    
    def _get_stream_id_from_channel(self, token: str) -> int:
        """Доп метод получения ID стрима из данных канала"""
        self.session.headers["Authorization"] = f"Bearer {token}"
        
        try:
            logger.info(t("getting_stream_id_from_channel", username=self.username))
            
            headers = {
                "Referer": f"https://kick.com/{self.username}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br"
            }
            
            response = self.session.get(
                f"https://kick.com/api/v2/channels/{self.username}",
                headers=headers
            )
            
            logger.debug(t("channel_api_status", status=response.status_code))
            
            if response.status_code != 200:
                logger.error(t("channel_api_failed", status=response.status_code))
                return None
            
            # Распаковываем и парсим ответ
            try:
                response_text = self._decompress_response(response)
                data = json.loads(response_text)
                logger.debug(t("channel_data_response", data=json.dumps(data, indent=2)[:300]))
            except Exception as e:
                logger.error(t("json_parsing_error", error=str(e)))
                return None
            
            # livestream ID
            if 'data' in data:
                channel_data = data['data']
                if 'livestream' in channel_data and channel_data['livestream'] and 'id' in channel_data['livestream']:
                    stream_id = channel_data['livestream']['id']
                    logger.success(t("livestream_id_from_channel", stream_id=stream_id))
                    return stream_id
            
            logger.warning(t("no_livestream_found"))
            return None
            
        except Exception as e:
            logger.error(t("error_getting_stream_from_channel", error=str(e)))
            return None
    
    def get_channel_id(self, token: str) -> int:
        """ID канала"""
        self.session.headers["Authorization"] = f"Bearer {token}"
        
        try:
            logger.info(t("getting_channel_id", username=self.username))
            
            headers = {
                "Referer": f"https://kick.com/{self.username}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br"
            }
            
            response = self.session.get(
                f"https://kick.com/api/v2/channels/{self.username}",
                headers=headers
            )
            
            logger.debug(t("channel_api_status", status=response.status_code))
            
            if response.status_code != 200:
                logger.error(t("channel_api_failed", status=response.status_code))
                logger.debug(t("response", response=self._decompress_response(response)))
                return None
            
            # Распаковываем и парсим ответ
            try:
                response_text = self._decompress_response(response)
                data = json.loads(response_text)
                logger.debug(t("channel_data_response", data=json.dumps(data, indent=2)[:300]))
            except Exception as e:
                logger.error(t("json_parsing_error", error=str(e)))
                return None
            
            # Извлекаем ID канала
            if 'data' in data and 'id' in data['data']:
                channel_id = data['data']['id']
                logger.success(t("channel_id_success", channel_id=channel_id))
                return channel_id
            elif 'id' in data:
                channel_id = data['id']
                logger.success(t("channel_id_success", channel_id=channel_id))
                return channel_id
            
            logger.error(t("channel_id_not_found_response"))
            return None
            
        except Exception as e:
            logger.error(t("error_getting_channel_id", error=str(e)))
            logger.debug(t("channel_id_traceback", traceback=traceback.format_exc()))

            return None
