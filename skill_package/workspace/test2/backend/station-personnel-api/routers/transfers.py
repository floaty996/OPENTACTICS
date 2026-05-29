"""
换站申请与审批相关路由 — 读写 allocation.station_transfers
审批通过后同步更新 employee_station 表
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import fetch_all_target, fetch_one_target, execute_target, fetch_one_source

router = APIRouter(prefix="/api/transfers", tags=["换站申请管理"])


class TransferCreate(BaseModel):
    employee_no: str
    to_subway_line: str
    to_subway_station: str
    reason: str
    apply_date: str | None = None


class TransferApprove(BaseModel):
    status: str  # approved / rejected
    approver: str
    reject_reason: str | None = None


@router.get("")
@router.get("/")
def list_transfers(
    status: str | None = None,
    employee_no: str | None = None,
):
    """获取换站申请列表"""
    sql = "SELECT * FROM station_transfers WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = %s"
        params.append(status)
    if employee_no:
        sql += " AND employee_no = %s"
        params.append(employee_no)
    sql += " ORDER BY apply_date DESC, created_at DESC"
    return fetch_all_target(sql, params)


@router.get("/{transfer_id}")
def get_transfer(transfer_id: int):
    """获取单个申请详情"""
    row = fetch_one_target(
        "SELECT * FROM station_transfers WHERE id = %s", [transfer_id]
    )
    if not row:
        raise HTTPException(status_code=404, detail="申请不存在")
    return row


@router.post("")
def create_transfer(data: TransferCreate):
    """提交换站申请"""
    # 1. 查找员工（源库）
    employee = fetch_one_source(
        "SELECT * FROM metro_employees WHERE emp_id = %s", [data.employee_no]
    )
    if not employee:
        raise HTTPException(status_code=404, detail="员工编号不存在")
    if employee["status"] != "在职":
        raise HTTPException(status_code=400, detail="员工状态非在职，不可申请")

    # 2. 检查目标站点不能与当前相同
    if employee["subway_line"] == data.to_subway_line and employee["subway_station"] == data.to_subway_station:
        raise HTTPException(status_code=400, detail="目标站点与当前站点相同")

    # 3. 检查是否有待处理的申请
    pending = fetch_one_target(
        "SELECT id FROM station_transfers WHERE employee_no=%s AND status='pending'",
        [data.employee_no],
    )
    if pending:
        raise HTTPException(status_code=400, detail="该员工已有待处理的申请")

    today = data.apply_date or str(date.today())
    new_id = execute_target(
        """INSERT INTO station_transfers
           (employee_no, employee_name, from_subway_line, from_subway_station,
            to_subway_line, to_subway_station, reason, status, apply_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s)""",
        [data.employee_no, employee["name"],
         employee["subway_line"], employee["subway_station"],
         data.to_subway_line, data.to_subway_station,
         data.reason, today],
    )
    return {"ok": True, "id": new_id, "message": "申请提交成功"}


@router.put("/{transfer_id}/approve")
def approve_transfer(transfer_id: int, data: TransferApprove):
    """审批换站申请"""
    if data.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="状态值必须为 approved 或 rejected")

    transfer = fetch_one_target(
        "SELECT * FROM station_transfers WHERE id = %s", [transfer_id]
    )
    if not transfer:
        raise HTTPException(status_code=404, detail="申请不存在")
    if transfer["status"] != "pending":
        raise HTTPException(status_code=400, detail="申请已处理，不能重复审批")

    today = str(date.today())

    # 1. 更新申请状态
    execute_target(
        """UPDATE station_transfers
           SET status=%s, approve_date=%s, approver=%s, reject_reason=%s
           WHERE id=%s""",
        [data.status, today, data.approver, data.reject_reason, transfer_id],
    )

    # 2. 如果审批通过，更新 employee_station 表中的员工站点信息
    if data.status == "approved":
        execute_target(
            """UPDATE employee_station
               SET subway_line=%s, subway_station=%s
               WHERE employee_no=%s""",
            [transfer["to_subway_line"], transfer["to_subway_station"],
             transfer["employee_no"]],
        )

    action = "已通过（员工站点已同步更新）" if data.status == "approved" else "已驳回"
    return {"ok": True, "message": f"申请{action}"}
