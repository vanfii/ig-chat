from .config import get_client
from .handlers import handle_makanan, handle_villa
from .instagram_API import send_reply
from .config import log_bot_activity
from datetime import datetime

now = datetime.now()

def handle_message(user_id, text, ig_id):
    lower_text = text.lower()

    # Log pesan masuk dari user
    log_bot_activity(ig_id, "reply", f"Pesan masuk dari {user_id}: {text}")

    client = get_client(ig_id)
    if not client:
        send_reply(user_id, "❌ Konfigurasi client tidak ditemukan.", ig_id)
        log_bot_activity(ig_id, "error", f"Client tidak ditemukan untuk IG ID: {ig_id}")
        return

    business_type = client.get("business_type", "default")

    if business_type == "kuliner":
        handle_makanan(user_id, text, ig_id, lower_text, now, client)
    elif business_type == "villa":
        handle_villa(user_id, text, ig_id, lower_text, now, client)
    else:
        msg = f"🔧 Jenis bisnis '{business_type}' belum didukung."
        send_reply(user_id, msg, ig_id)
        log_bot_activity(ig_id, "error", msg)