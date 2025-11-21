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
    """Verify HMAC signature with your secret key"""
    try:
        # Using your key: d5e9792fe5f846376b6d373ede48e2c7
        expected_sig = hmac.new(
            HMAC_SECRET.encode(), 
            payload.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        logger.info(f"Signature Check:")
        logger.info(f"  Expected: {expected_sig}")
        logger.info(f"  Received: {sig}")
        logger.info(f"  Match: {hmac.compare_digest(expected_sig, sig)}")
        
        return hmac.compare_digest(expected_sig, sig)
    except Exception as e:
        logger.error(f"Signature error: {e}")
        return False

@router.get("/ad")
async def show_ad_page(payload: str = None, sig: str = None):
    
    if not payload or not sig:
        return HTMLResponse("<h1>❌ Missing parameters!</h1>", status_code=400)
    
    # Verify signature
    if not verify_signature(payload, sig):
        return HTMLResponse(
            "<h1>❌ Invalid or tampered link!</h1>"
            "<p>Signature verification failed.</p>"
            "<p>Please request a new token from the bot.</p>",
            status_code=400
        )
    
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, timestamp = decoded.split(":")
        uid = int(uid)
        timestamp = int(timestamp)
    except Exception as e:
        logger.error(f"Decode error: {e}")
        return HTMLResponse("<h1>❌ Invalid payload format!</h1>", status_code=400)
    
    # Check expiry (24 hours)
    current_time = int(time.time())
    if current_time - timestamp > 86400:
        return HTMLResponse("<h1>⏰ Link expired! Request new token.</h1>", status_code=410)
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Generate Access Token</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
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
            h1 {{ color: #333; margin-bottom: 20px; font-size: 26px; }}
            .info {{
                background: #f0f4ff;
                border-left: 4px solid #667eea;
                padding: 15px;
                margin: 20px 0;
                text-align: left;
                border-radius: 8px;
            }}
            .info p {{ margin: 8px 0; color: #555; font-size: 14px; }}
            .timer {{
                font-size: 56px;
                font-weight: bold;
                color: #667eea;
                margin: 30px 0;
            }}
            .btn {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 16px 40px;
                font-size: 18px;
                border-radius: 50px;
                cursor: pointer;
                width: 100%;
                margin-top: 20px;
                transition: all 0.3s;
            }}
            .btn:hover {{ transform: translateY(-2px); box-shadow: 0 10px 20px rgba(102,126,234,0.4); }}
            .btn:disabled {{ background: #ccc; cursor: not-allowed; transform: none; }}
            .success {{ 
                color: #10b981; 
                font-size: 20px; 
                margin-top: 20px; 
                display: none;
                animation: fadeIn 0.5s;
            }}
            @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Generate Access Token</h1>
            <div class="info">
                <p><strong>📌 User ID:</strong> {uid}</p>
                <p><strong>⏰ Token Validity:</strong> 12 hours</p>
                <p><strong>✅ Status:</strong> Ready to activate</p>
            </div>
            <div class="timer" id="timer">10</div>
            <button class="btn" id="activateBtn" disabled>⏳ Please wait 10 seconds...</button>
            <div class="success" id="successMsg">
                ✅ Token Activated Successfully!<br>
                <small>Redirecting to bot...</small>
            </div>
        </div>
        <script>
            let timeLeft = 10;
            const timerEl = document.getElementById('timer');
            const btn = document.getElementById('activateBtn');
            const success = document.getElementById('successMsg');
            
            const countdown = setInterval(() => {{
                timeLeft--;
                timerEl.textContent = timeLeft;
                btn.textContent = `⏳ Please wait ${{timeLeft}} seconds...`;
                
                if (timeLeft <= 0) {{
                    clearInterval(countdown);
                    btn.disabled = false;
                    btn.textContent = '🔓 Activate Token Now';
                    timerEl.textContent = '✓';
                    timerEl.style.color = '#10b981';
                }}
            }}, 1000);
            
            btn.addEventListener('click', async () => {{
                btn.style.display = 'none';
                
                try {{
                    const response = await fetch('/activate?payload={payload}&sig={sig}');
                    const data = await response.json();
                    
                    if (data.success) {{
                        success.style.display = 'block';
                        setTimeout(() => {{
                            window.location.href = 'https://t.me/freevideosherebot?start=verified';
                        }}, 2000);
                    }} else {{
                        alert('❌ Activation failed: ' + data.message);
                        btn.style.display = 'block';
                        btn.disabled = false;
                        btn.textContent = '🔓 Try Again';
                    }}
                }} catch (error) {{
                    console.error('Error:', error);
                    alert('❌ Network error! Please check your connection.');
                    btn.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = '🔓 Try Again';
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/activate")
async def activate_user_token(payload: str = None, sig: str = None):
    
    logger.info(f"=== TOKEN ACTIVATION REQUEST ===")
    
    if not payload or not sig:
        return JSONResponse({"success": False, "message": "Missing parameters"}, status_code=400)
    
    # Verify signature
    if not verify_signature(payload, sig):
        return JSONResponse({"success": False, "message": "Invalid signature"}, status_code=400)
    
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, _ = decoded.split(":")
        uid = int(uid)
        logger.info(f"Activating token for user: {uid}")
    except Exception as e:
        logger.error(f"Payload decode error: {e}")
        return JSONResponse({"success": False, "message": "Invalid payload"}, status_code=400)
    
    try:
        await activate_token(uid, payload, sig)
        logger.info(f"✅ Token activated successfully for user {uid}")
        return JSONResponse({
            "success": True, 
            "message": "Token activated successfully!",
            "user_id": uid
        })
    except Exception as e:
        logger.error(f"Token activation error: {e}")
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)
