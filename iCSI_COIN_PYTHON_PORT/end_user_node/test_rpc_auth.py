import requests
import json
import time

PORTS = [9340, 9336]
RPC_URL = None
CONFIG_URL = None

PORTS = [9340, 9336]
CONFIG_URL = "http://127.0.0.1:9340/api/rpc/config"
RPC_URL = "http://127.0.0.1:9336/"

def check_connection():
    # Check Config (Web)
    try:
        requests.get(CONFIG_URL, timeout=2)
        print(f"Connected to Web Config at {CONFIG_URL}")
    except:
        print(f"ERROR: Cannot connect to Web Config at {CONFIG_URL}")
        return False
        
    # Check RPC
    try:
        # Check if RPC server is up (getinfo doesn't require auth on permissive default?)
        # Or just checking socket open?
        # We'll just assume if Web is up, RPC is likely up, but let's check config endpoint on RPC too if previously it was there?
        # RPC server also has /api/rpc/config.
        # Let's just try to hit RPC config endpoint to verify it's up.
        requests.get("http://127.0.0.1:9336/api/rpc/config", timeout=2)
        print(f"Connected to RPC Server at {RPC_URL}")
    except:
        print(f"ERROR: Cannot connect to RPC Server at {RPC_URL}")
        return False
        
    return True

def get_config():
    try:
        resp = requests.get(CONFIG_URL, timeout=2)
        return resp.json()
    except Exception as e:
        print(f"GET Config Failed: {e}")
        print(f"Status: {resp.status_code}")
        print(f"Text: {resp.text}")
        raise

def set_config(user, password, enforce):
    try:
        resp = requests.post(CONFIG_URL, json={"user": user, "password": password, "enforce_auth": enforce}, timeout=2)
        if resp.status_code != 200:
             print(f"SET Config Failed: Status {resp.status_code}")
             print(f"Text: {resp.text}")
    except Exception as e:
        print(f"SET Config Exception: {e}")
        raise

def rpc_call(user=None, password=None):
    auth = (user, password) if user else None
    try:
        resp = requests.post(RPC_URL, json={"jsonrpc": "2.0", "method": "getinfo", "id": 1}, auth=auth, timeout=2)
        return resp.status_code
    except Exception as e:
        return str(e)

print("Starting Verification...")

if not check_connection():
    print("ERROR: Could not connect to RPC Server on ports 9340 or 9336. Is the node running?")
    exit(1)

try:
    # 1. Reset Config
    print("1. Resetting Config to Permissive...")
    set_config("user", "pass", False)
    config = get_config()
    if config['enforce_auth'] != False:
        print(f"FAIL: enforce_auth is {config['enforce_auth']}, expected False")
        exit(1)
        
    status = rpc_call()
    if status != 200:
        print(f"FAIL: Permissive mode rejected unauth request (Status: {status})")
        exit(1)
    print("   PASS: Permissive mode allows unauth request.")

    # 2. Enforce Auth
    print("2. Enforcing Auth...")
    set_config("user", "pass", True)
    config = get_config()
    if config['enforce_auth'] != True:
        print(f"FAIL: enforce_auth is {config['enforce_auth']}, expected True")
        exit(1)

    # 3. Test Unauth Rejection
    print("3. Testing Unauth Rejection...")
    status = rpc_call()
    if status != 401:
        print(f"FAIL: Enforced mode did not reject unauth request (Status: {status})")
        exit(1)
    print(f"   PASS: Enforced mode rejected unauth request (Status: {status}).")

    # 4. Test Auth Acceptance
    print("4. Testing Auth Acceptance...")
    status = rpc_call("user", "pass")
    if status != 200:
        print(f"FAIL: Enforced mode rejected valid auth (Status: {status})")
        exit(1)
    print(f"   PASS: Enforced mode accepted auth request (Status: {status}).")

    # 5. Test Invalid Auth
    print("5. Testing Invalid Auth...")
    status = rpc_call("user", "wrongpass")
    if status != 401:
        print(f"FAIL: Enforced mode accepted invalid auth (Status: {status})")
        exit(1)
    print(f"   PASS: Enforced mode rejected invalid auth (Status: {status}).")

    # 6. Disable Enforcement
    print("6. Disabling Enforcement...")
    set_config("user", "pass", False)
    status = rpc_call()
    if status != 200:
        print(f"FAIL: Disabling enforcement did not restore access (Status: {status})")
        exit(1)
    print("   PASS: Disabling enforcement restores access.")

    print("\nVerification Complete: ALL PASS")

except Exception as e:
    print(f"\nERROR during verification: {e}")
    exit(1)
