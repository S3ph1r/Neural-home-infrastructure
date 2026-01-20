
import time
import threading
import sys
# Aggiungiamo il percorso corrente per sicurezza
sys.path.append('.')
from tools.core.lock_manager import acquire_lock

def finta_ai_1():
    print('🔴 AI 1: Provo a prendere il lock...')
    # Usiamo la funzione senza parametri extra
    with acquire_lock():
        print('🟢 AI 1: PRESO! Sto scrivendo state.json...')
        time.sleep(3) # Simula un lavoro lungo
        print('⚪ AI 1: Finito, rilascio.')

def finta_ai_2():
    time.sleep(0.5) # Parte poco dopo
    print('🔴 AI 2: Provo a prendere il lock...')
    with acquire_lock():
        print('🟢 AI 2: PRESO! (Se leggi questo subito, il test è FALLITO)')
        print('⚪ AI 2: Rilascio.')

t1 = threading.Thread(target=finta_ai_1)
t2 = threading.Thread(target=finta_ai_2)

t1.start()
t2.start()
t1.join()
t2.join()

