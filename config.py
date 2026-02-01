import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = 7973988177
    
    # Web App
    WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
    WEB_PORT = int(os.getenv("WEB_PORT", 8080))
    SECRET_KEY = os.getenv("SECRET_KEY", "monkey-stars-secret-key")
    
    # Database
    DB_PATH = "monkey_stars.db"
    
    # Game Settings
    CLICK_REWARD = 0.2
    CLICK_COOLDOWN = 3600
    REFERRAL_REWARD_REFERRER = 3.0
    REFERRAL_REWARD_REFEREE = 2.0
    CLICK_REFERRAL_PERCENT = 10
    
    # Games RTP
    GAMES = {
        'flip': {
            'win_chance': 0.49,
            'multiplier': 2.0,
            'special_event_chance': 0.015,
        },
        'crash': {
            'instant_crash_chance': 0.6,
            'low_multiplier_range': (1.0, 1.1),
        },
        'slot': {
            'winning_combinations': 1,
            'total_combinations': 27,
            'win_multiplier': 20,
        }
    }
