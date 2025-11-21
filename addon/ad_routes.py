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
        # Log the secret being used (first 10 chars only for security)
        logger.info(f"🔑 Using HMAC_SECRET: {HMAC_SECRET[:10]}...")
        
        expected_sig = hmac.new(
            HMAC_SECRET.encode(), 
            payload.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        logger.info(f"📝 Payload: {payload}")
        logger.info(f"✅ Expected Signature: {expected_sig}")
        logger.info(f"📨 Received Signature: {sig}")
        logger.info(f"🔍 Match Result: {hmac.compare_digest(expected_sig, sig)}")
        
        return hmac.compare_digest(expected_sig, sig)
    except Exception as e:
        logger.error(f"❌ Signature error: {e}")
        return False

@router.get("/ad")
async def show_ad_page(payload: str = None, sig: str = None):
    
    logger.info("="*50)
    logger.info("🎯 AD PAGE REQUEST")
    logger.info("="*50)
    
    if not payload or not sig:
        logger.warning("⚠️ Missing parameters!")
        return HTMLResponse("<h1>❌ Missing parameters!</h1>", status_code=400)
    
    if not verify_signature(payload, sig):
        logger.error("❌ Signature verification FAILED!")
        return HTMLResponse(
            "<h1>❌ Invalid or tampered link!</h1>"
            "<p>Signature verification failed.</p>"
            "<p><strong>Solution:</strong> Request a NEW token from the bot.</p>"
            "<p>Old tokens won't work after key update.</p>",
            status_code=400
        )
    
    logger.info("✅ Signature verified successfully!")
    
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, timestamp = decoded.split(":")
        uid = int(uid)
        timestamp = int(timestamp)
        logger.info(f"👤 User ID: {uid}")
        logger.info(f"⏰ Timestamp: {timestamp}")
    except Exception as e:
        logger.error(f"❌ Decode error: {e}")
        return HTMLResponse("<h1>❌ Invalid payload!</h1>", status_code=400)
    
    current_time = int(time.time())
    if current_time - timestamp > 86400:
        logger.warning("⏰ Token expired!")
        return HTMLResponse("<h1>⏰ Link expired!</h1>", status_code=410)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token Generator</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea, #764ba2);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .box {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        h1 {{ color: #333; margin-bottom: 20px; }}
        .info {{
            background: #f0f4ff;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin: 20px 0;
            text-align: left;
            border-radius: 8px;
        }}
        .info p {{ margin: 8px 0; color: #555; }}
        .timer {{
            font-size: 56px;
            font-weight: bold;
            color: #667eea;
            margin: 30px 0;
        }}
        .btn {{
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 16px;
            font-size: 18px;
            border-radius: 50px;
            cursor: pointer;
            width: 100%;
            margin-top: 20px;
        }}
        .btn:disabled {{ background: #ccc; cursor: not-allowed; }}
        .ok {{ color: #10b981; font-size: 20px; margin-top: 20px; display: none; }}
    </style>
</head>
<body>
    <div class="box">
        <h1>🔐 Generate Token</h1>
        <div class="info">
            <p><strong>📌 User ID:</strong> {uid}</p>
            <p><strong>⏰ Valid:</strong> 12 hours</p>
            <p><strong>✅ Status:</strong> Ready</p>
        </div>
        <div class="timer" id="t">10</div>
        <button class="btn" id="b" disabled>⏳ Wait 10s...</button>
        <div class="ok" id="ok">✅ Token Activated!<br><small>Redirecting...</small></div>
    </div>
    <script>
        let n=10;
        const t=document.getElementById('t');
        const b=document.getElementById('b');
        const ok=document.getElementById('ok');
        
        const countdown=setInterval(()=>{{
            n--;
            t.textContent=n;
            b.textContent=`⏳ Wait ${{n}}s...`;
            if(n<=0){{
                clearInterval(countdown);
                b.disabled=false;
                b.textContent='🔓 Activate';
                t.textContent='✓';
                t.style.color='#10b981';
            }}
        }},1000);
        
        b.addEventListener('click',async()=>{{
            b.style.display='none';
            try{{
                const r=await fetch('/activate?payload={payload}&sig={sig}');
                const d=await r.json();
                if(d.success){{
                    ok.style.display='block';
                    setTimeout(()=>{{
                        window.location.href='https://t.me/freevideosherebot';
                    }},2000);
                }}else{{
                    alert('❌ '+d.message);
                    b.style.display='block';
                    b.disabled=false;
                }}
            }}catch(e){{
                alert('❌ Error!');
                b.style.display='block';
                b.disabled=false;
            }}
        }});
    </script>
</body>
</html>"""
    
    return HTMLResponse(content=html)

@router.get("/activate")
async def activate_user_token(payload: str = None, sig: str = None):
    
    logger.info("="*50)
    logger.info("🔓 ACTIVATION REQUEST")
    logger.info("="*50)
    
    if not payload or not sig:
        return JSONResponse({"success": False, "message": "Missing"})
    
    if not verify_signature(payload, sig):
        return JSONResponse({"success": False, "message": "Invalid signature"})
    
    try:
        decoded = base64.urlsafe_b64decode(payload.encode()).decode()
        uid, _ = decoded.split(":")
        uid = int(uid)
    except:
        return JSONResponse({"success": False, "message": "Invalid"})
    
    try:
        await activate_token(uid, payload, sig)
        logger.info(f"✅ Token activated for user {uid}")
        return JSONResponse({"success": True, "message": "Done!", "user_id": uid})
    except Exception as e:
        logger.error(f"❌ Activation error: {e}")
        return JSONResponse({"success": False, "message": str(e)})
