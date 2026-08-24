import threading
import requests
from settings_manager import get_shop_settings

API_URL = "https://galaxycare-api.onrender.com/api"

def get_headers():
    """جلب رمز المحل تلقائياً من إعدادات البرنامج المحلية وإرساله في ترويسات الطلب"""
    try:
        cfg = get_shop_settings()
        shop_code = cfg.get("shop_code", "GALAXY-01")
    except Exception:
        shop_code = "GALAXY-01"
        
    return {
        "X-Shop-Code": shop_code,
        "Content-Type": "application/json"
    }

def _async_request(method, endpoint, data=None):
    """إرسال الطلب في Thread مستقل في الخلفية حتى لا يعطل واجهة برنامج الكمبيوتر"""
    def run():
        try:
            url = f"{API_URL}{endpoint}"
            headers = get_headers()
            if method == "POST":
                requests.post(url, json=data, headers=headers, timeout=6)
            elif method == "GET":
                requests.get(url, headers=headers, timeout=6)
        except Exception:
            # في حالة انقطاع الإنترنت يستمر برنامج الكمبيوتر بالعمل محلياً دون توقف
            pass

    threading.Thread(target=run, daemon=True).start()

def sync_new_repair(cust_name, phone, brand, model, problem, cost, part_cost, tech_id=None, notes="", inspection="", warranty=14):
    """مزامنة استلام جهاز جديد إلى السحابة مع ربطه بالمحل الحالي"""
    payload = {
        "customer_name": cust_name,
        "customer_phone": phone,
        "brand": brand,
        "model": model,
        "problem_desc": problem,
        "cost": float(cost or 0),
        "part_cost": float(part_cost or 0),
        "technician_id": tech_id,
        "notes": notes or "",
        "inspection": inspection or "",
        "warranty_days": int(warranty or 14)
    }
    _async_request("POST", "/repairs/add", payload)

def sync_deliver_repair(repair_id, final_cost, final_part_cost):
    """مزامنة تسليم الجهاز إلى السحابة وتوريده في خزينة المحل الحالي"""
    payload = {
        "repair_id": int(repair_id),
        "final_cost": float(final_cost or 0),
        "final_part_cost": float(final_part_cost or 0)
    }
    _async_request("POST", "/repairs/deliver", payload)