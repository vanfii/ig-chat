import os
from dotenv import load_dotenv
from supabase import create_client, Client
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import uuid
# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global cache
clients_cache = {}
log_cache = {}
# Scheduler setup
scheduler = BackgroundScheduler()

def load_all_clients():
    global clients_cache  # supaya kita update variabel global

    response = supabase.table("client").select("*").execute()
    if response.data is None:
        clients_cache = {}  # pastikan tetap kosong jika gagal
        return {}

    temp = {}
    for item in response.data:
        ig_id = str(item.get("ig_id"))
        if ig_id:
            temp[ig_id] = item

    clients_cache = temp  # simpan hasil ke cache global
    print(f"✅ Loaded {len(clients_cache)} clients into cache.")
    return clients_cache

def get_client(ig_id):
    return clients_cache.get(str(ig_id))

def delete_client_by_ig_id(ig_id):
    return supabase.table("client").delete().eq("ig_id", ig_id).execute()

def get_token_by_ig_id(ig_id):
    client = get_client(ig_id)
    if client:
        return client.get("token")
    
    # Fallback ke Supabase
    try:
        response = supabase.table("client").select("token").eq("ig_id", ig_id).single().execute()
        if response.data:
            token = response.data.get("token")
            # Update ke cache juga
            clients_cache[str(ig_id)] = response.data
            print(f"📥 Token {ig_id} loaded from Supabase as fallback")
            return token
    except Exception as e:
        print(f"❌ Error fallback get_token_by_ig_id({ig_id}): {e}")
    return None

def get_menu_link_by_ig_id(ig_id):
    client = get_client(ig_id)
    menu_links = client.get("menu_link") if client else None

    if isinstance(menu_links, list):
        return menu_links
    elif isinstance(menu_links, str):
        return [menu_links]
    return []


def update_client_by_ig_id(ig_id, client_name, token, redirect_url):
    try:
        response = supabase.table("client").update({
            "client_name": client_name,
            "token": token,
            "redirect_url": redirect_url
        }).eq("ig_id", ig_id).execute()

        if hasattr(response, 'error') and response.error:
            raise Exception(response.error)
    except Exception as e:
        raise Exception(f"Gagal update user: {e}")

def insert_user(ig_id, client_name, token, redirect_url):
    created_at = datetime.utcnow().isoformat()
    return supabase.table("client").insert({
        "ig_id": ig_id,
        "client_name": client_name,
        "token": token,
        "redirect_url": redirect_url,
        "joined": created_at
    }).execute()

def get_all_users(limit=10):
    return supabase.table("client") \
                   .select("ig_id, token, redirect_url, client_name, joined") \
                   .limit(limit).execute()
def insert_user(data):
    return supabase.table("client").insert({
        "client_name": data.get("client_name"),
        "token": data.get("token"),
        "business_type": data.get("business_type"),
        "ig_id": data.get("ig_id"),
        "joined": data.get("joined"),
        "triger_stop": data.get("stop_keywords"),   # sudah list
        "pemicu": data.get("trigger_keywords"),     # sudah list
    }).execute()

def replace_menu_image(ig_id, index, new_image):
    # Step 1: Ambil data client
    response = supabase.table("client").select("menu_link").eq("ig_id", ig_id).execute()
    if not response.data:
        raise Exception("Client tidak ditemukan.")

    menu_links = response.data[0].get("menu_link", [])
    if not isinstance(menu_links, list):
        raise Exception("menu_link bukan array.")
    
    if index < 0 or index >= len(menu_links):
        raise Exception("Index gambar tidak valid.")

    # Step 2: Hapus gambar lama dari storage
    old_url = menu_links[index]
    # Contoh: https://xxx.supabase.co/storage/v1/object/public/menus/ig_id/filename.jpg
    path_to_file = old_url.split("/storage/v1/object/public/menus/")[-1]
    supabase.storage.from_("menus").remove([path_to_file])

    # Step 3: Upload gambar baru
    filename = f"{uuid.uuid4()}_{new_image.filename}"
    path = f"{ig_id}/{filename}"

    upload_response = supabase.storage.from_('menus').upload(
        path, new_image.read(), {"content-type": new_image.content_type}
    )

    if hasattr(upload_response, 'error') and upload_response.error:
        raise Exception(str(upload_response.error))

    new_url = f"{SUPABASE_URL}/storage/v1/object/public/menus/{path}"

    # Step 4: Ganti URL di posisi index
    menu_links[index] = new_url

    # Step 5: Simpan ke database
    update_response = supabase.table("client").update({
        "menu_link": menu_links
    }).eq("ig_id", ig_id).execute()

    if hasattr(update_response, 'error') and update_response.error:
        raise Exception(update_response.error)

    return new_url

def add_menu_image(ig_id, image):
    filename = f"{uuid.uuid4()}_{image.filename}"
    path = f"{ig_id}/{filename}"

    upload_response = supabase.storage.from_('menus').upload(
        path, image.read(), {"content-type": image.content_type}
    )

    if hasattr(upload_response, 'error') and upload_response.error:
        raise Exception(str(upload_response.error))

    public_url = f"{SUPABASE_URL}/storage/v1/object/public/menus/{path}"

    client_data = supabase.table('client').select('menu_link').eq('ig_id', ig_id).execute()
    if not client_data.data:
        raise Exception("Client tidak ditemukan")

    old_links = client_data.data[0].get('menu_link', []) or []
    new_links = old_links + [public_url]

    update_response = supabase.table('client').update({
        'menu_link': new_links
    }).eq('ig_id', ig_id).execute()

    if hasattr(update_response, 'error') and update_response.error:
        raise Exception(update_response.error)

    return public_url

def get_spreadsheet_id_by_ig_id(ig_id):
    result = supabase.table("client").select("spreadsheet_id").eq("ig_id", ig_id).execute()
    if result.data and result.data[0].get("spreadsheet_id"):
        return result.data[0]["spreadsheet_id"]
    return None

def log_bot_activity(ig_id, log_type, message):
    log_cache[ig_id] = log_cache.get(ig_id, [])
    log_cache[ig_id].append({"type": log_type, "content": message})
    # batasi jumlah log biar nggak meledak
    log_cache[ig_id] = log_cache[ig_id][-50:]
# Load pertama kali saat start
load_all_clients()


# Jalankan refresh tiap 5 menit
scheduler.add_job(load_all_clients, 'interval', minutes=5)
scheduler.start()

# Supaya dipakai oleh app.py
app_id = os.getenv("app_id")
app_secret = os.getenv("app_secret")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
meta_id = os.getenv("meta_id")
meta_secret = os.getenv("meta_secret")
redirect_url = os.getenv("redirect_url")
SECRET_KEY = os.getenv("secretkey")
