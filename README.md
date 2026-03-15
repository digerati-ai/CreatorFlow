# CreatorFlow

Content publishing platform for TikTok creators. Publish original video content to TikTok with full control over privacy, interactions, and compliance.

## Features

- Secure TikTok OAuth login (Login Kit)
- Video upload with preview
- Full privacy and interaction controls
- Commercial content disclosure (Your Brand / Branded Content)
- Direct Post or Upload to Drafts
- Real-time post status tracking
- TikTok Content Sharing Guidelines compliant UX

## Setup

### Local Development

1. Clone the repo
2. Create a virtual environment:
   ```
   python -m venv .venv
   .venv\Scripts\activate       # Windows
   source .venv/bin/activate    # macOS/Linux
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your TikTok credentials
5. Run:
   ```
   python app.py
   ```
6. Open `http://localhost:5000`

### Render Deployment

- **Language**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app`
- Set environment variables in the Render dashboard

## TikTok Developer Setup

1. Create an app at [developers.tiktok.com](https://developers.tiktok.com)
2. Add **Login Kit** and **Content Posting API** products
3. Configure scopes: `user.info.basic`, `video.publish`, `video.upload`
4. Set redirect URI to `https://your-domain/auth/tiktok/callback`
5. Create a Sandbox and add test accounts
6. Record demo video showing the full OAuth + publish flow
7. Submit for review

## License

Proprietary. All rights reserved.
