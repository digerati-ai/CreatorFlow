"""
CreatorFlow - Content Publishing Platform for TikTok Creators
Flask web application with TikTok Content Posting API integration.
"""

import os
import json
import time
import secrets
import logging
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
from flask import (
    Flask, render_template, redirect, url_for, request,
    session, flash, jsonify, abort, send_from_directory, make_response
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024  # 128 MB (sandbox limit)

TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USERINFO_URL = "https://open.tiktokapis.com/v2/user/info/"
TIKTOK_CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
TIKTOK_PUBLISH_VIDEO_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_UPLOAD_INBOX_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
TIKTOK_PUBLISH_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
TIKTOK_REFRESH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"mp4", "webm", "mov"}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_connected_account():
    """Return the TikTok account stored in the session, or None."""
    return session.get("tiktok_account")


def tiktok_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def refresh_access_token(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a new access token."""
    resp = requests.post(TIKTOK_TOKEN_URL, data={
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    data = resp.json()
    if "access_token" in data:
        return data
    logger.error("Token refresh failed: %s", data)
    return None


def ensure_valid_token() -> str | None:
    """Return a valid access token, refreshing if needed."""
    acct = get_connected_account()
    if not acct:
        return None

    expires_at = acct.get("expires_at", 0)
    if time.time() < expires_at - 300:  # 5 min buffer
        return acct["access_token"]

    # Attempt refresh
    refreshed = refresh_access_token(acct.get("refresh_token", ""))
    if refreshed:
        acct["access_token"] = refreshed["access_token"]
        acct["refresh_token"] = refreshed.get("refresh_token", acct["refresh_token"])
        acct["expires_at"] = time.time() + refreshed.get("expires_in", 86400)
        session["tiktok_account"] = acct
        session.modified = True
        return acct["access_token"]

    return None


# ---------------------------------------------------------------------------
# Public marketing pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    account = get_connected_account()
    logger.info("INDEX: session keys: %s, has account: %s", list(session.keys()), account is not None)
    return render_template("index.html", account=account)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/tiktoktnYOLBZ7ZoFhy3pJKoYCwGrpulwkRgcx.txt")
def tiktok_verification():
    return send_from_directory("static", "tiktoktnYOLBZ7ZoFhy3pJKoYCwGrpulwkRgcx.txt")

# ---------------------------------------------------------------------------
# TikTok OAuth flow
# ---------------------------------------------------------------------------
@app.route("/auth/tiktok")
def auth_tiktok():
    """Redirect user to TikTok's authorization page."""
    csrf_state = secrets.token_urlsafe(32)
    session["oauth_state"] = csrf_state

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "response_type": "code",
        "scope": "user.info.basic,video.publish,video.upload",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": csrf_state,
    }
    auth_url = f"{TIKTOK_AUTH_URL}?{urlencode(params)}"
    return redirect(auth_url)


@app.route("/auth/tiktok/callback")
def auth_tiktok_callback():
    """Handle the OAuth callback from TikTok."""
    error = request.args.get("error")
    if error:
        flash(f"TikTok authorization failed: {request.args.get('error_description', error)}", "error")
        return redirect(url_for("index"))

    code = request.args.get("code")
    state = request.args.get("state")

    if not code:
        flash("No authorization code received from TikTok.", "error")
        return redirect(url_for("index"))

    # Verify CSRF state
    if state != session.pop("oauth_state", None):
        flash("Invalid state parameter. Please try again.", "error")
        return redirect(url_for("index"))

    # Exchange code for access token
    token_resp = requests.post(TIKTOK_TOKEN_URL, data={
        "client_key": TIKTOK_CLIENT_KEY,
        "client_secret": TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    token_data = token_resp.json()

    if "access_token" not in token_data:
        logger.error("Token exchange failed: %s", token_data)
        flash("Failed to obtain access token from TikTok.", "error")
        return redirect(url_for("index"))

    access_token = token_data["access_token"]
    open_id = token_data.get("open_id", "")

    # Fetch user info
    user_resp = requests.get(
        TIKTOK_USERINFO_URL,
        headers=tiktok_headers(access_token),
        params={"fields": "open_id,union_id,avatar_url,display_name"},
    )
    user_data = user_resp.json().get("data", {}).get("user", {})

    # Store in session
    session["tiktok_account"] = {
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token", ""),
        "open_id": open_id,
        "expires_at": time.time() + token_data.get("expires_in", 86400),
        "display_name": user_data.get("display_name", "TikTok Creator"),
        "avatar_url": user_data.get("avatar_url", ""),
    }

    flash(f"Successfully connected as {user_data.get('display_name', 'TikTok Creator')}!", "success")
    return redirect(url_for("dashboard"))


@app.route("/auth/disconnect")
def auth_disconnect():
    """Remove TikTok account from session."""
    logger.info("DISCONNECT: session keys before: %s", list(session.keys()))
    session.clear()
    logger.info("DISCONNECT: session keys after clear: %s", list(session.keys()))
    # Redirect to index with a clean response — delete cookie by name AND path
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("session", "", expires=0, path="/")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.route("/debug/session")
def debug_session():
    """Debug route to see raw session state."""
    return jsonify({
        "session_keys": list(session.keys()),
        "has_account": "tiktok_account" in session,
        "display_name": session.get("tiktok_account", {}).get("display_name", None),
    })


# ---------------------------------------------------------------------------
# Authenticated app pages
# ---------------------------------------------------------------------------
@app.after_request
def add_no_cache(response):
    """Prevent browser from caching authenticated pages."""
    if request.endpoint in ("dashboard", "publish", "index"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.route("/dashboard")
def dashboard():
    account = get_connected_account()
    if not account:
        flash("Please connect your TikTok account first.", "info")
        return redirect(url_for("index"))
    return render_template("dashboard.html", account=account)


@app.route("/publish", methods=["GET"])
def publish():
    """Render the publish page with all required TikTok UX elements."""
    account = get_connected_account()
    if not account:
        flash("Please connect your TikTok account first.", "info")
        return redirect(url_for("index"))

    access_token = ensure_valid_token()
    if not access_token:
        flash("Your session has expired. Please reconnect your TikTok account.", "error")
        return redirect(url_for("auth_disconnect"))

    # Query creator info (required by TikTok UX guidelines)
    creator_info = {}
    try:
        resp = requests.post(
            TIKTOK_CREATOR_INFO_URL,
            headers=tiktok_headers(access_token),
        )
        resp_data = resp.json()
        if resp_data.get("error", {}).get("code") == "ok":
            creator_info = resp_data.get("data", {})
    except Exception as e:
        logger.error("Failed to fetch creator info: %s", e)
        flash("Unable to fetch creator information. Please try again.", "error")

    return render_template("publish.html", account=account, creator_info=creator_info)


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Handle video upload and publish/draft to TikTok."""
    account = get_connected_account()
    if not account:
        return jsonify({"error": "Not authenticated"}), 401

    access_token = ensure_valid_token()
    if not access_token:
        return jsonify({"error": "Token expired. Please reconnect."}), 401

    # Gather form data
    title = request.form.get("title", "").strip()
    privacy_level = request.form.get("privacy_level", "")
    allow_comment = request.form.get("allow_comment") == "on"
    allow_duet = request.form.get("allow_duet") == "on"
    allow_stitch = request.form.get("allow_stitch") == "on"
    post_mode = request.form.get("post_mode", "UPLOAD_TO_INBOX")

    # Commercial content
    commercial_content = request.form.get("commercial_content") == "on"
    your_brand = request.form.get("your_brand") == "on"
    branded_content = request.form.get("branded_content") == "on"

    # Consent check
    consent = request.form.get("consent") == "on"
    if not consent:
        return jsonify({"error": "You must agree to TikTok's Music Usage Confirmation."}), 400

    if not privacy_level:
        return jsonify({"error": "Please select a privacy level."}), 400

    # Handle file upload
    if "video" not in request.files:
        return jsonify({"error": "No video file provided."}), 400

    video = request.files["video"]
    if video.filename == "" or not allowed_file(video.filename):
        return jsonify({"error": "Invalid video file. Accepted: MP4, WebM, MOV."}), 400

    filename = secure_filename(video.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    video.save(filepath)
    file_size = os.path.getsize(filepath)

    try:
        description = request.form.get("description", "").strip()

        # Source info is common to both modes
        source_info = {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,
            "total_chunk_count": 1,
        }

        if post_mode == "DIRECT_POST":
            # Direct Post: include post_info with all metadata
            endpoint = TIKTOK_PUBLISH_VIDEO_URL
            post_info = {
                "title": title,
                "description": description,
                "privacy_level": privacy_level,
                "disable_comment": not allow_comment,
                "disable_duet": not allow_duet,
                "disable_stitch": not allow_stitch,
            }

            # Add commercial content fields if applicable
            if commercial_content:
                if your_brand and branded_content:
                    post_info["brand_content_toggle"] = True
                    post_info["brand_organic_toggle"] = True
                elif branded_content:
                    post_info["brand_content_toggle"] = True
                elif your_brand:
                    post_info["brand_organic_toggle"] = True

            init_body = {
                "post_info": post_info,
                "source_info": source_info,
            }
        else:
            # Upload to Inbox: only source_info, creator sets metadata in TikTok app
            endpoint = TIKTOK_UPLOAD_INBOX_URL
            init_body = {
                "source_info": source_info,
            }

        logger.info("Upload init request to %s: %s", endpoint, json.dumps(init_body))

        init_resp = requests.post(
            endpoint,
            headers=tiktok_headers(access_token),
            json=init_body,
        )
        init_data = init_resp.json()
        logger.info("Upload init response: %s", json.dumps(init_data))

        if init_data.get("error", {}).get("code") != "ok":
            error_msg = init_data.get("error", {}).get("message", "Upload initiation failed.")
            logger.error("Upload init failed: %s", init_data)
            return jsonify({"error": error_msg}), 400

        upload_url = init_data["data"]["upload_url"]
        publish_id = init_data["data"]["publish_id"]

        # Upload the video file
        with open(filepath, "rb") as f:
            video_bytes = f.read()

        upload_resp = requests.put(
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                "Content-Type": "video/mp4",
            },
            data=video_bytes,
        )

        logger.info("Video PUT status: %s", upload_resp.status_code)
        logger.info("Video PUT response: %s", upload_resp.text[:500] if upload_resp.text else "(empty)")

        if upload_resp.status_code not in (200, 201):
            return jsonify({"error": f"Video upload to TikTok failed. Status: {upload_resp.status_code}"}), 400

        # Check publish status immediately
        try:
            status_resp = requests.post(
                TIKTOK_PUBLISH_STATUS_URL,
                headers=tiktok_headers(access_token),
                json={"publish_id": publish_id},
            )
            logger.info("Initial publish status: %s", status_resp.text[:500])
        except Exception as se:
            logger.warning("Status check failed: %s", se)

        return jsonify({
            "success": True,
            "publish_id": publish_id,
            "message": "Video uploaded successfully! Check your TikTok inbox for a notification to finalize your post.",
        })

    except Exception as e:
        logger.error("Upload error: %s", e)
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temp file
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/api/publish-status", methods=["POST"])
def api_publish_status():
    """Poll publish status for a given publish_id."""
    account = get_connected_account()
    if not account:
        return jsonify({"error": "Not authenticated"}), 401

    access_token = ensure_valid_token()
    if not access_token:
        return jsonify({"error": "Token expired"}), 401

    publish_id = request.json.get("publish_id")
    if not publish_id:
        return jsonify({"error": "No publish_id provided"}), 400

    resp = requests.post(
        TIKTOK_PUBLISH_STATUS_URL,
        headers=tiktok_headers(access_token),
        json={"publish_id": publish_id},
    )
    return jsonify(resp.json())


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
