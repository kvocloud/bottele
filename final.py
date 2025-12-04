import requests
import asyncio
import sys
import os
import time as time_module
import json
import hashlib
import base64
import socket
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, time
from collections import defaultdict
from pytz import timezone

from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler, JobQueue

# ==============================================================================
# 1. CẤU HÌNH TỪ FILE SETUP.TXT (CỦA tool.py)
# ==============================================================================

try:
    with open('setup.txt', 'r', encoding='utf-8') as file:
        lines = file.readlines()
        # Khai báo các biến từ setup.txt
        api_id = lines[0].strip().split('|')[1]
        api_hash = lines[1].strip().split('|')[1]
        phone = "+" + str(lines[2].strip().split('|')[1])
        time1 = lines[3].strip().split('|')[1]
        time_spam_from = int(time1.split('-')[0])
        time_spam_to = int(time1.split('-')[1])
        time2 = lines[4].strip().split('|')[1]
        time2_1 = time2.split('-')[0]
        time2_2 = time2.split('-')[1]
        time3 = lines[5].strip().split('|')[1]
        source = str(lines[6].strip().split('|')[1])
        mes_id1 = int(lines[7].strip().split('|')[1])
        mes_id2 = int(lines[8].strip().split('|')[1])
        already_id = int(lines[9].strip().split('|')[1])
        number_limit = int(lines[10].strip().split('|')[1])
        # TOKEN BOT CHÍNH (Sử dụng cho Application)
        BOT_TOKEN = lines[14].strip().split('|')[1] 
    print("Đã tải cấu hình từ setup.txt.")
except FileNotFoundError:
    print("LỖI: Không tìm thấy file setup.txt. Vui lòng tạo file cấu hình.")
    sys.exit(1) 

# ==============================================================================
# 2. CẤU HÌNH ADMIN VÀ CONSTANTS CHUNG (TÁCH BIỆT API)
# ==============================================================================

# Cấu hình Admin Smart Server (từ adminkvo.py)
SS_ADMIN_ACCOUNT = "kvocloud@gmail.com/Tungvu@23" # ⚠️ THAY BẰNG TÀI KHOẢN ADMIN THẬT CỦA BẠN 
TARGET_CHAT_ID = 7365030386 # ✅ CHAT ID ĐÃ ĐƯỢC XÁC NHẬN
AGENCY_NAME = "kvocloud" 
AGENCY_EMAIL = "kvocloud@gmail.com" 

# Thông tin API cố định SmartServer (dùng chung cho cả 2 hệ thống)
SS_API_TOKEN_URL = "https://api.smartserver.vn/api/token"
SS_API_USERS_URL = "https://api.smartserver.vn/api/sadmin/users"
SS_CLIENT_ID = "RqRtYo59WKhWIEg9E0iqg2RZWAg5yP1eiOg21hxb" 
# ✅ CẬP NHẬT THEO YÊU CẦU: Dùng API /api/server/list để kiểm tra VPS/Proxy hết hạn
SS_API_SERVICES_URL = "https://api.smartserver.vn/api/server/list" 

# Ngưỡng (Threshold) Tốn Tài nguyên
RESOURCE_THRESHOLD_SECONDS = 5.0
EXPIRATION_THRESHOLD_DAYS = 3 # Số ngày còn lại để cảnh báo hết hạn

# Hằng số chung (từ tool.py)
WAITING_FOR_PROXY_LIST = range(1)
IPINFO_API_KEY = '415603757b699'
GITHUB_TOKEN = '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' 
REPO = 'kvocloud/bottele'
FILE_PATH = 'key.json'
API_URL = f'https://api.github.com/repos/{REPO}/contents/{FILE_PATH}' # API cho GitHub
LAST_SEEN_CLIENT_ID_KEY = 'last_seen_client_id' 
VIETNAM = timezone("Asia/Ho_Chi_Minh") 
vu = "vncaytien6@gmail.com/Tungvu@23" # Tài khoản dùng cho scheduled_get (kvocloud.com)

################################################################################
# PHẦN A: HÀM API CORE CHO LẤY TOKEN & DATA
################################################################################

def get_ss_token(acc: str) -> str | None:
    """Lấy Access Token từ Smartserver API (dành cho sadmin.smartserver.vn)."""
    try:
        email, password = acc.split('/')
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://sadmin.smartserver.vn",
            "Referer": "https://sadmin.smartserver.vn/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        data = {
            "email": email,
            "password": password,
            "client_id": SS_CLIENT_ID, 
            "grant_type": "password"
        }

        response = requests.post(SS_API_TOKEN_URL, headers=headers, data=data, timeout=10)
        response.raise_for_status() 
        return response.json().get("access_token")

    except Exception as e:
        print(f"LỖI LẤY SS TOKEN (Admin): {e}")
        return None

def get_kvocloud_token(acc: str) -> str | None:
    """Lấy Access Token từ Smartserver API (dành cho manage.kvocloud.com)."""
    try:
        email, password = acc.split('/')
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://manage.kvocloud.com", # Header từ tool.py
            "Referer": "https://manage.kvocloud.com/", # Header từ tool.py
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        data = {
            "email": email,
            "password": password,
            "client_id": SS_CLIENT_ID, 
            "grant_type": "password"
        }

        response = requests.post(SS_API_TOKEN_URL, headers=headers, data=data, timeout=5)
        response.raise_for_status() 
        return response.json().get("access_token")

    except Exception as e:
        print(f"LỖI LẤY KVO CLOUD TOKEN (Client): {e}")
        return None

def get_latest_client_id(auth: str) -> tuple[int | None, str | None]:
    """Lấy ID và Email của người dùng mới nhất ĐÃ LỌC THEO site_name (AGENCY_NAME) từ Smartserver API."""
    url = SS_API_USERS_URL 
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {auth}"
    }
    params = {
        'page': 1, 
        'page_size': 1, 
        'site_name': AGENCY_NAME, 
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        clients = data.get("results") 
        if clients and isinstance(clients, list) and len(clients) > 0:
            latest_client = clients[0]
            return int(latest_client.get("id")), latest_client.get("email")
            
        return None, None
    except Exception as e:
        print(f"LỖI LỌC CLIENTS (SS API users): {e}")
        return None, None

def get_servers(auth: str, is_proxy: bool = False) -> tuple[dict, str]:
    """
    Lấy danh sách VPS/Proxy còn 3 ngày hết hạn từ Smartserver API (Server List API).
    Sử dụng URL mới: https://api.smartserver.vn/api/server/list
    Trả về (grouped_data, expiration_date)
    """
    url = SS_API_SERVICES_URL # Đã được cập nhật thành /api/server/list
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {auth}"
    }
    
    # Lọc tất cả dịch vụ đang hoạt động
    params = {
        'page': 1, 
        'page_size': 9999, # Lấy tất cả services
        'status': 'active'
    }

    # API Smartserver thường dùng 'type' để phân biệt VPS và Proxy
    service_type = 'proxy' if is_proxy else 'vps'

    try:
        # Lấy tất cả services
        res = requests.get(url, headers=headers, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        services = data.get("results", [])
        
        grouped_data = defaultdict(list)
        closest_expiration_date = None
        
        today = datetime.now(VIETNAM).date()
        
        for service in services:
            # Lọc theo loại (Proxy hoặc VPS)
            if service.get("type") != service_type:
                continue

            expired_at_str = service.get("expired_at")
            if not expired_at_str:
                continue

            # Chuyển đổi ngày hết hạn
            try:
                # Loại bỏ phần thời gian nếu có
                expired_date_part = expired_at_str.split('T')[0] 
                expired_date = datetime.strptime(expired_date_part, '%Y-%m-%d').date()
            except ValueError:
                continue
                
            # Tính số ngày còn lại
            remaining_days = (expired_date - today).days

            # Kiểm tra nếu còn đúng 3 ngày (EXPIRATION_THRESHOLD_DAYS)
            if remaining_days == EXPIRATION_THRESHOLD_DAYS:
                ip_address = service.get("ip_address")
                # Lấy tên khách hàng từ trường note
                note = service.get("note", "Khách hàng không tên") 
                
                if ip_address:
                    grouped_data[note].append(ip_address)
                
                # Cập nhật ngày hết hạn gần nhất (của nhóm này)
                if closest_expiration_date is None or expired_date < datetime.strptime(closest_expiration_date, "%d/%m/%Y").date():
                    closest_expiration_date = expired_date.strftime("%d/%m/%Y")
                
        return grouped_data, closest_expiration_date or "Chưa rõ"
        
    except Exception as e:
        print(f"LỖI API Smart Server (get_servers - {service_type}): {e}")
        return {}, "LỖI API"


################################################################################
# PHẦN B: HÀM HANDLERS & JOBS MỚI (TỪ adminkvo.py)
################################################################################

async def monitor_new_clients(context: ContextTypes.DEFAULT_TYPE):
    """Job chạy định kỳ để kiểm tra người dùng mới và báo cáo tài nguyên Smartserver."""
    start_time = time_module.time()
    chat_id = TARGET_CHAT_ID

    # 1. Lấy Token Smart Server (Admin)
    token = get_ss_token(SS_ADMIN_ACCOUNT)
    if not token:
        if context.job and context.job.data.get('check_resource'):
            await context.bot.send_message(chat_id, "⚠️ LỖI: Không lấy được Admin Token Smart Server trong quá trình quét định kỳ.")
        return
            
    # 2. Lấy thông tin người dùng mới nhất
    latest_id, latest_email = get_latest_client_id(token)
    
    end_time = time_module.time()
    elapsed_time = end_time - start_time

    # --- LOGIC CẢNH BÁO TÀI NGUYÊN ---
    if context.job and context.job.data.get('check_resource'):
        if elapsed_time > RESOURCE_THRESHOLD_SECONDS:
            msg = (
                f"⚠️ **CẢNH BÁO TỐN TÀI NGUYÊN!**\n"
                f"Quá trình quét clients Smart Server đã mất `{elapsed_time:.2f}` giây (> {RESOURCE_THRESHOLD_SECONDS}s)."
            )
            await context.bot.send_message(chat_id, msg, parse_mode='Markdown')
            
    # --- LOGIC THÔNG BÁO CLIENT MỚI ---
    if not latest_id:
        return

    last_seen_id = context.application.bot_data.get(LAST_SEEN_CLIENT_ID_KEY)
    
    if last_seen_id is None:
        context.application.bot_data[LAST_SEEN_CLIENT_ID_KEY] = latest_id
        print(f"Smart Server Monitor initialized. Last seen client ID: {latest_id}")
        return
        
    if latest_id > last_seen_id:
        msg = (
            "🔔🔔 **NGƯỜI DÙNG MỚI ĐĂNG KÝ (SMART SERVER)** 🔔🔔\n"
            f"👤 **ID Client mới:** `{latest_id}`\n"
            f"📧 **Email:** `{latest_email}`\n"
            f"🔑 **Đại lý:** `{AGENCY_NAME}`\n"
            f"🔗 **Link Admin:** https://sadmin.smartserver.vn/users"
        )
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
        context.application.bot_data[LAST_SEEN_CLIENT_ID_KEY] = latest_id
        print(f"Người dùng Smart Server mới được thông báo: ID {latest_id}")

async def test_monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lệnh /test_monitor: Chạy kiểm tra thủ công và báo cáo kết quả/thời gian của Smart Server."""
    #if update.effective_chat.id != TARGET_CHAT_ID:
        # Lỗi Permission
        #await update.message.reply_text("❌ Lỗi: Bạn không có quyền sử dụng lệnh này.")
        #return

    await update.message.reply_text("Đang chạy kiểm tra thủ công Smart Server và đo thời gian...")
    
    start_time = time_module.time()
    token = get_ss_token(SS_ADMIN_ACCOUNT)
    if not token:
        await update.message.reply_text("❌ Lỗi: Không lấy được Admin Token Smart Server.")
        return

    latest_id, latest_email = get_latest_client_id(token)
    end_time = time_module.time()
    elapsed_time = end_time - start_time
    
    if latest_id:
        msg = (
            f"✅ **KIỂM TRA SMART SERVER HOÀN TẤT**\n"
            f"Thời gian quét: `{elapsed_time:.2f}` giây.\n"
            f"ID Client mới nhất (Đại lý {AGENCY_NAME}): `{latest_id}`\n"
            f"Email: `{latest_email}`"
        )
    else:
        msg = (
            f"⚠️ **KIỂM TRA SMART SERVER HOÀN TẤT**\n"
            f"Thời gian quét: `{elapsed_time:.2f}` giây.\n"
            f"❌ Không tìm thấy client mới nhất (Lỗi API hoặc không có người dùng mới)."
        )
    
    await update.message.reply_text(msg, parse_mode='Markdown')


################################################################################
# PHẦN C: HÀM HANDLERS & UTILITY CŨ (TỪ tool.py)
################################################################################

# Hàm khởi đầu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # Logic cũ của tool.py
    await update.message.reply_markdown_v2(
        fr'Chào {user.mention_markdown_v2()} đến với KVOCloud\.com\. Hãy gửi danh sách proxy theo dạng IP:PORT:USER:PASS, mỗi proxy trên một dòng để kiểm tra\.',
        reply_markup=ForceReply(selective=True),
    )
    # Bổ sung thông tin giám sát client (nếu là chat admin)
    if update.effective_chat.id == TARGET_CHAT_ID:
        await update.message.reply_html(
            f"Đang giám sát ID Client Smart Server cuối cùng: `{context.application.bot_data.get(LAST_SEEN_CLIENT_ID_KEY, 'Đang khởi tạo...')}`"
        )


# Hàm lấy Location (Sử dụng IPRegistry)
def get_proxy_location(ip: str) -> str:
    flags = {
    "AF": "🇦🇫", "AL": "🇦🇱", "DZ": "🇩🇿", "AS": "🇦🇸", "AD": "🇦🇩", "AO": "🇦🇴",
    "AG": "🇦🇬", "AR": "🇦🇷", "AM": "🇦🇲", "AU": "🇦🇺", "AT": "🇦🇹", "AZ": "🇦🇿",
    "BS": "🇧🇸", "BH": "🇧🇭", "BD": "🇧🇩", "BB": "🇧🇧", "BY": "🇧🇾", "BE": "🇧🇪",
    "BZ": "🇧🇿", "BJ": "🇧🇯", "BM": "🇧🇲", "BT": "🇧🇹", "BO": "🇧🇴", "BA": "🇧🇦",
    "BW": "🇧🇼", "BR": "🇧🇷", "BN": "🇧🇳", "BG": "🇧🇬", "BF": "🇧🇫", "BI": "🇧🇮",
    "KH": "🇰🇭", "CM": "🇨🇲", "CA": "🇨🇦", "CV": "🇨🇻", "CF": "🇨🇫", "TD": "🇹🇩",
    "CL": "🇨🇱", "CN": "🇨🇳", "CO": "🇨🇴", "KM": "🇰🇲", "CD": "🇨🇩", "CG": "🇨🇬",
    "CR": "🇨🇷", "CI": "🇨🇮", "HR": "🇭🇷", "CU": "🇨🇺", "CY": "🇨🇾", "CZ": "🇨🇿",
    "DK": "🇩🇰", "DJ": "🇩🇯", "DM": "🇩🇲", "DO": "🇩🇴", "EC": "🇪🇨", "EG": "🇪🇬",
    "SV": "🇸🇻", "GQ": "🇬🇶", "ER": "🇪🇷", "EE": "🇪🇪", "SZ": "🇸🇿", "ET": "🇪🇹",
    "FJ": "🇫🇯", "FI": "🇫🇮", "FR": "🇫🇷", "GA": "🇬🇦", "GM": "🇬🇲", "GE": "🇬🇪",
    "DE": "🇩🇪", "GH": "🇬🇭", "GR": "🇬🇷", "GD": "🇬🇩", "GT": "🇬🇹", "GN": "🇬🇳",
    "GW": "🇬🇼", "GY": "🇬🇾", "HT": "🇭🇹", "HN": "🇭🇳", "HU": "🇭🇺", "IS": "🇮🇸",
    "IN": "🇮🇳", "ID": "🇮🇩", "IR": "🇮🇷", "IQ": "🇮🇶", "IE": "🇮🇪", "IL": "🇮🇱",
    "IT": "🇮🇹", "JM": "🇯🇲", "JP": "🇯🇵", "JO": "🇯🇴", "KZ": "🇰🇿", "KE": "🇰🇪",
    "KI": "🇰🇮", "KP": "🇰🇵", "KR": "🇰🇷", "KW": "🇰🇼", "KG": "🇰🇬", "LA": "🇱🇦",
    "LV": "🇱🇻", "LB": "🇱🇧", "LS": "🇱🇸", "LR": "🇱🇷", "LY": "🇱🇾", "LI": "🇱🇮",
    "LT": "🇱🇹", "LU": "🇱🇺", "MG": "🇲🇬", "MW": "🇲🇼", "MY": "🇲🇾", "MV": "🇲🇻",
    "ML": "🇲🇱", "MT": "🇲🇹", "MH": "🇲🇭", "MR": "🇲🇷", "MU": "🇲🇺", "MX": "🇲🇽",
    "FM": "🇫🇲", "MD": "🇲🇩", "MC": "🇲🇨", "MN": "🇲🇳", "ME": "🇲🇪", "MA": "🇲🇦",
    "MZ": "🇲🇿", "MM": "🇲🇲", "NA": "🇳🇦", "NR": "🇳🇷", "NP": "🇳🇵", "NL": "🇳🇱",
    "NZ": "🇳🇿", "NI": "🇳🇮", "NE": "🇳🇪", "NG": "🇳🇬", "NO": "🇳🇴", "OM": "🇴🇲",
    "PK": "🇵🇰", "PW": "🇵🇼", "PA": "🇵🇦", "PG": "🇵🇬", "PY": "🇵🇾", "PE": "🇵🇪",
    "PH": "🇵🇭", "PL": "🇵🇱", "PT": "🇵🇹", "QA": "🇶🇦", "RO": "🇷🇴", "RU": "🇷🇺",
    "RW": "🇷🇼", "KN": "🇰🇳", "LC": "🇱🇨", "VC": "🇻🇨", "WS": "🇼🇸", "SM": "🇸🇲",
    "ST": "🇸🇹", "SA": "🇸🇦", "SN": "🇸🇳", "RS": "🇷🇸", "SC": "🇸🇨", "SL": "🇸🇱",
    "SG": "🇸🇬", "SK": "🇸🇰", "SI": "🇸🇮", "SB": "🇸🇧", "SO": "🇸🇴", "ZA": "🇿🇦",
    "SS": "🇸🇸", "ES": "🇪🇸", "LK": "🇱🇰", "SD": "🇸🇩", "SR": "🇸🇷", "SE": "🇸🇪",
    "CH": "🇨🇭", "SY": "🇸🇾", "TW": "🇹🇼", "TJ": "🇹🇯", "TZ": "🇹🇿", "TH": "🇹🇭",
    "TL": "🇹🇱", "TG": "🇹🇬", "TO": "🇹🇴", "TT": "🇹🇹", "TN": "🇹🇳", "TR": "🇹🇷",
    "TM": "🇹🇲", "TV": "🇹🇻", "UG": "🇺🇬", "UA": "🇺🇦", "AE": "🇦🇪", "GB": "🇬🇧",
    "US": "🇺🇸", "UY": "🇺🇾", "UZ": "🇺🇿", "VU": "🇻🇺", "VA": "🇻🇦", "VE": "🇻🇪",
    "VN": "🇻🇳", "YE": "🇾🇪", "ZM": "🇿🇲", "ZW": "🇿🇼"
}
    try:
        response = requests.get(f'https://api.ipregistry.co/{ip}?key=ira_w1eGyZ3wi2XljsEa4jyt5stR6Pe8aa2knCA6', timeout=5)
        data = response.json()
        if 'error' in data:
            return 'Unknown location'
        loca = f"{data.get('location', {}).get('country', {}).get('code', 'Unknown country')}"
        flag = flags.get(loca.upper(), "N/A")
        location = loca+" - "+flag
        return location
    except Exception as e:
        return 'Unknown location'

# Hàm kiểm tra RDP/SSH
def check_rdp(vps, timeout=3):
    try:
        ip = vps.split(":")[0]
        port = int(vps.split(":")[1])
        location = get_proxy_location(ip=ip)
        try:
            s = socket.create_connection((ip, port), timeout)
            s.close()
            return f"✅ - {location} - {ip}:{port}"
        except (socket.timeout,socket.error):
            if port ==22:
                return f"🔴 - {ip}:{port}"
            else:
                try:
                    s = socket.create_connection((ip, 3389), timeout)
                    s.close()
                    return f"✅ - {location} - {ip}:{3389} - PORT"
                except (socket.timeout,socket.error):
                    pass
                try:
                    s = socket.create_connection((ip, 22), timeout)
                    s.close()
                    return f"✅ - {location} - {ip}:{22} - PORT"
                except (socket.timeout,socket.error):
                    pass
        return f"🔴 - {ip}:{port}"
    except Exception as e:
        return f"🔴 - {ip}:{port}"

# Hàm kiểm tra từng proxy (Không kèm location)
def check_single_proxy(proxy: str) -> str:
    parts = proxy.split(':')
    ip, port = parts[0], parts[1]

    # Kiểm tra RDP trước
    rdp_result = check_rdp(ip + ":" + port)

    if '✅' in rdp_result:
        if len(parts) == 2:
            return rdp_result
        elif len(parts) == 4:
            user, password = parts[2], parts[3]
            auth = f"{user}:{password}@"

            http_proxies = {
                'http': f'http://{auth}{ip}:{port}',
                'https': f'https://{auth}{ip}:{port}',
            }
            socks_proxies = {
                'http': f'socks5h://{auth}{ip}:{port}',
                'https': f'socks5h://{auth}{ip}:{port}',
            }

            try:
                response = requests.get('http://ifconfig.me/ip', proxies=http_proxies, timeout=3)
                if response.ok:
                    return f'✅ - {proxy}'
            except Exception:
                pass

            try:
                response = requests.get('http://ifconfig.me/ip', proxies=socks_proxies, timeout=3)
                if response.ok:
                    return f'✅ - SOCKS5 - {proxy}'
            except Exception:
                pass

            return f'🔴🔑 - {proxy}'
    else:
        return f'🔴 - {proxy}'

# Hàm kiểm tra từng proxy (Kèm location)
def check_single_proxy_lo(proxy: str) -> str:
    try:
        parts = proxy.split(':')
        ip, port = parts[0], parts[1]

        auth = ""
        if len(parts) == 4:
            user, password = parts[2], parts[3]
            auth = f"{user}:{password}@"

        http_proxies = {
            'http': f'http://{auth}{ip}:{port}',
            'https': f'https://{auth}{ip}:{port}',
        }
        socks_proxies = {
            'http': f'socks5h://{auth}{ip}:{port}',
            'https': f'socks5h://{auth}{ip}:{port}',
        }
        location = get_proxy_location(ip)
        try:
            response = requests.get('http://ifconfig.me/ip', proxies=http_proxies, timeout=5)
            if response.ok:
                return f'✅ - {location} - {proxy}'
        except Exception as e:
            pass
        try:
            response = requests.get('http://ifconfig.me/ip', proxies=socks_proxies, timeout=5)
            if response.ok:
                return f'✅ - SOCKS5 - {location} - {proxy}'
        except Exception as e:
            pass

        return f'🔴 - {proxy}'
    except:
        return f'🔴 - {proxy}'


# Hàm lấy Location chi tiết (Đang dùng IPRegistry)
def get_proxy_location_de(ip: str) -> str:
    # Logic tương tự get_proxy_location, nhưng giả định sẽ fetch detail hơn nếu API key/link khác
    return get_proxy_location(ip)

# Hàm kiểm tra từng proxy (Kèm location chi tiết)
def check_single_proxy_lo_de(proxy: str) -> str:
    try:
        parts = proxy.split(':')
        ip, port = parts[0], parts[1]

        auth = ""
        if len(parts) == 4:
            user, password = parts[2], parts[3]
            auth = f"{user}:{password}@"

        http_proxies = {
            'http': f'http://{auth}{ip}:{port}',
            'https': f'https://{auth}{ip}:{port}',
        }
        socks_proxies = {
            'http': f'socks5h://{auth}{ip}:{port}',
            'https': f'socks5h://{auth}{ip}:{port}',
        }
        location = get_proxy_location_de(ip)
        try:
            response = requests.get('http://ifconfig.me/ip', proxies=http_proxies, timeout=5)
            if response.ok:
                return f'✅ - {location} - {proxy}'
        except Exception as e:
            pass
        try:
            response = requests.get('http://ifconfig.me/ip', proxies=socks_proxies, timeout=5)
            if response.ok:
                return f'✅ - SOCKS5 - {location} - {proxy}'
        except Exception as e:
            pass

        return f'🔴 - {proxy}'
    except:
        return f'🔴 - {proxy}'


# Hàm tạo key
def generate_key(hwid):
    hashed_hwid = hashlib.sha256(hwid.encode()).hexdigest().upper()
    return f"{hashed_hwid[:6]}-{hashed_hwid[6:12]}"

# Lấy dữ liệu hiện tại từ file JSON trên GitHub
def get_current_data():
    response = requests.get(API_URL, headers={'Authorization': f'token {GITHUB_TOKEN}'})
    if response.status_code == 200:
        content = response.json()
        data = json.loads(base64.b64decode(content['content']).decode())
        sha = content['sha']
        return data, sha
    else:
        # Nếu file chưa tồn tại, trả về dữ liệu rỗng
        return {"valid_keys": []}, None

# Cập nhật file key.json bằng cách bổ sung dữ liệu mới
def update_github_file(hwid):
    key = generate_key(hwid)
    data, sha = get_current_data()
    # Kiểm tra xem HWID đã tồn tại chưa để tránh trùng lặp
    if any(entry["hwid"] == hwid for entry in data["valid_keys"]):
        result = "HWID đã tồn tại trong danh sách! - Key:"+key
    else:
        # Thêm key mới vào danh sách
        data["valid_keys"].append({"key": key, "hwid": hwid})
        # Chuẩn bị dữ liệu để commit lên GitHub
        updated_content = json.dumps(data, indent=4)
        encoded_content = base64.b64encode(updated_content.encode()).decode()
        payload = {
            "message": f"Add new key for HWID {hwid}",
            "content": encoded_content,
            "sha": sha # Bắt buộc để cập nhật file
        }
        response = requests.put(API_URL, headers={'Authorization': f'token {GITHUB_TOKEN}'}, json=payload)
        if response.status_code in [200, 201]:
            result = "Key kích hoạt: "+key
        else:
            print("Lỗi khi cập nhật file:", response.json())
            result = "Lỗi khi cập nhật file key.json trên GitHub."
    return result

# Hàm kiểm tra nhiều proxy (Không kèm location)
async def check_proxies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    processing_message = await update.message.reply_text(" 🔄 Processing...")
    proxies = update.message.text.strip().split('\n')
    extracted = []
    # Regex tìm IP:PORT:USER:PASS ở đầu chuỗi
    pattern_full = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+:[^:\s/]+:[^:\s/]+)")
    # Regex tìm IP:PORT ở đầu chuỗi (nếu không có user:pass)
    pattern_basic = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+)")
    for proxy in proxies:
        match = pattern_full.search(proxy)
        if match:
            extracted.append(match.group(1))
        else:
            match = pattern_basic.search(proxy)
            if match:
                extracted.append(match.group(1))
    result_proxy = "\n".join(extracted)                        
    result_proxy = list(dict.fromkeys(result_proxy.split('\n'))) 
    final_proxy = [line.strip() for line in result_proxy if line.strip()] 
    proxy_count = len(final_proxy)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_single_proxy, final_proxy))
    active_proxies = [result for result in results if result is not None and '✅' in result]
    inactive_proxies = [result for result in results if result is not None and '🔴' in result]
    sorted_results = active_proxies + inactive_proxies
    result_message = "\n".join(sorted_results)
    summary_message = f"\n📔 - Tổng số : {proxy_count}"

    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
    
    await update.message.reply_text(result_message + summary_message)

    context.user_data['inactive_proxies'] = [proxy.split(' - ')[1] for proxy in inactive_proxies if '🔴' in proxy]

    if inactive_proxies:
        keyboard = [
            [InlineKeyboardButton("🔁RE-CHECK !", callback_data='recheck_proxies')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Kiểm tra lại VPS/Proxy không hoạt động !", reply_markup=reply_markup)

# Xử lý lệnh /vps (Start ConversationHandler 1)
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Trải nghiệm Proxy chính hãng tại kvocloud.com. Hãy gửi danh sách proxy theo dạng IP:PORT:USER:PASS, mỗi proxy trên một dòng để kiểm tra.")
    return WAITING_FOR_PROXY_LIST

# Xử lý danh sách VPS (End ConversationHandler 1 - /vps)
async def check_vps2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    processing_message = await update.message.reply_text(" 🔄 Processing...")
    vps_1 = update.message.text.strip().split('\n')
    extracted = []
    for vps in vps_1:
        if "📔 - Tổng số" in vps:
            pass
        elif "-" in vps:
            vps_tach = vps.split('-')
            vps_final = vps_tach[1].strip()
            extracted.append(vps_final)
        else:
            pattern_ip_port = r"\b\d{1,3}(?:\.\d{1,3}){3}:\d+\b"
            pattern_ip_only = r"\b\d{1,3}(?:\.\d{1,3}){3}\b"
            match = re.search(pattern_ip_port, vps)
            if match:
                extracted.append(match.group())
            else:
                match_ip = re.search(pattern_ip_only, vps)
                if match_ip:
                    extracted.append(f"{match_ip.group()}:3389")
    result_vps = "\n".join(extracted)
    final_vps = result_vps.strip().split('\n')
    proxy_count = len(final_vps)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_rdp, final_vps))
    active_vps = [result for result in results if '✅' in result]
    inactive_vps = [result for result in results if '🔴' in result]
    sorted_results_vps = active_vps + inactive_vps
    result_message_vps = "\n".join(sorted_results_vps)
    summary_message_vps = f"\n📔 - Tổng số VPS : {proxy_count}"

    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
    
    await update.message.reply_text(result_message_vps + summary_message_vps)

    context.user_data['inactive_vps'] = [vps.split(' - ')[1] for vps in inactive_vps if '🔴' in vps]
    if inactive_vps:
        keyboard = [
            [InlineKeyboardButton("🔁RE-CHECK !", callback_data='recheck_vps')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Kiểm tra lại VPS không hoạt động !", reply_markup=reply_markup)

    return ConversationHandler.END


# Xử lý danh sách Proxy (End ConversationHandler 2 - /proxy_location)
async def check_proxies_lo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    processing_message = await update.message.reply_text(" 🔄 Processing...")
    proxies = update.message.text.strip().split('\n')
    extracted = []
    pattern_full = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+:[^:\s/]+:[^:\s/]+)")
    pattern_basic = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+)")
    for proxy in proxies:
        match = pattern_full.search(proxy)
        if match:
            extracted.append(match.group(1))
        else:
            match = pattern_basic.search(proxy)
            if match:
                extracted.append(match.group(1))
    result_proxy = "\n".join(extracted)
    final_proxy = result_proxy.strip().split('\n')
    proxy_count = len(final_proxy)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_single_proxy_lo, final_proxy))
    active_proxies = [result for result in results if '✅' in result]
    inactive_proxies = [result for result in results if '🔴' in result]
    sorted_results = active_proxies + inactive_proxies
    result_message = "\n".join(sorted_results)
    summary_message = f"\n📔 - Tổng số proxy : {proxy_count}"

    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
    
    await update.message.reply_text(result_message + summary_message)
    
    return ConversationHandler.END


# Xử lý danh sách Proxy (End ConversationHandler 3 - /check_location_detail)
async def check_proxies_lo_de(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    processing_message = await update.message.reply_text(" 🔄 Processing...")
    proxies = update.message.text.strip().split('\n')
    extracted = []
    pattern_full = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+:[^:\s/]+:[^:\s/]+)")
    pattern_basic = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+)")
    for proxy in proxies:
        match = pattern_full.search(proxy)
        if match:
            extracted.append(match.group(1))
        else:
            match = pattern_basic.search(proxy)
            if match:
                extracted.append(match.group(1))
    result_proxy = "\n".join(extracted)
    final_proxy = result_proxy.strip().split('\n')
    proxy_count = len(final_proxy)
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_single_proxy_lo_de, final_proxy))
    active_proxies = [result for result in results if '✅' in result]
    inactive_proxies = [result for result in results if '🔴' in result]
    sorted_results = active_proxies + inactive_proxies
    result_message = "\n".join(sorted_results)
    summary_message = f"\n📔 - Tổng số proxy : {proxy_count}"

    await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=processing_message.message_id)
    
    await update.message.reply_text(result_message + summary_message)
    
    return ConversationHandler.END


# Xử lý danh sách Proxy (End ConversationHandler 4 - /ip)
async def tach_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    proxies = update.message.text.strip().split('\n')
    extracted_1 = []
    pattern_full = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+:[^:\s/]+:[^:\s/]+)")
    pattern_basic = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3}:\d+)")
    for proxy in proxies:
        match = pattern_full.search(proxy)
        if match:
            extracted_1.append(match.group(1))
        else:
            match = pattern_basic.search(proxy)
            if match:
                extracted_1.append(match.group(1))
    result_message = "\n".join(extracted_1)
    await update.message.reply_text(f"{result_message}")
    return ConversationHandler.END

# Xử lý tạo key (End ConversationHandler 5 - /key)
async def create_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    hwid = update.message.text.strip()
    result = update_github_file(hwid)
    await update.message.reply_text(result)
    return ConversationHandler.END


# Xử lý lấy data (End ConversationHandler 6 - /get_data)
async def get_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        data, _ = get_current_data()
        msg = "Danh sách HWID và Key đã lưu trên GitHub:\n\n"
        if data["valid_keys"]:
            for entry in data["valid_keys"]:
                msg += f"🔑 Key: {entry['key']}\n"
                msg += f"🖥️ HWID: {entry['hwid']}\n---\n"
        else:
            msg = "Không có key nào được lưu."
        
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Lỗi khi lấy dữ liệu: {e}")
    return ConversationHandler.END


# Hàm xử lý logic kiểm tra hết hạn (Core logic - MỚI)
async def _core_check_expiration(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Logic cốt lõi để kiểm tra VPS/Proxy sắp hết hạn và gửi báo cáo."""
    
    # LẤY TOKEN CHO HỆ THỐNG KVOCloud (manage.kvocloud.com)
    token_kvocloud = get_kvocloud_token(vu)
    
    if not token_kvocloud:
        await context.bot.send_message(chat_id, "⚠️ LỖI: Không lấy được KVO Cloud Token trong quá trình quét hết hạn.")
        return
    
    try:
        # 1. Lấy danh sách VPS còn 3 ngày hết hạn (Sử dụng API mới)
        grouped_vps, het_han_vps = get_servers(token_kvocloud, is_proxy=False) 
        
        # 2. Lấy danh sách Proxy còn 3 ngày hết hạn (Sử dụng API mới)
        grouped_pro, het_han_pro = get_servers(token_kvocloud, is_proxy=True)

        if not grouped_vps and not grouped_pro: 
            # Không có data hết hạn trong 3 ngày tới
            msg = "✅ Hoàn tất kiểm tra: Không có VPS hoặc Proxy nào sắp hết hạn trong vòng 3 ngày tới."
            await context.bot.send_message(chat_id, msg)
            return

        msg = f"Hôm nay: {datetime.now(VIETNAM).strftime('%d/%m/%Y')}\n"
        
        if grouped_vps:
            msg += "\n📑Danh sách VPS còn 3 ngày hết hạn:\n"
            msg += f"Ngày hết hạn: {het_han_vps}\n"
            for note, ips in grouped_vps.items():
                qtyvps = len(ips)
                msg += f"\n👨‍💼KH: {note} - {qtyvps} VPS - Hết hạn: {het_han_vps}\n"
                for ip in ips:
                    msg += f" - {ip}\n"
        
        if grouped_pro:
            msg += "\n📑Danh sách Proxy còn 3 ngày hết hạn:\n"
            msg += f"Ngày hết hạn: {het_han_pro}\n"
            for note, ips in grouped_pro.items():
                qtyprx = len(ips)
                msg += f"\n👨‍💼KH: {note} - {qtyprx} Proxy - Hết hạn: {het_han_pro}\n"
                for ip in ips:
                    msg += f" - {ip}\n"
                    
        await context.bot.send_message(chat_id, msg)
        
    except Exception as e:
        await context.bot.send_message(chat_id, f"⚠️ Lỗi khi chạy kiểm tra hết hạn (KVOCloud): {e}")


# Xử lý lệnh /get (Manual check hết hạn - ĐÃ SỬA LỖI TREO)
async def get_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # 1. Gửi thông báo đang xử lý
    await update.message.reply_text("Đã nhận lệnh /get. Đang kiểm tra VPS/Proxy sắp hết hạn...")
    
    # 2. Gọi logic cốt lõi, gửi kết quả về chat của người dùng
    await _core_check_expiration(context, update.effective_chat.id)


# Hàm chạy định kỳ gửi báo cáo (8:30 và 20:30)
async def scheduled_get(context: ContextTypes.DEFAULT_TYPE):
    # Job định kỳ sẽ gửi báo cáo về TARGET_CHAT_ID (Admin)
    await _core_check_expiration(context, TARGET_CHAT_ID)


# Xử lý Callback (Kiểm tra lại Proxy/VPS)
async def recheck_proxies_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    inactive_proxies = context.user_data.get('inactive_proxies')
    if not inactive_proxies:
        await query.edit_message_text("Không có proxy nào để kiểm tra lại.")
        return

    processing_message = await query.message.reply_text(" 🔄 Processing...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_single_proxy, inactive_proxies))
    
    active_proxies = [result for result in results if '✅' in result]
    still_inactive_proxies = [result for result in results if '🔴' in result]
    
    sorted_results = active_proxies + still_inactive_proxies
    result_message = "\n".join(sorted_results)
    summary_message = f"\n📔 - Tổng số proxy: {len(inactive_proxies)}"

    await context.bot.delete_message(chat_id=query.effective_chat.id, message_id=processing_message.message_id)
    await query.message.reply_text(result_message + summary_message)
    
    context.user_data['inactive_proxies'] = [proxy.split(' - ')[1] for proxy in still_inactive_proxies]

    if still_inactive_proxies:
        keyboard = [
            [InlineKeyboardButton("🔁RE-CHECK !", callback_data='recheck_proxies')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Kiểm tra lại VPS/Proxy không hoạt động !", reply_markup=reply_markup)

async def recheck_vps_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    vps_1 = context.user_data.get('inactive_vps')
    if not vps_1:
        await query.edit_message_text("Không có VPS nào để kiểm tra lại.")
        return

    processing_message = await query.message.reply_text(" 🔄 Processing...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_rdp, vps_1))
    
    active_vps = [result for result in results if '✅' in result]
    still_inactive_vps = [result for result in results if '🔴' in result]
    
    sorted_results = active_vps + still_inactive_vps
    result_message = "\n".join(sorted_results)
    summary_message = f"\n📔 - Tổng số VPS: {len(vps_1)}"

    await context.bot.delete_message(chat_id=query.effective_chat.id, message_id=processing_message.message_id)
    await query.message.reply_text(result_message + summary_message)
    
    context.user_data['inactive_vps'] = [vps.split(' - ')[1] for vps in still_inactive_vps]

    if still_inactive_vps:
        keyboard = [
            [InlineKeyboardButton("🔁RE-CHECK !", callback_data='recheck_vps')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Kiểm tra lại VPS không hoạt động !", reply_markup=reply_markup)


# Hàm hủy bỏ ConversationHandler
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Đã hủy bỏ.', reply_markup=ForceReply(selective=True))
    return ConversationHandler.END


################################################################################
# PHẦN D: MAIN FUNCTION (GỘP TẤT CẢ HANDLERS VÀ JOBS)
################################################################################

def main() -> None:
    
    # Kiểm tra cấu hình mặc định (từ adminkvo.py)
    if BOT_TOKEN == "Bot_token" or TARGET_CHAT_ID == 1234567 or SS_ADMIN_ACCOUNT == "mail/pass":
        print("LỖI CẤU HÌNH: Vui lòng thay BOT_TOKEN, TARGET_CHAT_ID và SS_ADMIN_ACCOUNT bằng giá trị thực.")
        # Nếu bot vẫn chạy với cấu hình mặc định này, vui lòng đảm bảo bạn đã thay TOKEN và ACCOUNT trước khi deploy.
        # return

    application = Application.builder().token(BOT_TOKEN).build()

    # ====================================================================
    # 1. CONVERSATION HANDLERS (TỪ tool.py)
    # ====================================================================
    
    # ConvHandler 1: /vps (Check RDP/SSH)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('vps', check_command)],
        states={
            WAITING_FOR_PROXY_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_vps2)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # ConvHandler 2: /proxy_location (Check Proxy kèm Location)
    conv_handler_1 = ConversationHandler(
        entry_points=[CommandHandler('proxy_location', check_command)],
        states={
            WAITING_FOR_PROXY_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_proxies_lo)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # ConvHandler 3: /check_location_detail (Check Proxy kèm Location Detail)
    conv_handler_2 = ConversationHandler(
        entry_points=[CommandHandler('check_location_detail', check_command)],
        states={
            WAITING_FOR_PROXY_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_proxies_lo_de)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # ConvHandler 4: /ip (Tách IP:PORT)
    conv_handler_3 = ConversationHandler(
        entry_points=[CommandHandler('ip', check_command)],
        states={
            WAITING_FOR_PROXY_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, tach_proxy)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # ConvHandler 5: /key (Tạo Key)
    conv_handler_4 = ConversationHandler(
        entry_points=[CommandHandler('key', check_command)],
        states={
            WAITING_FOR_PROXY_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_key)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # ConvHandler 6: /get_data (Lấy Key đã tạo)
    conv_handler_5 = ConversationHandler(
        entry_points=[CommandHandler('get_data', check_command)],
        states={
            WAITING_FOR_PROXY_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_data)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # ====================================================================
    # 2. STANDARD HANDLERS (TỪ tool.py VÀ adminkvo.py)
    # ====================================================================
    
    application.add_handler(CommandHandler("start", start)) 
    application.add_handler(CommandHandler("get", get_handler)) # ĐÃ FIX: Gọi logic kiểm tra hết hạn
    application.add_handler(CommandHandler("test_monitor", test_monitor_command)) # Lệnh Giám sát Smart Server
    
    # Thêm tất cả ConversationHandler
    application.add_handler(conv_handler)
    application.add_handler(conv_handler_1)
    application.add_handler(conv_handler_2)
    application.add_handler(conv_handler_3)
    application.add_handler(conv_handler_4)
    application.add_handler(conv_handler_5)

    # Xử lý tin nhắn văn bản (Check Proxy không kèm location)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_proxies))
    
    # Xử lý Callback Query (Re-check)
    application.add_handler(CallbackQueryHandler(recheck_proxies_callback, pattern='^recheck_proxies$'))
    application.add_handler(CallbackQueryHandler(recheck_vps_callback, pattern='^recheck_vps$'))
    
    
    # ====================================================================
    # 3. JOB QUEUE (GỘP CẢ tool.py VÀ adminkvo.py)
    # ====================================================================

    job_queue = application.job_queue

    # Job CŨ: Gửi cho vu lúc 8h30 sáng và 20h30 tối (tool.py - KVOCloud)
    print("Thiết lập Job báo cáo hết hạn KVOCloud (9:30 & 20:30)...")
    job_queue.run_daily(
        scheduled_get, 
        time=time(hour=9, minute=30, tzinfo=VIETNAM),
        days=(0, 1, 2, 3, 4, 5, 6),
    )
    job_queue.run_daily(
        scheduled_get, 
        time=time(hour=20, minute=30, tzinfo=VIETNAM),
        days=(0, 1, 2, 3, 4, 5, 6),
    )

    # Job MỚI: Giám sát Client mới (adminkvo.py - Smart Server)
    print("Thiết lập Job Giám sát Client Smart Server (11:00)...")
    job_queue.run_daily(
        monitor_new_clients, 
        time=time(hour=11, minute=0, tzinfo=VIETNAM), 
        days=(0, 1, 2, 3, 4, 5, 6),
        data={'check_resource': True} 
    )

    
    print("Thiết lập Job Giám sát Client Smart Server (18:00)...")
    job_queue.run_daily(
        monitor_new_clients, 
        time=time(hour=18, minute=0, tzinfo=VIETNAM), 
        days=(0, 1, 2, 3, 4, 5, 6),
        data={'check_resource': True} 
    )

    print("Bot đang chạy polling...")
    application.run_polling(poll_interval=1.0)


if __name__ == "__main__":
    main()