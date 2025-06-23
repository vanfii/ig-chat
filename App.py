import json
import requests
from flask import Flask, request, redirect, jsonify, render_template, url_for, flash, session
from Global.config import app_id, app_secret, VERIFY_TOKEN, redirect_url, SECRET_KEY, log_cache
from Global.sessions import handle_message
from Global.instagram_API import  get_token_status
from Global.config import supabase, load_all_clients , delete_client_by_ig_id, replace_menu_image, insert_user, get_all_users, insert_user
from datetime import datetime,timezone
from Global.spreadsheet import count_orders_from_sheet
import logging
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(
    level=logging.INFO,  # Ganti jadi DEBUG kalau mau lihat semua
    format="%(asctime)s [%(levelname)s] %(message)s"
)


app = Flask(__name__)
app.secret_key = SECRET_KEY
now = datetime.now()
@app.route("/generate_token")
def generate_token_page():
    return render_template("generate_token.html")

@app.route("/")
def index():
    code = request.args.get("code")
    if code:
        return f"Authorization Code:<br><code>{code}</code>"
    return "No code received. Silakan login terlebih dahulu."

@app.route("/privacy_policy")
def privacy_policy():
    try:
        with open("./privacyandpolicy.html", "rb") as file:
            return file.read()
    except FileNotFoundError:
        return "<p>Privacy policy not found.</p>", 404

@app.route("/auth")
def authorize():
    base_url = "https://www.instagram.com/oauth/authorize"
    response_type = "code"
    scope = ",".join([
        "instagram_business_basic",
        "instagram_business_manage_messages",
        "instagram_business_manage_comments",
        "instagram_business_content_publish"
    ])

    url = (
        f"{base_url}"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_url}"
        f"&response_type={response_type}"
        f"&scope={scope.replace(',', '%2C')}"
    )
    return redirect(url)

@app.route("/input_token", methods=["GET", "POST"])
def get_token_ui():
    if request.method == "POST":
        authorization_code = request.form.get("code")
        if not authorization_code:
            return "❌ Authorization code tidak ditemukan.", 400

        url = "https://api.instagram.com/oauth/access_token"
        form_data = {
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_url,
            "code": authorization_code
        }

        response = requests.post(url, data=form_data)
        if response.status_code != 200:
            return f"❌ Gagal mendapatkan token: {response.text}", 500

        data = response.json()
        short_token = data.get("access_token")
        user_id = data.get("user_id")

        # ✅ Tampilkan tombol untuk tukar token
        return render_template("show_short_token.html", token=short_token, user_id=user_id)

    return render_template("get_token.html")

@app.route("/long_token")
def exchange_long_lived_token():
    short_token = request.args.get("access_token")
    if not short_token:
        return "❌ Short-lived access token tidak ditemukan sebagai parameter 'access_token'.", 400

    url = "https://graph.instagram.com/access_token"
    params = {
        "grant_type": "ig_exchange_token",
        "client_secret": app_secret,
        "access_token": short_token
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        return f"❌ Gagal menukar token: {response.text}", 500

    data = response.json()
    long_lived_token = data.get("access_token")
    expires_in = data.get("expires_in")

    return f"""
    ✅ <b>Long-lived Token:</b><br><code>{long_lived_token}</code><br>
    ⏳ <b>Berlaku selama:</b> {expires_in} detik
    """

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    if request.method == "POST":
        try:
            data = request.get_json()

            # Debug hanya untuk developer
            logging.debug("Webhook Payload:\n%s", json.dumps(data, indent=2))

            for entry in data.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    if "message" not in messaging_event:
                        continue

                    message = messaging_event["message"]
                    ig_id = entry.get("id")

                    if message.get("is_echo", False):
                        logging.debug("Skip echo message")
                        continue

                    sender_id = messaging_event.get("sender", {}).get("id")
                    text = message.get("text", "")

                    if sender_id and text:
                        logging.info("Message from %s: %s", sender_id, text)
                        handle_message(sender_id, text, ig_id)
                        logging.info("Message handled.")

        except Exception as e:
            logging.exception("Error parsing webhook:")

        return "OK", 200

    elif request.method == "GET":
        hub_mode = request.args.get("hub.mode")
        hub_challenge = request.args.get("hub.challenge")
        hub_verify_token = request.args.get("hub.verify_token")

        logging.info("Verification Request - mode: %s, token: %s", hub_mode, hub_verify_token)

        if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
            logging.info("Verification successful")
            return hub_challenge, 200
        else:
            logging.warning("Verification failed - token mismatch")
            return "<p>Verification token mismatch.</p>", 403

@app.route("/api/users", methods=["GET", "POST"])
def api_users():
    if request.method == "GET":
        try:
            response = get_all_users()
            return jsonify(response.data), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == "POST":
        try:
            data = request.get_json()
            response = insert_user(data)

            if getattr(response, "data", None):
                return jsonify({"success": True}), 201
            return jsonify({"error": "Gagal menambahkan user"}), 500

        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/admin")
def admin_panel():
    clients = load_all_clients()
    users = list(clients.values())

    for user in users:
        token_info = get_token_status(user.get("expired_token", 0))
        user["token_status"] = token_info["status"]
        user["expire_str"] = token_info["expired_token"]

    return render_template("admin.html", users=users)

@app.route("/add_user", methods=["GET", "POST"])
def add_user():
    if request.method == "POST":
        trigger_raw = request.form.get("trigger_keywords", "")
        stop_raw = request.form.get("stop_keywords", "")

        trigger_keywords = [x.strip() for x in trigger_raw.split(",") if x.strip()]
        stop_keywords = [x.strip() for x in stop_raw.split(",") if x.strip()]

        data = {
            "ig_id": request.form["ig_id"].strip(),
            "client_name": request.form["client_name"].strip(),
            "token": request.form["token"].strip(),
            "business_type": request.form["business_type"],
            "trigger_keywords": trigger_keywords,
            "stop_keywords": stop_keywords,
            "joined": datetime.now(timezone.utc).isoformat()
        }

        response = insert_user(data)
        if not response.data:
            return "❌ Terjadi kesalahan saat menyimpan user.", 400
        return redirect(url_for("admin_panel"))

    return render_template("add_user.html")


@app.route("/delete/<string:ig_id>")
def delete_user(ig_id):
    try:
        delete_client_by_ig_id(ig_id)
        print(f"✅ User dengan IG ID {ig_id} berhasil dihapus.")
    except Exception as e:
        print(f"❌ Gagal menghapus user: {e}")
    return redirect(url_for("admin_panel"))

@app.route("/detail/<ig_id>", methods=["GET"])
def detail_user(ig_id):
    # Ambil data client dari Supabase berdasarkan ig_id
    response = supabase.table("client").select("*").eq("ig_id", ig_id).single().execute()

    if not response.data:
        return "Client tidak ditemukan", 404

    client = response.data

    # Ambil spreadsheet_id berdasarkan ig_id
    spreadsheet_id = client.get("spreadsheet_id")
    order_count = 0

    # Hitung jumlah order jika spreadsheet_id tersedia
    if spreadsheet_id:
        try:
            order_count = count_orders_from_sheet(spreadsheet_id)
        except Exception as e:
            print("❌ Gagal membaca sheet:", e)

    return render_template(
        "detai_user.html",  # Typo? Seharusnya mungkin "detail_user.html"
        user=client,
        order_count=order_count
    )
@app.route("/logs/<ig_id>")
def get_logs(ig_id):
    logs = log_cache.get(ig_id, [])
    error_logs = [log for log in logs if log["type"] == "error"]
    return jsonify(error_logs)


@app.route("/edit/<ig_id>", methods=["GET"])
def edit_user(ig_id):
    data = supabase.table("client").select("*").eq("ig_id", ig_id).single().execute()
    if not data.data:
        return "Client tidak ditemukan", 404
    return render_template("edit_user.html", client=data.data)

from flask import request, redirect, session, flash

@app.route("/edit/<ig_id>/update", methods=["POST"])
def update_user(ig_id):
    updated_data = {
        "client_name": request.form["client_name"],
        "token": request.form["token"],
        "redirect_url": request.form["redirect_url"],
        "spreadsheet_id": request.form["spreadsheet_id"],
        "greeting": request.form["greeting"],
        "closing": request.form["closing"],
        "promp_extra": request.form["promp_extra"],
        "business_type": request.form["business_type"],
        "expired_token": request.form["expired_token"],
        "pemicu": [p.strip() for p in request.form["pemicu"].split(",") if p.strip()],
        "triger_stop": [t.strip() for t in request.form["triger_stop"].split(",") if t.strip()],
    }

    # Simpan perubahan ke Supabase
    supabase.table("client").update(updated_data).eq("ig_id", ig_id).execute()

    # Tentukan redirect berdasarkan role
    role = session.get("role")
    if role == "client":
        flash("✅ Perubahan disimpan. Kamu diarahkan ke halaman detail.", "success")
        return redirect(f"/detail/{ig_id}")
    else:
        flash("✅ Data berhasil diperbarui.", "success")
        return redirect("/admin")


@app.route("/edit/<ig_id>/add-image", methods=["POST"])
def upload_menu_image_route(ig_id):
    image = request.files["image"]
    from config import add_menu_image  # pastikan sudah ada
    add_menu_image(ig_id, image)
    return redirect(f"/edit/{ig_id}")

@app.route("/edit/<ig_id>/replace-image/<int:index>", methods=["POST"])
def replace_image(ig_id, index):
    new_image = request.files.get("new_image")
    if not new_image:
        return "Gambar baru tidak ditemukan.", 400
    try:
        new_url = replace_menu_image(ig_id, index, new_image)
        return redirect(url_for("edit_client", ig_id=ig_id))
    except Exception as e:
        return str(e), 500
    
@app.route("/edit/<ig_id>/delete-image/<int:index>", methods=["POST"])
def delete_image(ig_id, index):
    try:
        # 1. Ambil data client
        response = supabase.table("client").select("menu_link").eq("ig_id", ig_id).execute()
        if not response.data:
            return "Client tidak ditemukan.", 404

        menu_links = response.data[0].get("menu_link", [])
        if not isinstance(menu_links, list):
            return "Kolom menu_link bukan array.", 400

        if index < 0 or index >= len(menu_links):
            return "Index gambar tidak valid.", 400

        # 2. Hapus file dari storage
        image_url = menu_links[index]
        storage_path = image_url.split("/storage/v1/object/public/menus/")[-1]
        supabase.storage.from_("menus").remove([storage_path])

        # 3. Hapus dari list
        menu_links.pop(index)

        # 4. Update ke database
        update_response = supabase.table("client").update({
            "menu_link": menu_links
        }).eq("ig_id", ig_id).execute()

        if hasattr(update_response, 'error') and update_response.error:
            return str(update_response.error), 500

        return redirect(url_for("edit_user", ig_id=ig_id))

    except Exception as e:
        return str(e), 500

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        result = supabase.table("users").select("*").eq("username", username).execute()
        users = result.data
        print("🔥 Cek hasil query:", users)

        if not users:
            flash("❌ Username tidak ditemukan", "danger")
            return redirect("/login")

        user = users[0]
        if check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["ig_id"] = user.get("ig_id")

            flash("✅ Login berhasil!", "success")
            return redirect("/admin" if user["role"] == "admin" else f"/detail/{user['ig_id']}")
        else:
            flash("❌ Password salah", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("✅ Berhasil logout", "info")
    return redirect("/login")

@app.before_request
def protect_routes():
    protected_admin = [
        "admin_panel", "add_user", "delete_user", "add_login_user"
    ]
    protected_client = ["detail_user"]
    edit_user_endpoint = "edit_user"

    current_role = session.get("role")
    current_endpoint = request.endpoint
    current_path = request.path  # e.g., "/edit/17841234"
    session_ig_id = session.get("ig_id")

    # 🔒 Hanya admin untuk route yang sangat sensitif
    if current_endpoint in protected_admin and current_role != "admin":
        flash("❌ Akses ditolak. Halaman khusus admin.", "danger")
        return redirect("/login")

    # 🔒 Boleh admin dan client untuk detail_user
    if current_endpoint in protected_client:
        if not session_ig_id and current_role != "admin":
            flash("❌ Anda tidak memiliki akses ke halaman ini.", "danger")
            return redirect("/login")

    # 🔒 Edit user boleh diakses admin atau client miliknya sendiri
    if current_endpoint == edit_user_endpoint:
        # Ekstrak ig_id dari path (misal: /edit/<ig_id>)
        path_ig_id = current_path.split("/edit/")[-1]
        if current_role == "client" and session_ig_id != path_ig_id:
            flash("❌ Anda hanya dapat mengedit akun Anda sendiri.", "danger")
            return redirect("/login")


@app.route("/add_login_user", methods=["GET", "POST"])
def add_login_user():
    if session.get("role") != "admin":
        return redirect("/login")

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]
        ig_id = request.form.get("ig_id") or None

        # Validasi: cek apakah username sudah ada
        existing = supabase.table("users").select("*").eq("username", username).execute().data
        if existing:
            flash("❌ Username sudah terdaftar!", "danger")
            return redirect("/add_login_user")

        hashed_password = generate_password_hash(password)
        supabase.table("users").insert({
            "username": username,
            "password": hashed_password,
            "role": role,
            "ig_id": ig_id
        }).execute()

        flash("✅ User berhasil ditambahkan!", "success")
        return redirect("/add_login_user")

    return render_template("add_user_login.html")

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()} 

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
