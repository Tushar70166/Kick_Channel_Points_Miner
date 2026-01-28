import asyncio
import json
import traceback
import random
import sys
import os
import time
from datetime import datetime, timedelta
import subprocess

from _websockets.ws_token import KickPoints
from _websockets.ws_connect import KickWebSocket
from utils.kick_utility import KickUtility
from utils.get_points_amount import PointsAmount
from localization import load_language, t
from loguru import logger

from tg_bot.bot import TelegramBot

import web_server

points_tracker = {}
last_points_update = {}
config = {}
telegram_bot = None

async def monitor_points_progress():
    """проверяет, идут ли начисления"""
    while True:
        await asyncio.sleep(60)
        
        current_time = datetime.now()
        streamers_to_restart = []
        
        for streamer_name, last_update in list(last_points_update.items()):
            time_diff = current_time - last_update
            
            if time_diff > timedelta(minutes=10):
                logger.warning(f"⚠️ {streamer_name}: No points for {int(time_diff.total_seconds()//60)} min")
                streamers_to_restart.append(streamer_name)
        
        if streamers_to_restart:
            logger.critical(f"🔄 Restart needed for: {', '.join(streamers_to_restart)}")
            
            if telegram_bot and telegram_bot.active:
                await telegram_bot.send_alert(streamers_to_restart)
                await telegram_bot.send_restart_notification()
            
            logger.info("Exiting for restart...")
            os._exit(1)

async def check_points_periodically(streamer_name, token, kick_utility):
    """опрос баланса (API)"""
    global points_tracker, last_points_update
    
    if streamer_name not in points_tracker:
        points_tracker[streamer_name] = {"last": 0, "history": []}
        last_points_update[streamer_name] = datetime.now()
    
    while True:
        try:
            await asyncio.sleep(random.randint(120, 180)) 
            
            stream_id = kick_utility.get_stream_id(token)
            
            points_amount = PointsAmount()
            amount = points_amount.get_amount(streamer_name, token)
            
            if amount is None:
                continue

            current_time = datetime.now()
            last_points_update[streamer_name] = current_time
            
            web_server.update_streamer_info(streamer_name, amount, current_time, stream_id)

            if telegram_bot and telegram_bot.active:
                telegram_bot.set_points_data(streamer_name, amount)

            last_amount = points_tracker[streamer_name]["last"]
            
            if amount > last_amount:
                gain = amount - last_amount
                logger.success(f"💰 {streamer_name}: +{gain} (Total: {amount})")
                
                points_tracker[streamer_name]["last"] = amount
                points_tracker[streamer_name]["history"].append((current_time, amount))
                
                if gain >= 10 and telegram_bot and telegram_bot.active:
                    await telegram_bot.send_points_update(streamer_name, last_amount, amount)
            
            elif amount < last_amount:
                points_tracker[streamer_name]["last"] = amount
                
        except Exception as e:
            logger.error(f"Error checking points for {streamer_name}: {e}")


async def handle_streamer(streamer_name):
    """работа с WebSocket одного стримера"""
    token = config['Private']['token']
    
    await asyncio.sleep(random.uniform(2, 10))
    logger.info(f"🔌 Connecting to {streamer_name}...")
    
    try:
        kick_points = KickPoints(token)
        ws_token = kick_points.get_ws_token(streamer_name)
        
        if not ws_token:
            raise Exception("Failed to get WS Token")
            
        kick_utility = KickUtility(streamer_name)
        stream_id = kick_utility.get_stream_id(token)
        channel_id = kick_utility.get_channel_id(token)
        
        if not channel_id:
             raise Exception("Failed to get Channel ID")
        
        points_amount = PointsAmount()
        initial_points = points_amount.get_amount(streamer_name, token)
        if initial_points is not None:
            web_server.update_streamer_info(streamer_name, initial_points, datetime.now(), stream_id)
        
        kick_websocket_client = KickWebSocket({
            "token": ws_token,
            "streamId": stream_id if stream_id else 0,
            "channelId": channel_id
        })
        
        ws_task = asyncio.create_task(kick_websocket_client.connect())
        points_task = asyncio.create_task(check_points_periodically(streamer_name, token, kick_utility))
        
        if telegram_bot and telegram_bot.active:
            await telegram_bot.send_streamer_started(streamer_name)
            
        await asyncio.gather(ws_task, points_task)
        
    except Exception as e:
        logger.error(f"❌ Error with {streamer_name}: {e}")
        if telegram_bot and telegram_bot.active:
            await telegram_bot.send_streamer_error(streamer_name, str(e))

async def main():
    global config, telegram_bot
    
    # 1. Загрузка конфига
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        logger.remove()

        log_level = "DEBUG" if config.get("Debug", False) else "INFO"
        
        logger.add(sys.stderr, level=log_level)
        logger.info(f"🔧 Log Level set to: {log_level}")

        lang = config.get("Language", "en")
        load_language(lang)
        
    except Exception as e:
        logger.add(sys.stderr, level="INFO")
        logger.critical(f"Config load error: {e}")
        return

    streamer_names = config.get('Streamers', [])

    # 2. Telegram Bot
    if config.get('Telegram', {}).get('enabled', False):
        try:
            telegram_bot = TelegramBot(config)
            telegram_bot.set_streamers(streamer_names)
            await telegram_bot.start() 
        except Exception as e:
            logger.error(f"Telegram start failed: {e}")

    # 3. Web Dashboard
    web_config = config.get("WebDashboard", {})
    if web_config.get("enabled", False):
        web_port = web_config.get("port", 5000)
        try:
            web_server.start_server(streamer_names, web_port)
            logger.info(f"🌍 Web Dashboard enabled on port {web_port}")
        except Exception as e:
            logger.error(f"Failed to start Web Dashboard: {e}")
    else:
        logger.info("🌍 Web Dashboard is disabled")

    # 4. Мониторинг и Стримеры
    monitor_task = asyncio.create_task(monitor_points_progress())
    
    tasks = [monitor_task]
    for streamer in streamer_names:
        tasks.append(asyncio.create_task(handle_streamer(streamer)))
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    
    while True:
        try:
            logger.info("🚀 Starting Miner...")
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("👋 Stopped by user")
            sys.exit(0)
        except SystemExit:
            # Этот блок ловит sys.exit(1) из Telegram бота
            logger.info("🔄 Restarting via SystemExit request...")
        except Exception as e:
            logger.critical(f"🔥 Fatal crash: {e}")
            traceback.print_exc()
        
        logger.info("🔄 Rebooting in 5 seconds...")
        time.sleep(5)

