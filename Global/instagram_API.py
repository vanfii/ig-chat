import requests, json
from .config import get_token_by_ig_id, get_menu_link_by_ig_id, log_bot_activity
from datetime import datetime, timezone

def get_username(ig_user_id,ig_id):
    token = get_token_by_ig_id(ig_id)
    url = f"https://graph.instagram.com/v23.0/{ig_user_id}?fields=username&access_token={token}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("username", "Unknown")
    except Exception as e:
        print(f"❌ Gagal ambil username: {e}")
        return "Unknown"

def send_reply(user_id, reply_text, ig_id):
    token = get_token_by_ig_id(ig_id)
    if not token:
        error_msg = f"Token tidak ditemukan untuk IG ID: {ig_id}"
        print(f"❌ {error_msg}")
        log_bot_activity(ig_id, "error", error_msg)
        return

    url = f"https://graph.instagram.com/v23.0/{ig_id}/messages"

    payload = {
        "messaging_product": "instagram",
        "recipient": {"id": user_id},
        "message": {"text": reply_text}
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Akan lempar exception jika status code 4xx/5xx

        print("✅ Berhasil kirim pesan:")
        print("🧾 Status Code:", response.status_code)
        print("📨 Payload:", json.dumps(payload, indent=2))
        print("📥 Response:", json.dumps(response.json(), indent=2))

        # Logging sukses ke UI
        log_bot_activity(ig_id, "reply", f"Balas ke {user_id}: {reply_text}")

    except requests.exceptions.HTTPError as e:
        error_text = response.text if response else str(e)
        print(f"❌ HTTP Error: {e}")
        print("🧾 Respon error:", error_text)
        log_bot_activity(ig_id, "error", f"HTTP Error kirim pesan ke {user_id}: {error_text}")

    except requests.exceptions.RequestException as e:
        print(f"❌ Request Error: {e}")
        log_bot_activity(ig_id, "error", f"Request Error saat kirim ke {user_id}: {e}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        log_bot_activity(ig_id, "error", f"Unexpected error saat kirim ke {user_id}: {e}")


def send_image(recipient_id, ig_id):
    """
    Kirim satu atau beberapa gambar (menu) ke pengguna berdasarkan IG ID client.
    Gambar diambil dari link yang disimpan di Supabase per IG ID.
    """
    token = get_token_by_ig_id(ig_id)
    image_urls = get_menu_link_by_ig_id(ig_id)  # Boleh string atau list

    # Normalisasi: jadi list
    if isinstance(image_urls, str):
        image_urls = [image_urls]
    elif not isinstance(image_urls, list) or not image_urls:
        log_bot_activity(ig_id, "error", f"Token atau link gambar tidak ditemukan.")
        print(f"❌ Token atau link gambar tidak ditemukan untuk IG ID: {ig_id}")
        return

    for image_url in image_urls:
        # Step 1: Upload gambar untuk dapatkan attachment_id
        upload_url = "https://graph.instagram.com/v23.0/me/message_attachments"
        upload_payload = {
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "is_reusable": True,
                        "url": image_url
                    }
                }
            }
        }

        upload_resp = requests.post(upload_url, params={"access_token": token}, json=upload_payload)
        if upload_resp.status_code != 200:
            log_bot_activity(ig_id, "error", f"Gagal upload gambar: {upload_resp.text}")
            print(f"❌ Gagal upload gambar: {upload_resp.text}")
            continue

        attachment_id = upload_resp.json().get("attachment_id")
        if not attachment_id:
            log_bot_activity(ig_id, "error", "Gagal mendapatkan attachment_id.")
            print("❌ Gagal mendapatkan attachment_id")
            continue

        # Step 2: Kirim pesan gambar ke pengguna
        message_url = f"https://graph.instagram.com/v23.0/{ig_id}/messages"
        message_payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {
                        "attachment_id": attachment_id
                    }
                }
            }
        }

        send_resp = requests.post(message_url, params={"access_token": token}, json=message_payload)
        if send_resp.status_code != 200:
            log_bot_activity(ig_id, "error", f"Gagal kirim gambar ke {recipient_id}: {send_resp.text}")
            print(f"❌ Gagal mengirim gambar ke {recipient_id}: {send_resp.text}")
        else:
            log_bot_activity(ig_id, "reply", f"Berhasil kirim gambar ke {recipient_id}")
            print(f"✅ Gambar berhasil dikirim ke {recipient_id}")

def get_token_status(expire_timestamp: int):
    try:
        expire_time = datetime.fromtimestamp(expire_timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        is_expired = now >= expire_time
        status = "Expired" if is_expired else "Active"
        return {
            "status": status,
            "expired_token": expire_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "is_expired": is_expired
        }
    except Exception as e:
        return {
            "status": "Error",
            "expired_token": None,
            "is_expired": True,
            "error": str(e)
        }
