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

class PointsAmount:
    def __init__(self):
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
            "Referer": "https://kick.com/",
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
            logger.info(t("initializing_points_session"))
            response = self.session.get("https://kick.com")
            
            logger.debug(t("base_page_status", status=response.status_code))
            if response.status_code == 200:
                logger.success(t("points_bypass_success"))
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
            if 'br' in content_encoding and len(content) > 0:
                try:
                    return brotli.decompress(content).decode('utf-8')
                except Exception as e:
                    logger.warning(t("brotli_decompression_failed", error=str(e)))
            elif 'gzip' in content_encoding and len(content) > 0:
                try:
                    buf = BytesIO(content)
                    with gzip.GzipFile(fileobj=buf) as f:
                        return f.read().decode('utf-8')
                except Exception as e:
                    logger.warning(t("gzip_decompression_failed", error=str(e)))
            elif 'deflate' in content_encoding and len(content) > 0:
                try:
                    return zlib.decompress(content, -zlib.MAX_WBITS).decode('utf-8')
                except Exception as e:
                    logger.warning(t("deflate_decompression_failed", error=str(e)))
            
            return content.decode('utf-8', errors='ignore')
                
        except Exception as e:
            logger.error(t("decompression_failed", error=str(e)))
            try:
                return content.decode('utf-8', errors='ignore')
            except:
                return str(content)
    
    def get_amount(self, username: str, token: str) -> int:
        """Количество поинтов для пользователя"""
        self.session.headers["Authorization"] = f"Bearer {token}"

        try:
            logger.info(t("getting_points_amount", username=username))
            
            headers = {
                "Referer": f"https://kick.com/{username}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br"
            }
            
            response = self.session.get(
                f"https://kick.com/api/v2/channels/{username}/points",
                headers=headers
            )
            
            logger.debug(t("points_api_status", username=username, status=response.status_code))
            
            if response.status_code == 404:
                logger.warning(t("points_endpoint_changed", username=username))
                # Попробуем альт эндпоинт
                return self._get_points_alternative(username, token)
            
            if response.status_code != 200:
                logger.error(t("failed_get_points", username=username, status=response.status_code))
                response_text = self._decompress_response(response)
                logger.debug(t("response", response=response_text[:500]))
                return 0
                
            # Распаковываем и парсим ответ
            response_text = self._decompress_response(response)
            try:
                data = json.loads(response_text)
                logger.debug(t("points_response_structure", structure=list(data.keys())))
            except Exception as e:
                logger.error(t("json_parsing_error", error=str(e)))
                logger.debug(t("response_text", text=response_text[:500]))
                return 0
            
            # Извлекаем количество поинтов
            points = 0
            if 'data' in data and 'points' in data['data']:
                points = data['data']['points']
                logger.success(t("points_success", username=username, amount=points))
            elif 'points' in data:
                points = data['points']
                logger.success(t("points_success", username=username, amount=points))
            else:
                logger.warning(t("points_field_not_found", username=username))
                logger.debug(t("response_structure", structure=json.dumps(data, indent=2)[:300]))
            
            return points
            
        except Exception as e:
            logger.error(t("error_getting_points", username=username, error=str(e)))
            logger.debug(t("points_traceback", traceback=traceback.format_exc()))
            return 0
    
    def _get_points_alternative(self, username: str, token: str) -> int:
        """Альт метод получения поинтов"""
        try:
            logger.info(t("trying_alternative_points", username=username))
            
            headers = {
                "Referer": f"https://kick.com/{username}/",
                "Origin": "https://kick.com",
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Authorization": f"Bearer {token}"
            }
            
            response = self.session.get(
                f"https://kick.com/api/v2/channels/{username}",
                headers=headers
            )
            
            if response.status_code != 200:
                logger.error(t("alternative_failed", status=response.status_code))
                return 0
            
            response_text = self._decompress_response(response)
            data = json.loads(response_text)
            
            if 'data' in data and 'user' in data['data'] and 'points' in data['data']['user']:
                points = data['data']['user']['points']
                logger.success(t("points_alternative_success", username=username, amount=points))
                return points
            
            logger.warning(t("points_not_found_alternative"))
            return 0
            
        except Exception as e:
            logger.error(t("alternative_error", error=str(e)))

            return 0
