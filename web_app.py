from aiohttp import web
import aiohttp_jinja2
import jinja2
import hashlib
import hmac
import random
import time
from database import Database
from config import Config

db = Database()

@aiohttp_jinja2.template('login.html')
async def login_page(request):
    return {}

async def login_handler(request):
    data = await request.post()
    
    # Проверка данных от Telegram Widget
    if 'hash' not in data:
        return web.HTTPFound('/')
    
    # Проверяем подпись Telegram
    check_string = "\n".join([
        f"{k}={v}" for k, v in sorted(data.items()) 
        if k != 'hash'
    ])
    
    secret_key = hashlib.sha256(Config.BOT_TOKEN.encode()).digest()
    hmac_string = hmac.new(
        secret_key,
        check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if hmac_string != data['hash']:
        return web.HTTPFound('/')
    
    user_id = int(data['id'])
    username = data.get('username', f'user_{user_id}')
    
    # Создаем/обновляем пользователя
    await db.create_user(user_id, username)
    
    # Устанавливаем сессию
    response = web.HTTPFound('/games')
    response.set_cookie('user_id', str(user_id))
    response.set_cookie('username', username)
    
    return response

@aiohttp_jinja2.template('games.html')
async def games_page(request):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return web.HTTPFound('/')
    
    user = await db.get_user(int(user_id))
    if not user:
        return web.HTTPFound('/')
    
    return {'balance': user[2], 'user_id': user_id}

@aiohttp_jinja2.template('profile.html')
async def profile_page(request):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return web.HTTPFound('/')
    
    user = await db.get_user(int(user_id))
    if not user:
        return web.HTTPFound('/')
    
    total_ref, active_ref = await db.get_user_referrals(int(user_id))
    
    return {
        'user_id': user_id,
        'username': user[1],
        'balance': user[2],
        'total_ref': total_ref,
        'active_ref': active_ref
    }

@aiohttp_jinja2.template('admin.html')
async def admin_page(request):
    user_id = request.cookies.get('user_id')
    if not user_id or int(user_id) != Config.ADMIN_ID:
        return web.HTTPFound('/')
    
    stats = await db.get_stats()
    sponsors = await db.get_sponsors()
    withdrawals = await db.get_withdrawals()
    
    return {
        'stats': stats,
        'sponsors': sponsors,
        'withdrawals': withdrawals
    }

async def play_game(request):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return web.json_response({'error': 'Not authorized'}, status=401)
    
    data = await request.json()
    game_type = data.get('game')
    bet = float(data.get('bet', 0))
    
    user = await db.get_user(int(user_id))
    if not user or user[2] < bet:
        return web.json_response({'error': 'Insufficient balance'}, status=400)
    
    result = {}
    
    if game_type == 'flip':
        # Monkey Flip
        choice = data.get('choice')
        
        # Специальное событие (1.5% шанс проигрыша)
        if random.random() < Config.GAMES['flip']['special_event_chance']:
            win = False
            multiplier = 0
        else:
            win_chance = Config.GAMES['flip']['win_chance']
            win = random.random() < win_chance
            multiplier = Config.GAMES['flip']['multiplier'] if win else 0
        
        result = {
            'win': win,
            'multiplier': multiplier,
            'amount': bet * multiplier if win else 0
        }
    
    elif game_type == 'crash':
        # Banana Crash
        instant_crash = random.random() < Config.GAMES['crash']['instant_crash_chance']
        
        if instant_crash:
            multiplier = 1.0
            win = False
        else:
            # 2% шанс на высокий множитель
            if random.random() < 0.02:
                multiplier = random.uniform(1.5, 5.0)
            else:
                multiplier = random.uniform(*Config.GAMES['crash']['low_multiplier_range'])
            
            # Игрок должен успеть забрать (имитация)
            player_cashout = random.uniform(1.0, multiplier * 0.8)
            win = player_cashout > 1.0
        
        result = {
            'win': win,
            'multiplier': multiplier if win else 1.0,
            'amount': bet * multiplier if win else 0
        }
    
    elif game_type == 'slot':
        # Слот
        combinations = Config.GAMES['slot']['total_combinations']
        winning_combos = Config.GAMES['slot']['winning_combinations']
        
        win = random.randint(1, combinations) <= winning_combos
        multiplier = Config.GAMES['slot']['win_multiplier'] if win else 0
        
        result = {
            'win': win,
            'multiplier': multiplier,
            'amount': bet * multiplier if win else 0
        }
    
    # Обновляем баланс
    if result['win']:
        await db.update_balance(int(user_id), result['amount'] - bet)
        await db.add_transaction(
            int(user_id),
            result['amount'] - bet,
            "game_win",
            f"Выигрыш в {game_type}: x{result['multiplier']:.2f}"
        )
    else:
        await db.update_balance(int(user_id), -bet)
        await db.add_transaction(
            int(user_id),
            -bet,
            "game_lose",
            f"Проигрыш в {game_type}"
        )
    
    # Получаем новый баланс
    user = await db.get_user(int(user_id))
    
    return web.json_response({
        **result,
        'new_balance': user[2]
    })

async def admin_action(request):
    user_id = request.cookies.get('user_id')
    if not user_id or int(user_id) != Config.ADMIN_ID:
        return web.json_response({'error': 'Access denied'}, status=403)
    
    data = await request.json()
    action = data.get('action')
    
    if action == 'add_sponsor':
        await db.add_sponsor(
            data['channel_username'],
            data['channel_id'],
            data['channel_url']
        )
        return web.json_response({'success': True})
    
    elif action == 'delete_sponsor':
        await db.delete_sponsor(int(data['sponsor_id']))
        return web.json_response({'success': True})
    
    elif action == 'update_withdrawal':
        await db.update_withdrawal_status(
            int(data['withdrawal_id']),
            data['status']
        )
        return web.json_response({'success': True})
    
    elif action == 'broadcast':
        # Здесь должна быть логика рассылки
        return web.json_response({'success': True, 'message': 'Рассылка начата'})
    
    return web.json_response({'error': 'Unknown action'}, status=400)

async def logout_handler(request):
    response = web.HTTPFound('/')
    response.del_cookie('user_id')
    response.del_cookie('username')
    return response

async def init_app():
    app = web.Application()
    
    # Настройка Jinja2
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader('templates')
    )
    
    # Роуты
    app.router.add_get('/', login_page)
    app.router.add_post('/login', login_handler)
    app.router.add_get('/games', games_page)
    app.router.add_get('/profile', profile_page)
    app.router.add_get('/admin', admin_page)
    app.router.add_post('/api/play', play_game)
    app.router.add_post('/api/admin', admin_action)
    app.router.add_get('/logout', logout_handler)
    
    # Статические файлы
    app.router.add_static('/static/', path='static', name='static')
    
    return app

if __name__ == '__main__':
    web.run_app(init_app(), host=Config.WEB_HOST, port=Config.WEB_PORT)
