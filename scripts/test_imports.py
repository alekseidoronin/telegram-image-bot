import sys
try:
    import handlers
    print("Handlers imported successfully")
except Exception as e:
    print(f"Handlers import failed: {e}")
    sys.exit(1)

try:
    import bot
    print("Bot imported successfully")
except Exception as e:
    print(f"Bot import failed: {e}")
    sys.exit(1)
