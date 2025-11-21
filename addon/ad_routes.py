import hmac
import hashlib
import base64
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from config import HMAC_SECRET
from db_init import activate_token

logger = logging.getLogger(__name__)

router = APIRouter()

def verify_signature(payload: str, sig: str) -> bool:
    """Verify HMAC signature"""
    try:
        expected_sig = hmac.new(
            HMAC_SECRET.encode(), 
            payload.encode(), 
            hashlib.sha256
        ).hexdigest()
        result = hmac.compare_digest(expected_sig, sig)
        logger.info(f"Signature verification: {result}")
        logger.info(f"Expected: {expected_sig}")
        logger.info(f"Received: {sig}")
        return result
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False

@router.get("/ad")
async def show_ad_page(payload: str = None, sig: str = None):
    """Show ad page with verification"""
    
    logger.info(f"Ad page request - Payload: {payload}, Sig: {sig}")
    
    # Check if parameters are provided
    if not payload or not sig:
        return HTMLResponse(
            content="<h1>❌ Missing parameters!</h1>",
            status_code=400
        )
    
    # Verify signature
    if not verify_signature(payload, sig):
        return HTMLResponse(
            content="<h1>❌ Invalid or tampered link!</h1><p>Please request a new token from the bot.</p>",
            status_code=400
        )
    
    # Decode payload
    try:
        decoded_payload = base64.urlsafe_b64decode(payload.encode()).decode()
        logger.info(f"Decoded payload: {decoded_payload}")
        uid, timestamp = decoded_payload.split(":")
        uid = int(uid)
        timestamp = int(timestamp)
    except Exception as e:
        logger.error(f"Payload decode error: {e}")
        return HTMLResponse(
            content="<h1>❌ Invalid payload format!</h1>",
            status_code=400
        )
    
    # Check if link expired (24 hours)
    current_time = int(time.time())
    if current_time - timestamp > 86400:  # 24 hours
        return HTMLResponse(
            content="<h1>⏰ Link expired!</h1><p>Please request a new token from the bot.</p>",
            status_code=410
        )
    
    # Generate ad HTML page
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Generate Token - File Sharing Bot</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
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
            h1 {{
                color: #333;
                margin-bottom: 20px;
                font-size: 28px;
            }}
            .info {{
                background: #f0f4ff;
                border-left: 4px solid #667eea;
                padding: 15px;
                margin: 20px 0;
                text-align: left;
                border-radius: 5px;
            }}
            .info p {{
                margin: 8px 0;
                color: #555;
                line-height: 1.6;
            }}
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
                transition: transform 0.2s, box-shadow 0.2s;
                margin-top: 20px;
                width: 100%;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
            }}
            .btn:disabled {{
                background: #ccc;
                cursor: not-allowed;
                transform: none;
            }}
            .success {{
                color: #10b981;
                font-size: 20px;
                margin-top: 20px;
                display: none;
            }}
            .loading {{
                display: none;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔐 Generate Access Token</h1>
            
            <div class="info">
                <p>📌 <strong>User ID:</strong> {uid}</p>
                <p>⏰ <strong>Token Validity:</strong> 12 hours</p>
                <p>✅ <strong>Status:</strong> Waiting for verification...</p>
            </div>
            
            <div class="timer" id="timer">10</div>
            
            <button class="btn" id="activateBtn" disabled>
                ⏳ Wait 10 seconds...
            </button>
            
            <div class="loading" id="loading">
                <p>⏳ Activating token...</p>
            </div>
            
            <div class="success" id="successMsg">
                ✅ Token Activated Successfully!<br>
                <small>Redirecting to bot...</small>
            </div>
        </div>

        <script>
            let timeLeft = 10;
            const timerElement = document.getElementById('timer');
            const activateBtn = document.getElementById('activateBtn');
            const successMsg = document.getElementById('successMsg');
            const loadingMsg = document.getElementById('loading');
            
            // Countdown timer
            const countdown = setInterval(() => {{
                timeLeft--;
                timerElement.textContent = timeLeft;
                activateBtn.textContent = `⏳ Wait ${{timeLeft}} seconds...`;
                
                if (timeLeft <= 0) {{
                    clearInterval(countdown);
                    activateBtn.disabled = false;
                    activateBtn.textContent = '🔓 Activate Token Now';
                    timerElement.textContent = '✓';
                    timerElement.style.color = '#10b981';
                }}
            }}, 1000);
            
            // Activate token
            activateBtn.addEventListener('click', async () => {{
                activateBtn.style.display = 'none';
                loadingMsg.style.display = 'block';
                
                try {{
                    const response = await fetch('/activate?payload={payload}&sig={sig}');
                    const data = await response.json();
                    
                    console.log('Activation response:', data);
                    
                    if (data.success) {{
                        loadingMsg.style.display = 'none';
                        successMsg.style.display = 'block';
                        
                        // Redirect to Telegram after 2 seconds
                        setTimeout(() => {{
                            window.location.href = 'https://t.me/freevideosherebot?start=verified';
                        }}, 2000);
                    }} else {{
                        loadingMsg.style.display = 'none';
                        alert('❌ Activation failed: ' + data.message);
                        activateBtn.style.display = 'block';
                        activateBtn.textContent = '🔓 Try Again';
                        activateBtn.disabled = false;
                    }}
                }} catch (error) {{
                    console.error('Activation error:', error);
                    loadingMsg.style.display = 'none';
                    alert('❌ Network error! Please check your connection.');
                    activateBtn.style.display = 'block';
                    activateBtn.textContent = '🔓 Try Again';
                    activateBtn.disabled = false;
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/activate")
async def activate_user_token(payload: str = None, sig: str = None):
    """Activate token after ad verification"""
    
    logger.info(f"Activation request - Payload: {payload}, Sig: {sig}")
    
    # Check parameters
    if not payload or not sig:
        return JSONResponse({
            "success": False, 
            "message": "Missing parameters"
        }, status_code=400)
    
    # Verify signature
    if not verify_signature(payload, sig):
        return JSONResponse({
            "success": False, 
            "message": "Invalid signature"
        }, status_code=400)
    
    # Decode payload
    try:
        decoded_payload = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, timestamp = decoded_payload.split(":")
        uid = int(uid)
        logger.info(f"Activating token for user: {uid}")
    except Exception as e:
        logger.error(f"Payload decode error: {e}")
        return JSONResponse({
            "success": False, 
            "message": "Invalid payload"
        }, status_code=400)
    
    # Activate token in database
    try:
        await activate_token(uid, payload, sig)
        logger.info(f"Token activated successfully for user {uid}")
        return JSONResponse({
            "success": True, 
            "message": "Token activated successfully!",
            "user_id": uid
        })
    except Exception as e:
        logger.error(f"Token activation error: {e}")
        return JSONResponse({
            "success": False, 
            "message": str(e)
        }, status_code=500)
