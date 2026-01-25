import os
import json
import asyncio
import traceback
import html
import sys
from datetime import datetime
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from loguru import logger

# Заглушка для локализации
try:
    from localization import t as loc_t
    def t(key, **kwargs):
        val = loc_t(key, **kwargs)
        return val if val else key
except ImportError:
    def t(key, **kwargs):
        return key

class TelegramBot:
    def __init__(self, config):
        self.active = False
        self.application = None
        self.user_language = {}
        self.language_files = {}
        self.config = config
        self.streamers = []
        self.points_data = {}
        
        self.load_language_files()

    async def start(self):
        tg_conf = self.config.get('Telegram', {})
        if not tg_conf.get('enabled', False):
            logger.info("Telegram bot disabled in config.")
            return

        token = tg_conf.get('bot_token', '')
        if not token:
            logger.error("Telegram token not found!")
            return
        
        try:
            self.application = Application.builder().token(token).build()
            
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("balance", self.balance_command))
            self.application.add_handler(CommandHandler("restart", self.restart_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("language", self.language_command))
            
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)
            
            self.active = True
            logger.success("✅ Telegram bot initialized")
            
            await self.send_startup_notification()
            
        except Exception as e:
            logger.error(f"❌ Telegram init failed: {str(e)}")
            self.active = False

    def set_streamers(self, streamers):
        self.streamers = streamers
        safe_list = [html.escape(str(s)) for s in streamers]
        logger.info(f"Telegram streamers set: {', '.join(safe_list)}")
    
    def set_points_data(self, streamer_name, points):
        current_time = datetime.now().strftime("%H:%M:%S")
        if streamer_name not in self.points_data:
            self.points_data[streamer_name] = {"history": []}
            
        self.points_data[streamer_name].update({
            "amount": points,
            "last_update": current_time
        })
        self.points_data[streamer_name]["history"].append((current_time, points))
        if len(self.points_data[streamer_name]["history"]) > 10:
            self.points_data[streamer_name]["history"] = self.points_data[streamer_name]["history"][-10:]
    
    def load_language_files(self):
        lang_dir = "tg_bot/lang"
        if not os.path.exists(lang_dir):
            os.makedirs(lang_dir)
        for lang in ['en', 'ru']:
            file_path = os.path.join(lang_dir, f"{lang}.lang")
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.language_files[lang] = json.load(f)
                else:
                    self.language_files[lang] = {}
            except Exception as e:
                logger.error(f"Error loading lang {lang}: {e}")
                self.language_files[lang] = {}

    def get_text(self, key, lang='en', **kwargs):
        lang = lang.lower()
        lang_dict = self.language_files.get(lang, self.language_files.get('en', {}))
        text = lang_dict.get(key, f"🔑 {key}")
        return text.format(**kwargs)

    def get_keyboard(self, lang='en', is_admin=False):
        l = self.language_files.get(lang, self.language_files.get('en', {}))
        
        btn_stat = l.get("btn_status", "📊 Status")
        btn_bal = l.get("btn_balance", "💰 Balance")
        btn_help = l.get("btn_help", "❓ Help")
        
        keyboard = [[btn_stat, btn_bal]]
        
        if is_admin:
            btn_restart = l.get("btn_restart", "🔄 Restart")
            keyboard.append([btn_help, btn_restart])
        else:
            keyboard.append([btn_help])
            
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def is_user_allowed(self, user_id):
        conf = self.config.get('Telegram', {})
        allowed = conf.get('allowed_users', [])
        owner = conf.get('chat_id')
        
        safe_allowed = [str(u) for u in allowed]
        if owner:
            safe_allowed.append(str(owner))
            
        if not safe_allowed:
            return False
            
        return str(user_id) in safe_allowed

    def is_admin(self, user_id):
        owner = self.config.get('Telegram', {}).get('chat_id')
        return str(user_id) == str(owner)

    # Обработчики команд 

    async def start_command(self, update: Update, context):
        user_id = update.effective_user.id
        if not self.is_user_allowed(user_id): return
        
        default_lang = self.config.get("Language", "en")
        lang = self.user_language.get(user_id, default_lang)
        self.user_language[user_id] = lang
        
        is_admin = self.is_admin(user_id)
        
        await update.message.reply_text(
            self.get_text("start_message", lang),
            reply_markup=self.get_keyboard(lang, is_admin),
            parse_mode=ParseMode.HTML
        )

    async def handle_message(self, update: Update, context):
        user_id = update.effective_user.id
        if not self.is_user_allowed(user_id): return

        text = update.message.text
        lang = self.user_language.get(user_id, self.config.get("Language", "en"))
        l = self.language_files.get(lang, self.language_files.get('en', {}))

        if text == l.get("btn_status", "📊 Status"): await self.status_command(update, context)
        elif text == l.get("btn_balance", "💰 Balance"): await self.balance_command(update, context)
        elif text == l.get("btn_help", "❓ Help"): await self.help_command(update, context)
        elif text == l.get("btn_restart", "🔄 Restart"): await self.restart_command(update, context)

    async def status_command(self, update: Update, context):
        if not self.is_user_allowed(update.effective_user.id): return
        
        user_id = update.effective_user.id
        lang = self.user_language.get(user_id, self.config.get("Language", "en"))
        
        if not self.streamers:
            await update.message.reply_text(self.get_text("status_inactive", lang), parse_mode=ParseMode.HTML)
            return
        
        streamers_list = "\n".join([f"• <code>{html.escape(str(s))}</code>" for s in self.streamers])
        
        last_update = datetime.now().strftime("%H:%M:%S")
        rate = "120"
        
        await update.message.reply_text(
            self.get_text("status_active", lang, streamers=streamers_list, last_update=last_update, rate=rate),
            parse_mode=ParseMode.HTML
        )

    async def balance_command(self, update: Update, context):
        if not self.is_user_allowed(update.effective_user.id): return
        
        user_id = update.effective_user.id
        lang = self.user_language.get(user_id, self.config.get("Language", "en"))
        
        if not self.streamers:
            await update.message.reply_text(self.get_text("balance_no_streamers", lang), parse_mode=ParseMode.HTML)
            return

        messages = []
        for streamer in self.streamers:
            data = self.points_data.get(streamer, {"amount": 0, "last_update": "N/A"})
            msg = self.get_text("balance_info", lang, streamer=html.escape(str(streamer)), amount=data['amount'], time=data['last_update'])
            messages.append(msg)
            
        full_text = "\n\n".join(messages)
        if len(full_text) > 4000: full_text = full_text[:4000] + "..."
        
        await update.message.reply_text(full_text, parse_mode=ParseMode.HTML)

    async def restart_command(self, update: Update, context):
        user_id = update.effective_user.id
        
        if not self.is_user_allowed(user_id): return
        
        if not self.is_admin(user_id):
            lang = self.user_language.get(user_id, self.config.get("Language", "en"))
            await update.message.reply_text(self.get_text("not_enough_permissions", lang), parse_mode=ParseMode.HTML)
            return
        
        lang = self.user_language.get(user_id, self.config.get("Language", "en"))
        await update.message.reply_text(self.get_text("restart_confirmation", lang), parse_mode=ParseMode.HTML)
        await asyncio.sleep(1)
        logger.info("Restart requested via Telegram")
        sys.exit(1) 

    async def help_command(self, update: Update, context):
        if not self.is_user_allowed(update.effective_user.id): return
        user_id = update.effective_user.id
        lang = self.user_language.get(user_id, self.config.get("Language", "en"))
        await update.message.reply_text(self.get_text("help_message", lang), parse_mode=ParseMode.HTML)

    async def language_command(self, update: Update, context):
        user_id = update.effective_user.id
        
        if not self.is_user_allowed(user_id): return

        if not self.is_admin(user_id):
            lang = self.user_language.get(user_id, self.config.get("Language", "en"))
            await update.message.reply_text(self.get_text("not_enough_permissions", lang), parse_mode=ParseMode.HTML)
            return
        
        if not context.args:
            await update.message.reply_text("Usage: /language [en/ru]")
            return
            
        lang_code = context.args[0].lower()
        if lang_code in ['en', 'ru']:
            self.user_language[user_id] = lang_code
            await update.message.reply_text(
                self.get_text("language_changed", lang_code, language=lang_code.upper()),
                reply_markup=self.get_keyboard(lang_code, is_admin=True),
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text("Supported languages: en, ru")

    async def send_startup_notification(self):
        if not self.active: return
        owner = self.config.get('Telegram', {}).get('chat_id')
        if not owner: return
        
        streamers_list = "\n".join([f"• <code>{html.escape(str(s))}</code>" for s in self.streamers]) if self.streamers else "None"
        lang = self.user_language.get(int(owner), self.config.get("Language", "en"))
        await self.send_message(owner, self.get_text("startup_notification", lang, streamers=streamers_list))

    async def send_points_update(self, streamer_name, old_amount, new_amount):
        if not self.active: return
        gain = new_amount - old_amount
        if gain <= 0: return

        conf = self.config.get('Telegram', {})
        allowed = conf.get('allowed_users', [])
        owner = conf.get('chat_id')
        recipients = set(allowed)
        if owner: recipients.add(owner)
        
        for user_id in recipients:
            lang = self.user_language.get(int(user_id), self.config.get("Language", "en"))
            await self.send_message(user_id, self.get_text("points_updated", lang, streamer=streamer_name, amount=gain, total=new_amount))
            
    async def send_streamer_error(self, streamer_name, error_message):
        if not self.active: return
        owner = self.config.get('Telegram', {}).get('chat_id')
        if not owner: return
        
        safe_err = str(error_message)[:300]
        lang = self.user_language.get(int(owner), self.config.get("Language", "en"))
        await self.send_message(owner, self.get_text("streamer_error", lang, streamer=streamer_name, error=safe_err))

    async def send_streamer_started(self, streamer):
        if not self.active: return
        pass

    async def send_message(self, user_id, text):
        try:
            if self.application:
                await self.application.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send TG message to {user_id}: {e}")

    async def stop(self):
        if self.application:
            try:
                if self.application.updater.running:
                    await self.application.updater.stop()
                if self.application.running:
                    await self.application.stop()
                await self.application.shutdown()
                self.active = False
            except Exception as e:
                logger.error(f"Error stopping TG bot: {e}")
