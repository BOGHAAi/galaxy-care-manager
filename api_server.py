import os
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

# 1. إنشاء التطبيق
app = FastAPI(
    title="Galaxy Care Multi-Tenant Cloud API",
    description="سيرفر الربط السحابي وإدارة محلات الصيانة المتعددة",
    version="2.0.0"
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

# ==================== المسارات والروابط ====================

@app.get("/")
def home():
    return {"status": "online", "mode": "multi-tenant", "message": "Galaxy Care Multi-Tenant Cloud API is running"}

# فتح لوحة الموبايل مباشرة من المتصفح
@app.get("/mobile", response_class=FileResponse)
def serve_mobile_dashboard():
    return "dashboard.html"

# فتح صفحة التتبع للعميل
@app.get("/track", response_class=FileResponse)
def serve_track_page():
    return "track.html"

# مسار إحصائيات الخزينة والأرباح اليومية للمحل الحالي
@app.get("/api/stats/today")
def get_today_stats(shop: dict = Depends(get_current_shop)):
    shop_id = shop["id"]
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    # جلب معاملات الخزينة لليوم الخاصة بالمحل فقط
    treasury_res = supabase.table("treasury").select("trans_type, amount").eq("shop_id", shop_id).gte("created_at", f"{today_str}T00:00:00").execute()
    
    today_income = sum(t["amount"] for t in treasury_res.data if t.get("trans_type") == "وارد")
    today_expense = sum(t["amount"] for t in treasury_res.data if t.get("trans_type") == "صادر")
    
    # جلب أذونات الصيانة التي تم تسليمها اليوم للمحل فقط
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
        "id, brand, model, problem_desc, cost, part_cost, status, notes, inspection, warranty_days, received_at, customers(name, phone), employees(name)"
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

# مسار تتبع العميل العام (يدعم البحث المباشر برقم الإذن أو رقم الهاتف)
@app.get("/api/track")
def track_repair(q: str, shop: Optional[str] = None):
    query = supabase.table("repair_orders").select(
        "id, brand, model, problem_desc, status, cost, inspection, warranty_days, shops(shop_name, phone)"
    )
    
    if shop:
        shop_res = supabase.table("shops").select("id").eq("shop_code", shop).execute()
        if shop_res.data:
            query = query.eq("shop_id", shop_res.data[0]["id"])

    # البحث برقم الإذن
    if q.isdigit():
        res = query.eq("id", int(q)).execute()
        if res.data:
            return res.data[0]
            
    # البحث برقم هاتف العميل
    cust = supabase.table("customers").select("id").eq("phone", q).execute()
    if cust.data:
        cust_id = cust.data[0]["id"]
        res = query.eq("customer_id", cust_id).order("id", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]
            
    raise HTTPException(status_code=404, detail="لم يتم العثور على أجهزة مطابقة")