-- AIScheduling 数据库初始化脚本
-- MySQL 8.0+

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS aischeduling
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE aischeduling;

-- ============================================
-- 表1: 避让规则表 (需先创建，因为 employees 表引用它)
-- ============================================
CREATE TABLE IF NOT EXISTS avoidance_rules (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '规则ID',
    name VARCHAR(50) NULL COMMENT '规则名称',
    member_ids_json JSON NOT NULL COMMENT '互斥成员ID列表JSON',
    description TEXT NULL COMMENT '规则说明',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否启用',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='避让规则表';

-- ============================================
-- 表2: 员工表
-- ============================================
CREATE TABLE IF NOT EXISTS employees (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '员工ID',
    name VARCHAR(50) NOT NULL COMMENT '姓名',
    is_night_leader BOOLEAN DEFAULT FALSE COMMENT '是否夜班长/主任资质(前6列)',
    sequence_order INT NOT NULL DEFAULT 0 COMMENT '前端列排序顺序',
    avoidance_group_id INT NULL COMMENT '避让规则组ID',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    INDEX idx_employee_sequence (sequence_order),
    CONSTRAINT fk_employee_avoidance FOREIGN KEY (avoidance_group_id)
        REFERENCES avoidance_rules(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='员工信息表';

-- ============================================
-- 表3: 排班记录表
-- ============================================
CREATE TABLE IF NOT EXISTS shifts (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '排班记录ID',
    date DATE NOT NULL COMMENT '日期',
    group_id VARCHAR(1) NOT NULL COMMENT '组别: A/B/C',
    employee_id INT NOT NULL COMMENT '员工ID',
    shift_type VARCHAR(20) NOT NULL COMMENT '班次类型: DAY/SLEEP/MINI_NIGHT/LATE_NIGHT/VACATION/NONE',
    seat_type VARCHAR(20) NULL COMMENT '席位类型: CHIEF/NORTHWEST/SOUTHEAST/REGULAR等',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',

    INDEX idx_shift_date (date),
    INDEX idx_shift_date_group (date, group_id),
    INDEX idx_shift_employee (employee_id),
    UNIQUE KEY uq_shift_date_group_employee (date, group_id, employee_id),
    CONSTRAINT fk_shift_employee FOREIGN KEY (employee_id)
        REFERENCES employees(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='排班记录表';

-- ============================================
-- 表4: 系统配置表
-- ============================================
CREATE TABLE IF NOT EXISTS system_config (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '配置ID',
    config_key VARCHAR(50) NOT NULL UNIQUE COMMENT '配置键',
    config_value VARCHAR(255) NOT NULL COMMENT '配置值',
    description TEXT NULL COMMENT '配置说明',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';

-- ============================================
-- 初始数据插入
-- ============================================

-- 插入系统配置：锚点日期和锚点组别
INSERT INTO system_config (config_key, config_value, description) VALUES
    ('anchor_date', '2024-01-01', '锚点日期，用于计算做一休二的工作日'),
    ('anchor_group', 'A', '锚点组别，锚点日期当天工作的组')
ON DUPLICATE KEY UPDATE config_value = VALUES(config_value);

-- 插入避让规则
INSERT INTO avoidance_rules (id, name, member_ids_json, description) VALUES
    (1, 'G1-张伟李浩', '[1, 2]', '张伟和李浩不能同班'),
    (2, 'G2-王强赵磊', '[7, 8]', '王强和赵磊不能同班')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- 插入初始员工数据（17人：6个主任 + 11个普通员工）
INSERT INTO employees (id, name, is_night_leader, sequence_order, avoidance_group_id) VALUES
    -- 主任资质员工（前6人）
    (1, '张伟', TRUE, 1, 1),
    (2, '李浩', TRUE, 2, 1),
    (3, '陈明', TRUE, 3, NULL),
    (4, '刘洋', TRUE, 4, NULL),
    (5, '周杰', TRUE, 5, NULL),
    (6, '吴涛', TRUE, 6, NULL),
    -- 普通员工（后11人）
    (7, '王强', FALSE, 7, 2),
    (8, '赵磊', FALSE, 8, 2),
    (9, '孙毅', FALSE, 9, NULL),
    (10, '徐静', FALSE, 10, NULL),
    (11, '马博', FALSE, 11, NULL),
    (12, '胡军', FALSE, 12, NULL),
    (13, '林峰', FALSE, 13, NULL),
    (14, '郭鹏', FALSE, 14, NULL),
    (15, '何洁', FALSE, 15, NULL),
    (16, '高飞', FALSE, 16, NULL),
    (17, '罗娜', FALSE, 17, NULL)
ON DUPLICATE KEY UPDATE name = VALUES(name), is_night_leader = VALUES(is_night_leader);

-- 更新避让规则的成员ID（基于实际插入的员工ID）
UPDATE avoidance_rules SET member_ids_json = '[1, 2]' WHERE id = 1;
UPDATE avoidance_rules SET member_ids_json = '[7, 8]' WHERE id = 2;
