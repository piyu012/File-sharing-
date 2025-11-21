import hmac
import hashlib
import base64
import time
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from config import HMAC_SECRET
from db_init import activate_token, has_valid_token

router = APIRouter()

def verify_signature(payload: str, sig: str) -> bool:
    """Verify HMAC signature"""
    expected_sig = hmac.new(
        HMAC_SECRET.encode(), 
        payload.encode(), 
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, sig)

@router.get("/ad")
async def show_ad_page(payload: str, sig: str):
    """Show ad page with verification"""
    
    # Verify signature
    if not verify_signature(payload, sig):
        return HTMLResponse(
            content="<h1>❌ Invalid or tampered link!</h1>",
            status_code=400
        )
    
    # Decode payload
    try:
        decoded_payload = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, timestamp = decoded_payload.split(":")
        uid = int(uid)
        timestamp = int(timestamp)
    except:
        return HTMLResponse(
            content="<h1>❌ Invalid payload format!</h1>",
            status_code=400
        )
    
    # Check if link expired (24 hours)
    current_time = int(time.time())
    if current_time - timestamp > 86400:  # 24 hours
        return HTMLResponse(
            content="<h1>⏰ Link expired! Please request a new token.</h1>",
            status_code=410
        )
    
    # Generate ad HTML page
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Generate Token</title>
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
                Generating Token...
            </button>
            
            <div class="success" id="successMsg">
                ✅ Token Activated Successfully!<br>
                You can now access files.
            </div>
        </div>

        <script>
            let timeLeft = 10;
            const timerElement = document.getElementById('timer');
            const activateBtn = document.getElementById('activateBtn');
            const successMsg = document.getElementById('successMsg');
            
            // Countdown timer
            const countdown = setInterval(() => {{
                timeLeft--;
                timerElement.textContent = timeLeft;
                
                if (timeLeft <= 0) {{
                    clearInterval(countdown);
                    activateBtn.disabled = false;
                    activateBtn.textContent = '🔓 Activate Token';
                    timerElement.textContent = '✓';
                    timerElement.style.color = '#10b981';
                }}
            }}, 1000);
            
            // Activate token
            activateBtn.addEventListener('click', async () => {{
                activateBtn.disabled = true;
                activateBtn.textContent = 'Activating...';
                
                try {{
                    const response = await fetch('/activate?payload={payload}&sig={sig}');
                    const data = await response.json();
                    
                    if (data.success) {{
                        successMsg.style.display = 'block';
                        activateBtn.style.display = 'none';
                        
                        // Redirect to Telegram after 2 seconds
                        setTimeout(() => {{
                            window.location.href = 'https://t.me/freevideosherebot';
                        }}, 2000);
                    }} else {{
                        alert('❌ Activation failed: ' + data.message);
                        activateBtn.disabled = false;
                        activateBtn.textContent = '🔓 Activate Token';
                    }}
                }} catch (error) {{
                    alert('❌ Network error! Please try again.');
                    activateBtn.disabled = false;
                    activateBtn.textContent = '🔓 Activate Token';
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)

@router.get("/activate")
async def activate_user_token(payload: str, sig: str):
    """Activate token after ad verification"""
    
    # Verify signature
    if not verify_signature(payload, sig):
        return {"success": False, "message": "Invalid signature"}
    
    # Decode payload
    try:
        decoded_payload = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, timestamp = decoded_payload.split(":")
        uid = int(uid)
    except:
        return {"success": False, "message": "Invalid payload"}
    
    # Activate token in database
    try:
        await activate_token(uid, payload, sig)
        return {
            "success": True, 
            "message": "Token activated successfully!",
            "user_id": uid
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
