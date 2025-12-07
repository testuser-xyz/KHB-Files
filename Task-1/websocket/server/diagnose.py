"""
Quick diagnostic script to verify configuration before running the bot.
Run this to check if everything is set up correctly.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add server directory to path
server_dir = Path(__file__).parent
sys.path.insert(0, str(server_dir))

# Load environment variables
env_file = server_dir / ".env"
load_dotenv(env_file, override=True)

print("=" * 60)
print("🔍 DIAGNOSTIC CHECK - Soniox + OpenAI + Cartesia Setup")
print("=" * 60)
print()

# Check 1: Environment file
print("📁 Step 1: Checking .env file...")
if env_file.exists():
    print(f"   ✅ Found: {env_file}")
else:
    print(f"   ❌ Missing: {env_file}")
    sys.exit(1)

# Check 2: API Keys
print("\n🔑 Step 2: Checking API keys...")
issues = []

openai_key = os.getenv("OPENAI_API_KEY")
if not openai_key:
    print("   ❌ OPENAI_API_KEY: NOT SET")
    issues.append("Add OPENAI_API_KEY to .env file")
elif openai_key == "your_openai_key_here":
    print("   ⚠️  OPENAI_API_KEY: PLACEHOLDER (replace with real key)")
    issues.append("Replace 'your_openai_key_here' with actual OpenAI API key")
else:
    print(f"   ✅ OPENAI_API_KEY: Set ({openai_key[:8]}...{openai_key[-4:]})")

soniox_key = os.getenv("SONIOX_API_KEY")
if not soniox_key:
    print("   ❌ SONIOX_API_KEY: NOT SET")
    issues.append("Add SONIOX_API_KEY to .env file")
else:
    print(f"   ✅ SONIOX_API_KEY: Set ({soniox_key[:8]}...{soniox_key[-4:]})")

cartesia_key = os.getenv("CARTESIA_API_KEY")
if not cartesia_key:
    print("   ❌ CARTESIA_API_KEY: NOT SET")
    issues.append("Add CARTESIA_API_KEY to .env file")
else:
    print(f"   ✅ CARTESIA_API_KEY: Set ({cartesia_key[:8]}...{cartesia_key[-4:]})")

# Check 3: Required modules
print("\n📦 Step 3: Checking Python packages...")
required_packages = [
    ("pipecat", "pipecat-ai"),
    ("cartesia", "cartesia"),
    ("websockets", "websockets"),
    ("openai", "openai"),
]

missing_packages = []
for module_name, package_name in required_packages:
    try:
        __import__(module_name)
        print(f"   ✅ {package_name}: Installed")
    except ImportError:
        print(f"   ❌ {package_name}: NOT INSTALLED")
        missing_packages.append(package_name)

if missing_packages:
    issues.append(f"Install missing packages: pip install {' '.join(missing_packages)}")

# Check 4: Processor files
print("\n🔧 Step 4: Checking processor files...")
processors_dir = server_dir / "processors"
required_files = [
    "__init__.py",
    "soniox_stt.py",
    "cartesia_tts.py",
]

for filename in required_files:
    file_path = processors_dir / filename
    if file_path.exists():
        print(f"   ✅ {filename}: Found")
    else:
        print(f"   ❌ {filename}: MISSING")
        issues.append(f"Create missing file: {file_path}")

# Check 5: Import processors
print("\n🔍 Step 5: Testing imports...")
try:
    from processors import SonioxSTTService, CartesiaTTSService
    print("   ✅ SonioxSTTService: Importable")
    print("   ✅ CartesiaTTSService: Importable")
except ImportError as e:
    print(f"   ❌ Import error: {e}")
    issues.append("Fix processor imports")

# Check 6: Server mode
print("\n⚙️  Step 6: Checking configuration...")
server_mode = os.getenv("WEBSOCKET_SERVER", "fast_api")
print(f"   ℹ️  Server mode: {server_mode}")

# Summary
print("\n" + "=" * 60)
if issues:
    print("❌ ISSUES FOUND:")
    print("=" * 60)
    for i, issue in enumerate(issues, 1):
        print(f"{i}. {issue}")
    print("\n⚠️  Fix these issues before starting the server!")
    sys.exit(1)
else:
    print("✅ ALL CHECKS PASSED!")
    print("=" * 60)
    print("\n🚀 Ready to start the server:")
    print("   python server.py")
    print("\nExpected flow:")
    print("   🎤 User speaks → Soniox STT")
    print("   🤖 Soniox text → OpenAI LLM")
    print("   🔊 OpenAI response → Cartesia TTS")
    print("   🎵 Cartesia audio → User hears")
    print()
