-- 新增锁定排班持久化表
-- 执行时间：2026-03-20

USE aischeduling;

CREATE TABLE IF NOT EXISTS locked_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '锁定记录ID',
    employee_id INT NOT NULL COMMENT '员工ID',
    date DATE NOT NULL COMMENT '锁定日期',
    shift_type VARCHAR(20) NOT NULL COMMENT '锁定班次类型',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    UNIQUE KEY uq_locked_assignment_employee_date (employee_id, date),
    INDEX idx_locked_assignment_date (date),
    INDEX idx_locked_assignment_employee (employee_id),
    CONSTRAINT fk_locked_assignment_employee FOREIGN KEY (employee_id)
        REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='锁定排班表';
