import os
import json
import urllib.request
import urllib.error
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from supabase import create_client, Client

# إعدادات قاعدة البيانات السحابية
SUPABASE_URL = "https://jolhhglgomnocrglmxco.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpvbGhoZ2xnb21ub2NyZ2xteGNvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc1MjMzMTgsImV4cCI6MjEwMzA5OTMxOH0.2jJLUh-enCuIrN25lQc2o1sgnh7JyzdtaTpiwnh0SF8"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# مفتاح OpenAI من متغيرات البيئة في Render
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

SYSTEM_PROMPT = """
You are an intelligent database assistant for 'Galaxy Care Manager' (a mobile phone repair & POS desktop system).
Your task is to convert the user's natural language question into a single, safe, read-only SQL query for SQLite, OR answer general advice directly.

Database Schema:
1. employees (id, name, phone, role, salary_type, commission_rate, fixed_salary, created_at)
2. customers (id, name, phone, created_at)
3. repair_orders (id, customer_id, technician_id, brand, model, problem_desc, cost, part_cost, status, notes, inspection, warranty_days, received_at, delivered_at)
4. inventory (id, item_name, category, cost_price, sell_price, quantity, created_at)
5. treasury (id, trans_type, category, amount, description, repair_id, employee_id, created_at)
6. accounts (id, name, account_type, phone, credit_limit, opening_balance)
7. attendance (id, employee_id, att_date, check_in, check_out, total_hours, status)

CRITICAL RULES:
- ONLY generate SELECT queries. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, or PRAGMA.
- Always output strict JSON with two keys:
  "sql": "SELECT ... " (or null if general advice)
  "explanation": "Short Arabic sentence explaining what you calculated or summarized."
"""

# 1. إنشاء التطبيق
app = FastAPI(
    title="Galaxy Care Multi-Tenant Cloud API",
    description="سيرفر الربط السحابي وإدارة محلات الصيانة المتعددة مع مساعد BOGHA AI",
    version="2.3.0"
)

# 2. إعدادات CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== Dependency لعزل بيانات كل محل ====================
def get_current_shop(x_shop_code: Optional[str] = Header(default="GALAXY-01", alias="X-Shop-Code")) -> dict:
    """التحقق من هوية المحل وجلب معرّف المحل shop_id لضمان عزل البيانات"""
    res = supabase.table("shops").select("id, shop_code, shop_name, is_active").eq("shop_code", x_shop_code).execute()
    if not res.data or not res.data[0].get("is_active", True):
        raise HTTPException(status_code=403, detail="رمز المحل غير موجود أو الحساب معطل")
    return res.data[0]

# ==================== نماذج البيانات ====================
class LoginRequest(BaseModel):
    username: str
    password: str

class RepairCreateRequest(BaseModel):
    customer_name: str
    customer_phone: str
    brand: str
    model: str
    problem_desc: str
    cost: float = 0.0
    part_cost: float = 0.0
    technician_id: Optional[int] = None
    notes: Optional[str] = ""
    inspection: Optional[str] = ""
    warranty_days: Optional[int] = 14

class RepairDeliverRequest(BaseModel):
    repair_id: int
    final_cost: float
    final_part_cost: float

class AIQueryRequest(BaseModel):
    machine_id: str
    prompt: str

# ==================== المسارات والروابط ====================

@app.get("/")
def home():
    return {"status": "online", "mode": "multi-tenant", "ai_engine": "OpenAI", "message": "Galaxy Care Cloud API is running"}

# فتح لوحة الموبايل مباشرة من المتصفح
@app.get("/mobile", response_class=FileResponse)
def serve_mobile_dashboard():
    return "dashboard.html"

# فتح صفحة التتبع للعميل
@app.get("/track", response_class=FileResponse)
def serve_track_page():
    return "track.html"

# مسار مساعد الذكاء الاصطناعي المركزي عبر OpenAI
@app.post("/api/ai_query")
async def handle_ai_query(req_data: AIQueryRequest):
    user_prompt = req_data.prompt.strip()
    if not user_prompt:
        return {"success": False, "error": "السؤال فارغ"}

    api_key = OPENAI_API_KEY.strip()
    if not api_key:
        return {"success": False, "error": "مفتاح OpenAI API غير مضاف في متغيرات السيرفر"}

    try:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=20) as response:
            res_data = json.loads(response.read().decode('utf-8'))

        raw_text = res_data['choices'][0]['message']['content']
        parsed = json.loads(raw_text)

        return {
            "success": True,
            "sql": parsed.get("sql"),
            "explanation": parsed.get("explanation", "إليك النتيجة المطلوبة:")
        }
    except urllib.error.HTTPError as he:
        err_body = he.read().decode('utf-8', errors='ignore')
        return {"success": False, "error": f"خطأ OpenAI ({he.code}): {err_body}"}
    except Exception as e:
        return {"success": False, "error": f"تعذر استجابة الذكاء الاصطناعي: {str(e)}"}

# مسار إحصائيات الخزينة والأرباح اليومية للمحل الحالي
@app.get("/api/stats/today")
def get_today_stats(shop: dict = Depends(get_current_shop)):
    shop_id = shop["id"]
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    treasury_res = supabase.table("treasury").select("trans_type, amount").eq("shop_id", shop_id).gte("created_at", f"{today_str}T00:00:00").execute()
    
    today_income = sum(t["amount"] for t in treasury_res.data if t.get("trans_type") == "وارد")
    today_expense = sum(t["amount"] for t in treasury_res.data if t.get("trans_type") == "صادر")
    
    repairs_res = supabase.table("repair_orders").select("cost, part_cost").eq("shop_id", shop_id).eq("status", "تم التسليم").gte("delivered_at", f"{today_str}T00:00:00").execute()
    
    repair_revenue = sum(r.get("cost", 0) for r in repairs_res.data)
    repair_parts = sum(r.get("part_cost", 0) for r in repairs_res.data)
    repair_profit = repair_revenue - repair_parts

    return {
        "shop_name": shop["shop_name"],
        "today_income": today_income,
        "today_expense": today_expense,
        "repair_profit": repair_profit,
        "delivered_today_count": len(repairs_res.data)
    }

@app.post("/api/auth/login")
def login(data: LoginRequest):
    res = supabase.table("app_users").select("id, username, role").eq("username", data.username).eq("password", data.password).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    return {"status": "success", "user": res.data[0]}

# جلب أذونات المحل الحالي فقط
@app.get("/api/repairs")
def get_repairs(shop: dict = Depends(get_current_shop)):
    shop_id = shop["id"]
    res = supabase.table("repair_orders").select(
        "id, brand, model, problem_desc, cost, part_cost, status, notes, inspection, warranty_days, received_at, customers(name, phone)"
    ).eq("shop_id", shop_id).order("id", desc=True).execute()
    return res.data

# إضافة جهاز وربطه بالمحل الحالي
@app.post("/api/repairs/add")
def add_repair(data: RepairCreateRequest, shop: dict = Depends(get_current_shop)):
    shop_id = shop["id"]
    
    cust_res = supabase.table("customers").select("id").eq("shop_id", shop_id).eq("phone", data.customer_phone).execute()
    if cust_res.data:
        customer_id = cust_res.data[0]["id"]
    else:
        new_cust = supabase.table("customers").insert({
            "shop_id": shop_id,
            "name": data.customer_name, 
            "phone": data.customer_phone
        }).execute()
        customer_id = new_cust.data[0]["id"]

    order_data = {
        "shop_id": shop_id,
        "customer_id": customer_id,
        "technician_id": data.technician_id,
        "brand": data.brand,
        "model": data.model,
        "problem_desc": data.problem_desc,
        "cost": data.cost,
        "part_cost": data.part_cost,
        "notes": data.notes,
        "inspection": data.inspection,
        "warranty_days": data.warranty_days,
        "status": "تم الاستلام"
    }
    new_order = supabase.table("repair_orders").insert(order_data).execute()
    return {"status": "success", "order": new_order.data[0]}

# تسليم الجهاز وتوريد المبلغ في خزينة المحل
@app.post("/api/repairs/deliver")
def deliver_repair(data: RepairDeliverRequest, shop: dict = Depends(get_current_shop)):
    shop_id = shop["id"]
    order_res = supabase.table("repair_orders").select("*, customers(name)").eq("shop_id", shop_id).eq("id", data.repair_id).execute()
    if not order_res.data:
        raise HTTPException(status_code=404, detail="إذن الصيانة غير موجود")
    
    order = order_res.data[0]
    cust_name = order["customers"]["name"] if order.get("customers") else "عميل"
    device_info = f"{order['brand']} {order['model']}"

    supabase.table("repair_orders").update({
        "status": "تم التسليم",
        "cost": data.final_cost,
        "part_cost": data.final_part_cost,
        "delivered_at": datetime.utcnow().isoformat()
    }).eq("shop_id", shop_id).eq("id", data.repair_id).execute()

    supabase.table("treasury").insert({
        "shop_id": shop_id,
        "trans_type": "وارد",
        "category": "صيانة",
        "amount": data.final_cost,
        "description": f"تحصيل صيانة إذن #{data.repair_id} ({device_info} - {cust_name})",
        "repair_id": data.repair_id
    }).execute()

    return {"status": "success", "message": "تم تسليم الجهاز بنجاح"}

# مسار تتبع العميل المطور والمرن
@app.get("/api/track")
def track_repair(q: str, shop: Optional[str] = None):
    clean_q = q.strip()
    
    if clean_q.isdigit() and len(clean_q) <= 6:
        query = supabase.table("repair_orders").select(
            "id, brand, model, problem_desc, status, cost, inspection, warranty_days"
        ).eq("id", int(clean_q))
        
        if shop:
            shop_res = supabase.table("shops").select("id").eq("shop_code", shop).execute()
            if shop_res.data:
                query = query.eq("shop_id", shop_res.data[0]["id"])
                
        res = query.execute()
        if res.data:
            return res.data[0]

    phone_digits = "".join(filter(str.isdigit, clean_q))
    search_sub = phone_digits[-9:] if len(phone_digits) >= 9 else phone_digits

    cust_res = supabase.table("customers").select("id").ilike("phone", f"%{search_sub}%").execute()
    
    if cust_res.data:
        cust_ids = [c["id"] for c in cust_res.data]
        order_query = supabase.table("repair_orders").select(
            "id, brand, model, problem_desc, status, cost, inspection, warranty_days"
        ).in_("customer_id", cust_ids).order("id", desc=True).limit(1)
        
        if shop:
            shop_res = supabase.table("shops").select("id").eq("shop_code", shop).execute()
            if shop_res.data:
                order_query = order_query.eq("shop_id", shop_res.data[0]["id"])
                
        res = order_query.execute()
        if res.data:
            return res.data[0]

    raise HTTPException(status_code=404, detail="لم يتم العثور على أجهزة مطابقة")
