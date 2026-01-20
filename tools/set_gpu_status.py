
import sys
import redis

if len(sys.argv) < 2:
    print("Usage: python set_gpu_status.py [VERDE|RED|BUSY]")
    sys.exit(1)

status = sys.argv[1]
try:
    r = redis.Redis(host='localhost', port=6379, db=0)
    r.set("gpu_status", status)
    print(f"✅ GPU Status set to: {status}")
except Exception as e:
    print(f"❌ Error: {e}")
