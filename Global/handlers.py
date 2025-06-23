
from .instagram_API import send_reply, get_username, send_image
from .spreadsheet import log_to_sheet
import re
import difflib

user_sessions = {}
SESSION_TIMEOUT = 180
WARNING_TIME = 60

def fuzzy_match(input_text, keywords, threshold=0.85):
    match = difflib.get_close_matches(input_text, keywords, n=1, cutoff=threshold)
    return match[0] if match else None

import re
from datetime import datetime, timedelta

# Global Config
SESSION_TIMEOUT = timedelta(minutes=5)
WARNING_TIME = timedelta(minutes=1)
GREETING_TIMEOUT = timedelta(hours=6)

# Cache Session & Greeting
user_sessions = {}      # user_id -> session data
greeted_users = {}      # user_id -> last greeted time

# Kata Kunci
sapaan_keywords = ["halo", "hai", "pagi", "siang", "malam", "assalamualaikum"]
info_keywords = ["info", "menu", "lihat", "list"]
now = datetime.now()

# Fungsi Utama
def parse_order_items(text):
    parts = re.split(r",|\s+dan\s+|/", text, flags=re.IGNORECASE)
    orders = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue

        match = re.match(r"^(\d+)\s+(.*)", part)
        if match:
            qty = int(match.group(1))
            item = match.group(2).strip().lower()
        else:
            qty = 1
            item = part.strip().lower()

        if item in orders:
            orders[item] += qty
        else:
            orders[item] = qty
    return orders

# Main handler
def handle_makanan(user_id, text, ig_id, lower_text, now, client):
    trigger_keywords = client.get("pemicu", ["pesan", "order", "beli"])
    stop_keywords = client.get("triger_stop", ["tidak", "nggak", "ga", "sudah", "cukup", "selesai"])
    username = get_username(user_id, ig_id)
    session = user_sessions.get(user_id)

    # === Jika sedang dalam sesi ===
    if session:
        last_active = session["last_active"]
        if isinstance(last_active, float):
            last_active = datetime.fromtimestamp(last_active)

        elapsed = now - last_active

        if elapsed > SESSION_TIMEOUT:
            send_reply(user_id, "⏰ Sesi Anda berakhir. Ketik 'pesan' untuk mulai ulang.", ig_id)
            del user_sessions[user_id]
            return
        elif SESSION_TIMEOUT - elapsed <= WARNING_TIME and not session.get("warned"):
            send_reply(user_id, "⚠️ Sesi akan berakhir dalam 1 menit. Balas pesan ini untuk lanjut.", ig_id)
            session["warned"] = True

        session["last_active"] = now

        # === Step: Sedang mengumpulkan pesanan ===
        if session["status"] == "collecting":
            if fuzzy_match(lower_text, stop_keywords):
                if not session["orders"]:
                    send_reply(user_id, "❗ Anda belum memasukkan pesanan apapun.", ig_id)
                    return

                session["status"] = "confirming"
                order_lines = [f"{item} x{qty}" for item, qty in session["orders"].items()]
                reply = (
                    "📋 Pesanan Anda:\n• " + "\n• ".join(order_lines) +
                    "\n\nApakah sudah benar?\n✅ Balas *ya* untuk konfirmasi\n✏️ Balas *edit [nama item]* untuk mengubah"
                )
                send_reply(user_id, reply, ig_id)
                return

            # Tambahkan pesanan
            parsed = parse_order_items(text)
            for item, qty in parsed.items():
                if item in session["orders"]:
                    session["orders"][item] += qty
                else:
                    session["orders"][item] = qty

            order_lines = [f"{item} x{qty}" for item, qty in session["orders"].items()]
            reply = "✅ Dicatat:\n• " + "\n• ".join(order_lines) + "\nAda tambahan lagi? Balas 'tidak' jika selesai."
            send_reply(user_id, reply, ig_id)
            return

        # === Step: Konfirmasi akhir ===
        elif session["status"] == "confirming":
            if lower_text.strip() == "ya":
                final_order = ", ".join([f"{item} x{qty}" for item, qty in session["orders"].items()])
                reply = (
                    f"✅ Pesanan dikonfirmasi kak @{username}!\n"
                    f"📦 Order: {final_order}\n\nTerima kasih, pesanan akan segera diproses 🙏"
                )
                send_reply(user_id, reply, ig_id)
                log_to_sheet(user_id, username, final_order, ig_id)
                del user_sessions[user_id]
                return

            elif lower_text.startswith("edit "):
                item_to_edit = lower_text.replace("edit", "", 1).strip()
                if item_to_edit in session["orders"]:
                    session["status"] = "editing"
                    session["editing_item"] = item_to_edit
                    send_reply(user_id, f"✏️ Berapa jumlah baru untuk *{item_to_edit}*?", ig_id)
                else:
                    send_reply(user_id, f"⚠️ Item *{item_to_edit}* tidak ditemukan di pesanan Anda.", ig_id)
                return

        # === Step: Sedang edit satu item ===
        elif session["status"] == "editing":
            item = session.get("editing_item")
            try:
                qty = int(text.strip())
                if qty <= 0:
                    session["orders"].pop(item, None)
                    send_reply(user_id, f"❌ *{item}* dihapus dari pesanan.", ig_id)
                else:
                    session["orders"][item] = qty
                    send_reply(user_id, f"✅ Jumlah *{item}* diperbarui jadi {qty}.", ig_id)
            except:
                send_reply(user_id, "⚠️ Mohon masukkan angka yang valid (contoh: 2)", ig_id)
                return

            session["status"] = "confirming"
            session.pop("editing_item", None)
            order_lines = [f"{item} x{qty}" for item, qty in session["orders"].items()]
            reply = (
                "📋 Update pesanan Anda:\n• " + "\n• ".join(order_lines) +
                "\n\nApakah sudah benar?\n✅ Balas *ya* untuk konfirmasi\n✏️ Balas *edit [nama item]* untuk mengubah"
            )
            send_reply(user_id, reply, ig_id)
            return

        return

    # === Jika belum dalam sesi ===
    if fuzzy_match(lower_text, trigger_keywords):
        user_sessions[user_id] = {
            "status": "collecting",
            "orders": {},
            "last_active": now,
            "warned": False
        }
        send_reply(user_id, client.get("promp_extra", "Silakan ketik pesanan kak 😊"), ig_id)
        send_image(user_id, ig_id)
        return

    if fuzzy_match(lower_text, info_keywords):
        send_reply(user_id, "📋 Ini menu promo hari ini kak:", ig_id)
        send_image(user_id, ig_id)
        return

    if any(word in lower_text for word in sapaan_keywords):
        last_greet = greeted_users.get(user_id)
        if not last_greet or now - last_greet > GREETING_TIMEOUT:
            greeting = client.get("greeting", f"👋 Halo kak @{username}, ada yang bisa kami bantu hari ini?")
            send_reply(user_id, greeting, ig_id)
            greeted_users[user_id] = now
        return

    # Jika bukan trigger/sapaan/info → tidak dibalas (manual handled)
    return

def handle_villa(user_id, text, ig_id, lower_text, now, client):
    username = get_username(user_id, ig_id)
    session = user_sessions.get(user_id)

    # ✅ 1. Cek jika user dalam sesi aktif
    if session:
        last_active = session.get("last_active")
        if isinstance(last_active, float):
            last_active = datetime.fromtimestamp(last_active)  # konversi jika data lama

        elapsed = now - last_active

        if elapsed > SESSION_TIMEOUT:
            send_reply(user_id, "⏰ Sesi Anda berakhir. Ketik 'booking' untuk mulai ulang.", ig_id)
            del user_sessions[user_id]
            return

        session["last_active"] = now  # update waktu aktif terakhir

        step = session.get("step")

        if step == "type":
            session["type"] = text
            session["step"] = "checkin"
            send_reply(user_id, "📅 Tanggal check-in?", ig_id)

        elif step == "checkin":
            session["checkin"] = text
            session["step"] = "checkout"
            send_reply(user_id, "📅 Tanggal check-out?", ig_id)

        elif step == "checkout":
            session["checkout"] = text
            session["step"] = "guests"
            send_reply(user_id, "👥 Jumlah tamu?", ig_id)

        elif step == "guests":
            session["guests"] = text
            reply = (
                f"🏡 Booking untuk @{username}:\n"
                f"✔️ Type : {session['type']}\n"
                f"✔️ Check-in: {session['checkin']}\n"
                f"✔️ Checkout: {session['checkout']}\n"
                f"✔️ Tamu: {session['guests']}\n\n"
                f"Terima kasih kak @{username}, tim kami akan segera menghubungi Anda 🙏"
            )
            send_reply(user_id, reply, ig_id)
            log_to_sheet(
                user_id,
                username,
                f"{session['type']}: {session['checkin']} - {session['checkout']} ({session['guests']} tamu)",
                ig_id
            )
            del user_sessions[user_id]

        return  # pastikan exit di sini jika sedang dalam sesi

    # ✅ 2. Jika user belum dalam sesi — cek trigger atau sapaan
    trigger_keywords = client.get("pemicu", ["booking", "villa", "pesan"])
    if fuzzy_match(lower_text, trigger_keywords):
        send_image(user_id, ig_id)  # kirim gambar promo/villa

        user_sessions[user_id] = {
            "step": "type",
            "last_active": now
        }
        send_reply(user_id, "Untuk Type apa kak?", ig_id)
        return

    # ✅ 3. Greeting jika sapaan dan belum disapa baru-baru ini
    if any(word in lower_text for word in sapaan_keywords):
        last_greet = greeted_users.get(user_id)
        if not last_greet or now - last_greet > GREETING_TIMEOUT:
            greeting = client.get("greeting", f"👋 Halo kak @{username}, ingin booking villa?")
            send_reply(user_id, greeting, ig_id)
            greeted_users[user_id] = now
        return

    # ✅ 4. Jika tidak termasuk trigger atau sapaan → tidak balas (biar admin manual)
    return


