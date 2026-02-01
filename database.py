import aiosqlite
import time
from config import Config

class Database:
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
    
    async def init_db(self):
        """Инициализация базы данных"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance REAL DEFAULT 0.0,
                    referrer_id INTEGER DEFAULT NULL,
                    last_click INTEGER DEFAULT NULL,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS sponsors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_username TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_url TEXT NOT NULL
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_sponsors (
                    user_id INTEGER,
                    sponsor_id INTEGER,
                    is_subscribed BOOLEAN DEFAULT 0,
                    PRIMARY KEY (user_id, sponsor_id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    status TEXT DEFAULT 'pending',
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    type TEXT,
                    description TEXT,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            ''')
            
            await db.commit()
    
    # Методы для работы с пользователями
    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            return await cursor.fetchone()
    
    async def create_user(self, user_id: int, username: str, referrer_id: int = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''INSERT OR IGNORE INTO users (user_id, username, referrer_id) 
                   VALUES (?, ?, ?)''',
                (user_id, username, referrer_id)
            )
            await db.commit()
    
    async def update_balance(self, user_id: int, amount: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (amount, user_id)
            )
            await db.commit()
    
    async def add_transaction(self, user_id: int, amount: float, type: str, description: str = ""):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''INSERT INTO transactions (user_id, amount, type, description) 
                   VALUES (?, ?, ?, ?)''',
                (user_id, amount, type, description)
            )
            await db.commit()
    
    # Методы для спонсоров
    async def get_sponsors(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM sponsors")
            return await cursor.fetchall()
    
    async def add_sponsor(self, channel_username: str, channel_id: str, channel_url: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''INSERT INTO sponsors (channel_username, channel_id, channel_url) 
                   VALUES (?, ?, ?)''',
                (channel_username, channel_id, channel_url)
            )
            await db.commit()
    
    async def delete_sponsor(self, sponsor_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
            await db.commit()
    
    # Методы для проверки подписки
    async def update_user_sponsor(self, user_id: int, sponsor_id: int, is_subscribed: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                '''INSERT OR REPLACE INTO user_sponsors (user_id, sponsor_id, is_subscribed) 
                   VALUES (?, ?, ?)''',
                (user_id, sponsor_id, int(is_subscribed))
            )
            await db.commit()
    
    async def get_user_sponsors_status(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT s.*, us.is_subscribed 
                FROM sponsors s 
                LEFT JOIN user_sponsors us ON s.id = us.sponsor_id AND us.user_id = ?
            ''', (user_id,))
            return await cursor.fetchall()
    
    # Методы для рефералов
    async def get_user_referrals(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE referrer_id = ?",
                (user_id,)
            )
            total = (await cursor.fetchone())[0]
            
            # Активные рефералы (которые подписаны на спонсоров)
            cursor = await db.execute('''
                SELECT COUNT(DISTINCT u.user_id) 
                FROM users u 
                JOIN user_sponsors us ON u.user_id = us.user_id 
                WHERE u.referrer_id = ? AND us.is_subscribed = 1
            ''', (user_id,))
            active = (await cursor.fetchone())[0]
            
            return total, active
    
    # Методы для выводов
    async def create_withdrawal(self, user_id: int, amount: float):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                '''INSERT INTO withdrawals (user_id, amount) 
                   VALUES (?, ?) RETURNING id''',
                (user_id, amount)
            )
            withdrawal_id = (await cursor.fetchone())[0]
            await db.commit()
            return withdrawal_id
    
    async def get_withdrawals(self, status: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            if status:
                cursor = await db.execute(
                    '''SELECT w.*, u.username 
                       FROM withdrawals w 
                       JOIN users u ON w.user_id = u.user_id 
                       WHERE w.status = ? 
                       ORDER BY w.created_at DESC''',
                    (status,)
                )
            else:
                cursor = await db.execute(
                    '''SELECT w.*, u.username 
                       FROM withdrawals w 
                       JOIN users u ON w.user_id = u.user_id 
                       ORDER BY w.created_at DESC'''
                )
            return await cursor.fetchall()
    
    async def update_withdrawal_status(self, withdrawal_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE withdrawals SET status = ? WHERE id = ?",
                (status, withdrawal_id)
            )
            await db.commit()
    
    # Админ методы
    async def get_all_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM users ORDER BY created_at DESC"
            )
            return await cursor.fetchall()
    
    async def get_stats(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT SUM(balance) FROM users")
            total_balance = (await cursor.fetchone())[0] or 0
            
            cursor = await db.execute(
                "SELECT SUM(amount) FROM transactions WHERE type IN ('game_lose', 'click')"
            )
            total_income = (await cursor.fetchone())[0] or 0
            
            return {
                'total_users': total_users,
                'total_balance': total_balance,
                'total_income': total_income
            }
