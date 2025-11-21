import hmac
import hashlib
import base64
import time
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from config import HMAC_SECRET
from db_init import activate_token

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_signature(payload: str, sig: str) -> bool:
    try:
        # DEBUG: Print secret being used
        logger.info(f"HMAC_SECRET (first 10 chars): {HMAC_SECRET[:10]}...")
        logger.info(f"Payload: {payload}")
        logger.info(f"Received sig: {sig}")
        
        expected_sig = hmac.new(
            HMAC_SECRET.encode(), 
            payload.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        logger.info(f"Expected sig: {expected_sig}")
        
        result = hmac.compare_digest(expected_sig, sig)
        logger.info(f"Signature match: {result}")
        
        return result
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

@router.get("/ad")
async def show_ad_page(payload: str = None, sig: str = None):
    
    logger.info(f"=== AD PAGE REQUEST ===")
    logger.info(f"Payload: {payload}")
    logger.info(f"Signature: {sig}")
    
    if not payload or not sig:
        return HTMLResponse("<h1>❌ Missing parameters!</h1>", status_code=400)
    
    if not verify_signature(payload, sig):
        return HTMLResponse(
            "<h1>❌ Invalid or tampered link!</h1>"
            "<p>Please request a new token from the bot.</p>",
            status_code=400
        )
    
    try:
        decoded_payload = base64.urlsafe_b64decode(payload.encode()).decode()
        logger.info(f"Decoded payload: {decoded_payload}")
        uid, timestamp = decoded_payload.split(":")
        uid = int(uid)
        timestamp = int(timestamp)
    except Exception as e:
        logger.error(f"Payload decode error: {e}")
        return HTMLResponse("<h1>❌ Invalid payload!</h1>", status_code=400)
    
    current_time = int(time.time())
    if current_time - timestamp > 86400:
        return HTMLResponse("<h1>⏰ Link expired!</h1>", status_code=410)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Generate Token</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
            }}
            .container {{
                background: white;
                border-radius: 20px;
                padding: 40px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                text-align: center;
            }}
            h1 {{ color: #333; margin-bottom: 20px; font-size: 28px; }}
            .info {{
                background: #f0f4ff;
                border-left: 4px solid #667eea;
                padding: 15px;
                margin: 20px 0;
                text-align: left;
                border-radius: 5px;
            }}
            .info p {{ margin: 8px 0; color: #555; }}
            .timer {{
                font-size: 48px;
                font-weight: bold;
                color: #667eea;
                margin: 30px 0;
            }}
            .btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 15px 40px;
                font-size: 18px;
                border-radius: 50px;
                cursor: pointer;
                width: 100%;
                margin-top: 20px;
            }}
            .btn:disabled {{ background: #ccc; cursor: not-allowed; }}
            .success {{ color: #10b981; font-size: 20px; margin-top: 20px; display: none; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Generate Token</h1>
            <div class="info">
                <p>📌 <strong>User ID:</strong> {uid}</p>
                <p>⏰ <strong>Validity:</strong> 12 hours</p>
                <p>✅ <strong>Status:</strong> Waiting...</p>
            </div>
            <div class="timer" id="timer">10</div>
            <button class="btn" id="btn" disabled>⏳ Wait 10s...</button>
            <div class="success" id="success">✅ Activated!<br><small>Redirecting...</small></div>
        </div>
        <script>
            let t = 10;
            const timer = document.getElementById('timer');
            const btn = document.getElementById('btn');
            const success = document.getElementById('success');
            
            const countdown = setInterval(() => {{
                t--;
                timer.textContent = t;
                btn.textContent = `⏳ Wait ${{t}}s...`;
                if (t <= 0) {{
                    clearInterval(countdown);
                    btn.disabled = false;
                    btn.textContent = '🔓 Activate Token';
                    timer.textContent = '✓';
                    timer.style.color = '#10b981';
                }}
            }}, 1000);
            
            btn.addEventListener('click', async () => {{
                btn.style.display = 'none';
                try {{
                    const res = await fetch('/activate?payload={payload}&sig={sig}');
                    const data = await res.json();
                    if (data.success) {{
                        success.style.display = 'block';
                        setTimeout(() => {{
                            window.location.href = 'https://t.me/freevideosherebot';
                        }}, 2000);
                    }} else {{
                        alert('❌ Failed: ' + data.message);
                        btn.style.display = 'block';
                        btn.disabled = false;
                    }}
                }} catch (e) {{
                    alert('❌ Error!');
                    btn.style.display = 'block';
                    btn.disabled = false;
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/activate")
async def activate_user_token(payload: str = None, sig: str = None):
    
    logger.info(f"=== ACTIVATION REQUEST ===")
    
    if not payload or not sig:
        return JSONResponse({"success": False, "message": "Missing params"}, status_code=400)
    
    if not verify_signature(payload, sig):
        return JSONResponse({"success": False, "message": "Invalid signature"}, status_code=400)
    
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, _ = decoded.split(":")
        uid = int(uid)
    except:
        return JSONResponse({"success": False, "message": "Invalid payload"}, status_code=400)
    
    try:
        await activate_token(uid, payload, sig)
        logger.info(f"✅ Token activated for user {uid}")
        return JSONResponse({"success": True, "message": "Activated!", "user_id": uid})
    except Exception as e:
        logger.error(f"Activation error: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
