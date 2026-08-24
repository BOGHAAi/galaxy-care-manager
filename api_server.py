import os
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from fastapi.responses import FileResponse

@app.get("/mobile", response_class=FileResponse)
def serve_mobile_dashboard():
    return "dashboard.html"

# وضع البيانات مباشرة لمنع أي خطأ في قراءة ملف .env
SUPABASE_URL = "https://jolhhglgomnocrglmxco.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpvbGhoZ2xnb21ub2NyZ2xteGNvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc1MjMzMTgsImV4cCI6MjEwMzA5OTMxOH0.2jJLUh-enCuIrN25lQc2o1sgnh7JyzdtaTpiwnh0SF8"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(
    title="Galaxy Care Cloud API",
    description="سيرفر الربط السحابي لمركز Galaxy Care",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.get("/")
def home():
    return {"status": "online", "message": "Galaxy Care Cloud API is running successfully"}

@app.post("/api/auth/login")
def login(data: LoginRequest):
    res = supabase.table("app_users").select("id, username, role").eq("username", data.username).eq("password", data.password).execute()
    if not res.data:
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة")
    return {"status": "success", "user": res.data[0]}

@app.get("/api/repairs")
def get_repairs():
    res = supabase.table("repair_orders").select(
        "id, brand, model, problem_desc, cost, part_cost, status, notes, inspection, warranty_days, received_at, customers(name, phone), employees(name)"
    ).order("id", desc=True).execute()
    return res.data

@app.post("/api/repairs/add")
def add_repair(data: RepairCreateRequest):
    cust_res = supabase.table("customers").select("id").eq("phone", data.customer_phone).execute()
    if cust_res.data:
        customer_id = cust_res.data[0]["id"]
    else:
        new_cust = supabase.table("customers").insert({"name": data.customer_name, "phone": data.customer_phone}).execute()
        customer_id = new_cust.data[0]["id"]

    order_data = {
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