# Testing Guide - Soniox STT + OpenAI + Cartesia TTS

## ✅ Configuration Checklist

### 1. Environment Variables (.env file)
Your `.env` file needs:
```env
OPENAI_API_KEY=your_openai_key_here  # ⚠️ ADD THIS!
CARTESIA_API_KEY=sk_car_hPEQcGysNLC3nQkxRcquim
SONIOX_API_KEY=87a17b93a7707b5ed1ddf2727c66066783698276afcd4c717fde0c5e30a8e309
WEBSOCKET_SERVER=fast_api
```

**⚠️ IMPORTANT:** Replace `your_openai_key_here` with your actual OpenAI API key!

---

## 🚀 Step-by-Step Testing

### Step 1: Install Dependencies
```powershell
cd Task-1\websocket\server
pip install -r requirements.txt
```

### Step 2: Start the Server
```powershell
cd Task-1\websocket\server
python server.py
```

**Expected Output:**
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 3: Start the Client (in a NEW terminal)
```powershell
cd Task-1\websocket\client
npm install
npm run dev
```

**Expected Output:**
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:5173/
```

### Step 4: Open Browser
1. Open **http://localhost:5173/**
2. Open **Developer Tools** (F12)
3. Go to **Console** tab

### Step 5: Test Connection
1. Click **"Connect"** button
2. **Allow microphone access** when prompted

**Expected Console Output:**
```
WebsocketClientApp
Initializing devices...
Connecting to bot...
Status: Connected
Bot ready: {...}
```

**Expected Server Output:**
```
Pipecat Client connected
🎤 [Soniox STT] Initialized successfully
🔊 [Cartesia TTS] Initialized successfully
Pipecat client ready.
```

### Step 6: Test Speech
1. **Speak into your microphone**: "Hello, how are you?"
2. Watch both browser console and server console

**Expected Browser Console:**
```
User: Hello, how are you?
Bot: I'm doing great, thanks for asking! How can I help you today?
```

**Expected Server Console:**
```
🎤 [Soniox STT] Audio received: 3200 bytes
✨ [Soniox STT] Transcription: "Hello, how are you?"
🤖 [OpenAI] Generating response...
🔊 [Cartesia TTS] Generating audio for: "I'm doing great, thanks for asking!..."
🎵 [Cartesia TTS] Streaming audio chunk: 1024 bytes
```

---

## 🔍 Debugging

### Issue: No Server Console Output When Speaking

**Check 1:** Verify microphone is working
- Browser should show microphone icon in address bar
- Check browser console for "getUserMedia" errors

**Check 2:** Check Network tab in browser
- Should see WebSocket connection to `ws://localhost:8000/ws`
- Status should be "101 Switching Protocols"
- Messages should be flowing (green arrows)

**Check 3:** Server logs
```powershell
# Restart server with verbose logging
python server.py
```

### Issue: "WebSocket connection failed"

**Solution:** Verify server is running on port 8000
```powershell
netstat -ano | findstr :8000
```

### Issue: "OPENAI_API_KEY not set"

**Solution:** Add your OpenAI API key to `.env` file:
```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx
```

### Issue: Audio not playing

**Check 1:** Browser audio element
- Open Console: `document.getElementById('bot-audio')`
- Should show `<audio>` element with srcObject

**Check 2:** Check browser audio permissions
- Settings → Privacy → Microphone/Speaker permissions

---

## 📊 Audio Flow Diagram

```
User speaks
    ↓
Browser captures microphone → WebSocket
    ↓
Server receives audio (16kHz PCM)
    ↓
🎤 Soniox STT → Text transcription
    ↓
🤖 OpenAI LLM → Text response
    ↓
🔊 Cartesia TTS → Audio speech
    ↓
Server sends audio → WebSocket
    ↓
Browser plays audio → Speaker
```

---

## 🧪 Quick Test Commands

### Test 1: Check if server is responding
```powershell
curl http://localhost:8000/connect
# Expected: {"ws_url":"ws://localhost:8000/ws"}
```

### Test 2: Check environment variables
```powershell
cd Task-1\websocket\server
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('OpenAI:', 'SET' if os.getenv('OPENAI_API_KEY') else 'MISSING'); print('Soniox:', 'SET' if os.getenv('SONIOX_API_KEY') else 'MISSING'); print('Cartesia:', 'SET' if os.getenv('CARTESIA_API_KEY') else 'MISSING')"
```

### Test 3: Verify imports
```powershell
cd Task-1\websocket\server
python -c "from processors import SonioxSTTService, CartesiaTTSService; print('✅ Processors imported successfully')"
```

---

## 📝 Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `OPENAI_API_KEY environment variable is not set` | Missing API key | Add to `.env` file |
| `WebSocket connection to 'ws://localhost:8000/ws' failed` | Server not running | Start server with `python server.py` |
| `Module 'processors' has no attribute 'SonioxSTTService'` | Import error | Check `processors/__init__.py` |
| `Connection refused` | Port already in use | Kill process on port 8000 |
| No audio output | Browser audio blocked | Check browser permissions |

---

## 🎯 Success Indicators

✅ Server starts without errors  
✅ Client connects successfully  
✅ Browser console shows "Bot ready"  
✅ Speaking triggers transcription in console  
✅ Server shows 🎤 emoji logs  
✅ Bot responds with audio  
✅ Server shows 🔊 emoji logs  

---

## Need Help?

1. Check `.env` file has all API keys
2. Verify server is running on http://localhost:8000
3. Check browser console for errors
4. Check server console for error messages
5. Ensure microphone permissions are granted
