
import sys
import json
from tools.automation.remote_exec import get_target_ip

# Proviamo a cercare l'IP della macchina 'docker-host' (che è nel tuo state.json)
try:
    ip = get_target_ip('docker-host')
    print(f'SUCCESS: IP found -> {ip}')
except Exception as e:
    print(f'ERROR: {e}')

