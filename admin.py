# =========================
# ADMIN WEB DASHBOARD
# =========================
@app.route("/admin", methods=["GET", "POST"])
@requires_auth
def admin_dashboard():

    if request.method == "POST":

        form_action = request.form.get("form_action", "").strip()

        # =========================
        # ADMIN ADD MARKETPLACE PRODUCT
        # =========================
        if form_action == "add_marketplace_product":

            category = request.form.get("category", "").strip()
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            price = request.form.get("price", "").strip()
            unit = request.form.get("unit", "").strip()
            seller_name = request.form.get("seller_name", "").strip()
            seller_phone = request.form.get("seller_phone", "").strip()
            seller_location = request.form.get("seller_location", "").strip()
            image_url = request.form.get("image_url", "").strip()

            image_file = request.files.get("marketplace_image")

            if not category or not name:
                return "Category and product name are required. Go back and complete the form."

    stats = get_dashboard_stats()

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT phone, action, details, created_at
        FROM activity_log
        ORDER BY created_at DESC
        LIMIT 100
    """)

    activities = c.fetchall()

    c.execute("SELECT phone, is_paid, payment_status FROM users")
    users = c.fetchall()

    # ===== OFFLINE REGISTRATIONS =====
    c.execute("""
        SELECT phone, full_name, location, detergent_choice, created_at
        FROM offline_registrations
        ORDER BY created_at DESC
    """)
    offline_regs = c.fetchall()

    c.execute("""
    SELECT details, COUNT(*)
    FROM activity_log
    WHERE action='open_module'
    GROUP BY details
    ORDER BY COUNT(*) DESC
    """)
    popular_modules = c.fetchall()

    c.execute("""
    SELECT phone, COUNT(*)
    FROM activity_log
    WHERE action='blocked_access'
    GROUP BY phone
    ORDER BY COUNT(*) DESC
    LIMIT 20
    """)

    blocked_users = c.fetchall()

    c.execute("""
    SELECT phone, followup_stage, last_followup
    FROM users
    WHERE is_paid = 0
    AND followup_stage > 0
    ORDER BY last_followup DESC
    """)

    followups = c.fetchall()

    c.execute("""
    SELECT COUNT(*)
    FROM users
    WHERE last_followup::date = CURRENT_DATE
    """)

    followups_today = c.fetchone()[0]

    c.execute("""
    SELECT phone, total_messages, ai_questions, modules_opened, last_active
    FROM student_metrics
    ORDER BY last_active DESC
    LIMIT 50
    """)

    students = c.fetchall()

    DATABASE_POOL.putconn(conn)

    html = "<h2>Arachis Admin Dashboard</h2>"

    # ===== STATS =====
    html += f"""
    <h3>📊 System Stats</h3>
    <ul>

      html += f"""
    <h3>📊 System Stats</h3>
    <ul>
        <li>Total WhatsApp Users: <b>{stats['total_users']}</b></li>
        <li>Paid Users: <b>{stats['paid_users']}</b></li>
        <li>Module Opens: <b>{stats['module_opens']}</b></li>
        <li>AI Questions Asked: <b>{stats['ai_questions']}</b></li>
        <li>Blocked Access Attempts: <b>{stats['blocked_attempts']}</b></li>
    </ul>

    <h3>📱 Android App Installs</h3>
    <ul>
        <li>Total App Installs / First Opens: <b>{install_stats['total_installs']}</b></li>
        <li>Active Today: <b>{install_stats['active_today']}</b></li>
        <li>Devices Linked To WhatsApp Number: <b>{install_stats['logged_in_devices']}</b></li>
    </ul>
    <hr>
    """

    html += "<h3>📲 Recent Android App Opens</h3>"

    if not install_stats["recent_installs"]:
        html += "<p>No app opens tracked yet.</p>"
    else:
        for r in install_stats["recent_installs"]:
            html += f"""
            📱 Device: {r[3]} |
            Phone: {r[1]} |
            Version: {r[2]} |
            First Open: {r[4]} |
            Last Open: {r[5]} |
            Opens: {r[6]}
            <br>
            """

    html += "<hr>"

    html += "<hr><h3>🚫 Users Blocked From Modules</h3>"

    for b in blocked_users:
        html += f"{b[0]} | Attempts: {b[1]}<br>"

      # ===== UPLOAD =====
    html += """
    <h3>📤 Upload Lesson PDF</h3>
    <form method="POST" enctype="multipart/form-data">
        <input type="file" name="file" required>
        <button type="submit">Upload PDF</button>
    </form>
    <hr>
    """

    # ===== USERS =====
    html += "<h3>👥 Users</h3>"

    for u in users:
        phone = u[0]
        is_paid = u[1]
        payment_status = u[2]

        html += f"""
        {phone} | Paid: {is_paid} | Status: {payment_status}
        | <a href='/admin/approve-package/{phone}/basic'>Approve Basic</a>
        | <a href='/admin/approve-package/{phone}/premium'>Approve Premium</a>
        | <a href='/admin/approve-package/{phone}/advanced'>Approve Advanced</a>
        | <a href='/admin/approve-package/{phone}/spices'>Approve Spices</a>
        | <a href='/admin/reset-device/{phone}'>Reset Device</a>
        | <a href='/admin/revoke/{phone}' style='color:red;'>Revoke Access</a><br>
        """

    html += "<hr><h3>📣 Follow-Up Funnel</h3>"

    if not followups:
        html += "<p>No users in follow-up funnel.</p>"
    else:
        for f in followups:
            phone = f[0]
            stage = f[1]
            last = f[2]

            html += f"""
            📱 {phone} |
            Stage: {stage} |
            Last Followup: {last} |
            <a href="/admin/send-followup/{phone}">📤 Send Message</a>
            <br>
            """
      html += "<hr><h3>🧑🏽‍🏫 Offline Registrations</h3>"

    if not offline_regs:
        html += "<p>No offline registrations yet.</p>"
    else:
        for reg in offline_regs:
            phone = reg[0]
            full_name = reg[1]
            location = reg[2]
            detergent = reg[3]
            created = reg[4]

            html += f"""
            <b>{full_name}</b><br>
            📞 {phone}<br>
            📍 {location}<br>
            🧪 {detergent}<br>
            🗓 {created}<br>
            <a href='/admin/approve-offline/{phone}'>✅ Approve</a>
            <hr>
            """

        html += "<hr><h3>🧠 Student Intelligence</h3>"

        for s in students:
            html += f"""
            📱 {s[0]} |
            💬 Msgs: {s[1]} |
            🤖 AI: {s[2]} |
            📚 Modules: {s[3]} |
            🕒 Last: {s[4]}
            <br>
            """

        html += """
        <hr>
        <h3>📣 Marketing</h3>
        <a href="/admin/followup-unpaid">Send follow-up to unpaid users</a>
        <hr>
        """
      html += "<hr><h3>📨 Template Delivery Logs</h3>"

    if not template_logs:
        html += "<p>No template logs yet.</p>"
    else:
        for t in template_logs:
            html += f"""
            📱 {t[0]} |
            Template: {t[1]} |
            Status: <b>{t[2]}</b> |
            Error: {t[3]} |
            Sent: {t[4]} |
            Updated: {t[5]}
            <br>
            """

    html += "<hr><h3>📜 Activity Feed (Latest 1000)</h3>"

    # ===== ACTIVITY FEED =====
    for a in activities:
        phone = a[0]
        action = a[1]
        details = a[2]
        created_at = a[3]

        html += f"""
        <small>
        [{created_at}] <b>{phone}</b> → {action} ({details})
        </small><br>
        """

    return html
  @app.route("/payment-result", methods=["POST"])
def payment_result():
    return "OK", 200

@app.route("/payment-success")
def payment_success():
    return "Payment received. You may return to WhatsApp."

@app.route("/admin/approve/<phone>")
@requires_auth
def admin_approve(phone):
    mark_paid(normalize_phone(phone))
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/approve-package/<phone>/<package>")
@requires_auth
def admin_approve_package(phone, package):
    phone = normalize_phone(phone)
    package = package.lower()

    if package not in ["basic", "premium", "advanced", "spices"]:
        return "Invalid package"

    has_spices = 1 if package in ["spices", "advanced"] else 0
    has_advanced = 1 if package == "advanced" else 0

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET is_paid=1,
            payment_status='approved',
            package=%s,
            has_spices=%s,
            has_advanced=%s,
            pending_purchase=NULL
        WHERE phone=%s
    """, (package, has_spices, has_advanced, phone))

    conn.commit()
    DATABASE_POOL.putconn(conn)

    send_message(
        phone,
        f"🎉 Payment Approved!\nPackage: {package.upper()}\nWava kukwanisa kuona malesson ako."
    )

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/revoke/<phone>")
@requires_auth
def admin_revoke(phone):
    phone = normalize_phone(phone)

    revoke_access(phone)

    send_message(
        phone,
        "⚠️ Your course access has been removed. If this is a mistake, contact Admin."
    )

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reset-device/<phone>")
@requires_auth
def admin_reset_device(phone):
    phone = normalize_phone(phone)

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE users
        SET device_id=NULL,
            device_model=NULL,
            device_locked_at=NULL
        WHERE phone=%s
    """, (phone,))

    conn.commit()
    DATABASE_POOL.putconn(conn)

    log_activity(phone, "device_lock_reset", "admin")

    send_message(
        phone,
        "✅ Your Arachis app device access has been reset.\n\n"
        "You can now login again using your approved WhatsApp number on your new phone."
    )

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/approve-offline/<phone>")
def approve_offline(phone):

    phone = normalize_phone(phone)

    # mark user as paid
    mark_paid(phone)

    # optional: log activity
    log_activity(phone, "offline_approved", "admin")

    # send confirmation message
    send_message(phone, "🎉 Wagamuchirwa! Wava kukwanisa kuona zvidzidzo zviripo.")

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/marketplace/status/<int:product_id>/<status>")
@requires_auth
def admin_marketplace_status(product_id, status):

    if status not in ["active", "pending", "rejected"]:
        return "Invalid status"

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        UPDATE marketplace_products
        SET status=%s
        WHERE id=%s
        RETURNING name, seller_phone
    """, (status, product_id))

    row = c.fetchone()

    conn.commit()
    DATABASE_POOL.putconn(conn)
