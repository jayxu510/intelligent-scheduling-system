"""
修复脚本：将每组前6人设置为主任资质
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.config import get_db
from database.models import Employee

def fix_night_leaders():
    db = next(get_db())

    for group_id in ['A', 'B', 'C']:
        print(f"\n处理 {group_id} 组...")

        # 获取该组所有员工，按 sequence_order 排序
        employees = db.query(Employee).filter(
            Employee.group_id == group_id
        ).order_by(Employee.sequence_order).all()

        print(f"  总人数: {len(employees)}")

        # 前6人设置为主任资质
        for i, emp in enumerate(employees):
            if i < 6:
                if not emp.is_night_leader:
                    emp.is_night_leader = True
                    print(f"  [OK] 设置 {emp.name} 为主任资质")
            else:
                if emp.is_night_leader:
                    emp.is_night_leader = False
                    print(f"  [OK] 取消 {emp.name} 的主任资质")

        db.commit()
        print(f"  {group_id} 组处理完成！")

    print("\n[SUCCESS] 所有组别处理完成！")
    db.close()

if __name__ == "__main__":
    fix_night_leaders()
