"""Admin dashboard — user approval management.

Serves a single-page HTML dashboard at /admin, accessible only from
localhost (SSH tunnel). Admin can view pending registrations and
approve/reject users with role assignment.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time

from aiohttp import web

from hub_server.auth import verify_password

logger = logging.getLogger(__name__)

_SESSION_SECRET = os.environ.get("CHENEDUSYS_JWT_SECRET", "change-me-in-production")


# ------------------------------------------------------------------
# Session helpers
# ------------------------------------------------------------------

def _create_session_token(username: str) -> str:
    payload = f"{username}:{int(time.time())}"
    sig = hmac.new(_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_session_token(token: str) -> str | None:
    parts = token.split(":")
    if len(parts) != 3:
        return None
    username, ts_str, sig = parts
    expected = hmac.new(
        _SESSION_SECRET.encode(), f"{username}:{ts_str}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    if time.time() - ts > 86400:
        return None
    return username


# ------------------------------------------------------------------
# Guards
# ------------------------------------------------------------------

def _require_localhost(request: web.Request) -> None:
    peer = request.transport.get_extra_info("peername")
    if peer is None or peer[0] not in ("127.0.0.1", "::1"):
        raise web.HTTPForbidden(reason="Admin access restricted to localhost")


def _require_admin(request: web.Request, db) -> dict:
    token = request.cookies.get("admin_session")
    if not token:
        raise web.HTTPUnauthorized(reason="Not authenticated")
    username = _verify_session_token(token)
    if not username:
        raise web.HTTPUnauthorized(reason="Session expired")
    from hub_server.database import Database
    user = db.get_user_by_username(username)
    if not user or user.get("role") != "admin":
        raise web.HTTPForbidden(reason="Admin access required")
    return user


# ------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------

async def admin_page(request: web.Request) -> web.Response:
    _require_localhost(request)
    return web.Response(text=_DASHBOARD_HTML, content_type="text/html")


async def admin_login(request: web.Request) -> web.Response:
    _require_localhost(request)
    db = request.app["db"]
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    user = db.get_user_by_username(username)
    if user is None or not verify_password(password, user["password_hash"]):
        return web.json_response({"reason": "Invalid credentials"}, status=401)
    if user.get("role") != "admin":
        return web.json_response({"reason": "Admin access required"}, status=403)
    if user.get("status") != "active":
        return web.json_response({"reason": "Account not active"}, status=403)

    token = _create_session_token(username)
    resp = web.json_response({"username": username})
    resp.set_cookie("admin_session", token, max_age=86400, httponly=True, samesite="Strict")
    return resp


async def admin_logout(request: web.Request) -> web.Response:
    _require_localhost(request)
    resp = web.json_response({"status": "logged_out"})
    resp.del_cookie("admin_session")
    return resp


async def admin_list_pending(request: web.Request) -> web.Response:
    _require_localhost(request)
    db = request.app["db"]
    _require_admin(request, db)
    return web.json_response(db.list_pending_users())


async def admin_list_all(request: web.Request) -> web.Response:
    _require_localhost(request)
    db = request.app["db"]
    _require_admin(request, db)
    return web.json_response(db.list_all_users())


async def admin_approve(request: web.Request) -> web.Response:
    _require_localhost(request)
    db = request.app["db"]
    _require_admin(request, db)
    body = await request.json()
    user_id = body.get("user_id", "")
    role = body.get("role", "student")
    if role not in ("teacher", "student"):
        return web.json_response({"reason": "Invalid role"}, status=400)
    user = db.get_user_by_id(user_id)
    if user is None:
        return web.json_response({"reason": "User not found"}, status=404)
    db.update_user_status(user_id, "active")
    db.update_user_role(user_id, role)
    logger.info("Admin approved user '%s' (id=%s) as %s", user["username"], user_id, role)
    return web.json_response({"status": "approved", "user_id": user_id})


async def admin_reject(request: web.Request) -> web.Response:
    _require_localhost(request)
    db = request.app["db"]
    _require_admin(request, db)
    body = await request.json()
    user_id = body.get("user_id", "")
    user = db.get_user_by_id(user_id)
    if user is None:
        return web.json_response({"reason": "User not found"}, status=404)
    db.update_user_status(user_id, "rejected")
    logger.info("Admin rejected user '%s' (id=%s)", user["username"], user_id)
    return web.json_response({"status": "rejected", "user_id": user_id})


async def admin_stats(request: web.Request) -> web.Response:
    _require_localhost(request)
    db = request.app["db"]
    _require_admin(request, db)
    users = db.list_all_users()
    return web.json_response({
        "total": len(users),
        "pending": sum(1 for u in users if u["status"] == "pending"),
        "active": sum(1 for u in users if u["status"] == "active"),
        "rejected": sum(1 for u in users if u["status"] == "rejected"),
    })


# ------------------------------------------------------------------
# Route registration
# ------------------------------------------------------------------

def setup_admin_routes(app: web.Application) -> None:
    app.router.add_get("/admin", admin_page)
    app.router.add_post("/admin/login", admin_login)
    app.router.add_post("/admin/logout", admin_logout)
    app.router.add_get("/admin/pending", admin_list_pending)
    app.router.add_get("/admin/users", admin_list_all)
    app.router.add_post("/admin/approve", admin_approve)
    app.router.add_post("/admin/reject", admin_reject)
    app.router.add_get("/admin/stats", admin_stats)


# ------------------------------------------------------------------
# Dashboard HTML
# ------------------------------------------------------------------

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ChenEduSys Admin</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #1a1a2e; color: #e0e0e0; }
.container { max-width: 900px; margin: 0 auto; padding: 20px; }
h1 { color: #4fc3f7; margin-bottom: 8px; font-size: 24px; }
.subtitle { color: #888; margin-bottom: 24px; font-size: 14px; }
.card { background: #16213e; border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.card h2 { color: #4fc3f7; font-size: 16px; margin-bottom: 12px; }
.stats { display: flex; gap: 16px; margin-bottom: 20px; }
.stat { flex: 1; text-align: center; padding: 12px; background: #0f3460; border-radius: 6px; }
.stat .num { font-size: 28px; font-weight: bold; }
.stat .label { font-size: 12px; color: #888; margin-top: 4px; }
.stat.pending .num { color: #ffa726; }
.stat.active .num { color: #66bb6a; }
.stat.rejected .num { color: #ef5350; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid #1a1a3e; font-size: 14px; }
th { color: #888; font-weight: 600; font-size: 12px; text-transform: uppercase; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.badge.pending { background: #3e2723; color: #ffa726; }
.badge.active { background: #1b5e20; color: #66bb6a; }
.badge.rejected { background: #3e1a1a; color: #ef5350; }
.badge.teacher { background: #1a237e; color: #7986cb; }
.badge.student { background: #1b5e20; color: #81c784; }
.btn { padding: 6px 14px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-approve { background: #2e7d32; color: white; }
.btn-reject { background: #c62828; color: white; }
.btn:hover { opacity: 0.85; }
select { padding: 4px 8px; border-radius: 4px; border: 1px solid #333; background: #0f3460; color: #e0e0e0; font-size: 13px; }
#login-form { max-width: 320px; margin: 60px auto; }
#login-form input { width: 100%; padding: 10px 12px; margin-bottom: 12px; border: 1px solid #333; border-radius: 4px; background: #0f3460; color: #e0e0e0; font-size: 14px; }
#login-form button { width: 100%; padding: 10px; background: #4fc3f7; color: #1a1a2e; border: none; border-radius: 4px; font-size: 15px; font-weight: 600; cursor: pointer; }
#login-form button:hover { background: #29b6f6; }
.tabs { display: flex; gap: 4px; margin-bottom: 16px; }
.tab { padding: 8px 16px; background: #0f3460; border: none; color: #888; cursor: pointer; border-radius: 4px 4px 0 0; font-size: 13px; }
.tab.active { background: #16213e; color: #4fc3f7; }
.toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: 6px; font-size: 14px; z-index: 100; opacity: 0; transition: opacity 0.3s; }
.toast.show { opacity: 1; }
.toast.success { background: #2e7d32; color: white; }
.toast.error { background: #c62828; color: white; }
.actions { display: flex; gap: 8px; align-items: center; }
.logout-link { float: right; color: #888; font-size: 13px; cursor: pointer; }
.logout-link:hover { color: #4fc3f7; }
</style>
</head>
<body>
<div class="container">
  <div id="login-form">
    <h1 style="text-align:center;margin-bottom:24px">ChenEduSys Admin</h1>
    <input type="text" id="username" placeholder="Admin username" autocomplete="username">
    <input type="password" id="password" placeholder="Password" autocomplete="current-password">
    <button onclick="doLogin()">Login</button>
    <p id="login-error" style="color:#ef5350;text-align:center;margin-top:12px;font-size:13px"></p>
  </div>

  <div id="dashboard" style="display:none">
    <h1>ChenEduSys Admin <span class="logout-link" onclick="doLogout()">Logout</span></h1>
    <p class="subtitle">User account management</p>

    <div class="stats" id="stats-bar"></div>

    <div class="tabs">
      <button class="tab active" onclick="showTab('pending')">Pending Approval</button>
      <button class="tab" onclick="showTab('all')">All Users</button>
    </div>

    <div id="tab-pending" class="card">
      <table>
        <thead><tr><th>Username</th><th>Requested Role</th><th>Registered</th><th>Actions</th></tr></thead>
        <tbody id="pending-body"></tbody>
      </table>
      <p id="no-pending" style="color:#888;text-align:center;padding:20px;display:none">No pending registrations</p>
    </div>

    <div id="tab-all" class="card" style="display:none">
      <table>
        <thead><tr><th>Username</th><th>Role</th><th>Status</th><th>Registered</th></tr></thead>
        <tbody id="all-body"></tbody>
      </table>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let currentTab = 'pending';

function showToast(msg, type) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show ' + type;
  setTimeout(() => t.className = 'toast', 2500);
}

async function api(path, opts = {}) {
  const resp = await fetch(path, { ...opts, credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...opts.headers } });
  return resp;
}

async function doLogin() {
  const u = document.getElementById('username').value;
  const p = document.getElementById('password').value;
  const err = document.getElementById('login-error');
  err.textContent = '';
  const resp = await api('/admin/login', {
    method: 'POST', body: JSON.stringify({ username: u, password: p })
  });
  if (resp.ok) {
    document.getElementById('login-form').style.display = 'none';
    document.getElementById('dashboard').style.display = 'block';
    refresh();
  } else {
    const body = await resp.json();
    err.textContent = body.reason || 'Login failed';
  }
}

async function doLogout() {
  await api('/admin/logout', { method: 'POST' });
  document.getElementById('login-form').style.display = 'block';
  document.getElementById('dashboard').style.display = 'none';
}

function showTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-pending').style.display = tab === 'pending' ? 'block' : 'none';
  document.getElementById('tab-all').style.display = tab === 'all' ? 'block' : 'none';
}

async function refresh() {
  try {
    const [statsResp, pendingResp, allResp] = await Promise.all([
      api('/admin/stats'), api('/admin/pending'), api('/admin/users')
    ]);
    if (statsResp.status === 401) { doLogout(); return; }
    const stats = await statsResp.json();
    const pending = await pendingResp.json();
    const all = await allResp.json();

    // Stats bar
    document.getElementById('stats-bar').innerHTML =
      '<div class="stat pending"><div class="num">' + stats.pending + '</div><div class="label">Pending</div></div>' +
      '<div class="stat active"><div class="num">' + stats.active + '</div><div class="label">Active</div></div>' +
      '<div class="stat rejected"><div class="num">' + stats.rejected + '</div><div class="label">Rejected</div></div>' +
      '<div class="stat"><div class="num">' + stats.total + '</div><div class="label">Total</div></div>';

    // Pending table
    const pb = document.getElementById('pending-body');
    const np = document.getElementById('no-pending');
    if (pending.length === 0) {
      pb.innerHTML = '';
      np.style.display = 'block';
    } else {
      np.style.display = 'none';
      pb.innerHTML = pending.map(u =>
        '<tr><td>' + esc(u.username) + '</td><td><span class="badge ' + u.role + '">' + u.role + '</span></td>' +
        '<td>' + fmtTime(u.created_at) + '</td>' +
        '<td class="actions"><select id="role-' + u.id + '"><option value="student">student</option><option value="teacher">teacher</option></select>' +
        '<button class="btn btn-approve" onclick="approve(\'' + u.id + '\')">Approve</button>' +
        '<button class="btn btn-reject" onclick="reject(\'' + u.id + '\')">Reject</button></td></tr>'
      ).join('');
    }

    // All users table
    const ab = document.getElementById('all-body');
    ab.innerHTML = all.map(u =>
      '<tr><td>' + esc(u.username) + '</td>' +
      '<td><span class="badge ' + u.role + '">' + u.role + '</span></td>' +
      '<td><span class="badge ' + u.status + '">' + u.status + '</span></td>' +
      '<td>' + fmtTime(u.created_at) + '</td></tr>'
    ).join('');
  } catch (e) { console.error(e); }
}

async function approve(id) {
  const role = document.getElementById('role-' + id).value;
  const resp = await api('/admin/approve', { method: 'POST', body: JSON.stringify({ user_id: id, role }) });
  if (resp.ok) { showToast('User approved as ' + role, 'success'); refresh(); }
  else { const b = await resp.json(); showToast(b.reason || 'Error', 'error'); }
}

async function reject(id) {
  if (!confirm('Reject this registration?')) return;
  const resp = await api('/admin/reject', { method: 'POST', body: JSON.stringify({ user_id: id }) });
  if (resp.ok) { showToast('User rejected', 'success'); refresh(); }
  else { const b = await resp.json(); showToast(b.reason || 'Error', 'error'); }
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function fmtTime(s) { if (!s) return '-'; const d = new Date(s + 'Z'); return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}); }

// Auto-refresh every 10s
setInterval(() => { if (document.getElementById('dashboard').style.display !== 'none') refresh(); }, 10000);
</script>
</body>
</html>
"""
