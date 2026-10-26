-- ============================================================
-- 电商风险控制系统 - SQLite 数据库结构
-- 核心 8 张表严格对应需求文档 2.3.8 字段定义
-- 另附业务明细表（用户/订单/地址/设备等）与审计辅助表
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------- 核心表：风险事件 ----------
CREATE TABLE IF NOT EXISTS risk_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type         TEXT    NOT NULL,
    source_id          TEXT    NOT NULL,
    user_id            TEXT    NOT NULL,
    order_id           TEXT,
    event_payload_json TEXT    NOT NULL,
    created_at         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_risk_events_user       ON risk_events(user_id);
CREATE INDEX IF NOT EXISTS idx_risk_events_created    ON risk_events(created_at);
CREATE INDEX IF NOT EXISTS idx_risk_events_type       ON risk_events(event_type);

-- ---------- 核心表：风险评估结果 ----------
CREATE TABLE IF NOT EXISTS risk_assessments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          INTEGER NOT NULL,
    risk_score        REAL    NOT NULL,
    risk_level        TEXT    NOT NULL,
    decision          TEXT    NOT NULL,
    assessment_status TEXT    NOT NULL DEFAULT 'completed',
    created_at        TEXT    NOT NULL,
    FOREIGN KEY (event_id) REFERENCES risk_events(id)
);
CREATE INDEX IF NOT EXISTS idx_assessments_event      ON risk_assessments(event_id);
CREATE INDEX IF NOT EXISTS idx_assessments_created    ON risk_assessments(created_at);
CREATE INDEX IF NOT EXISTS idx_assessments_level      ON risk_assessments(risk_level);

-- ---------- 核心表：特征快照 ----------
CREATE TABLE IF NOT EXISTS feature_snapshots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL UNIQUE,
    feature_json  TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_assessment ON feature_snapshots(assessment_id);

-- ---------- 核心表：风险规则 ----------
CREATE TABLE IF NOT EXISTS risk_rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code      TEXT    NOT NULL UNIQUE,
    rule_name      TEXT    NOT NULL,
    rule_status    TEXT    NOT NULL DEFAULT 'enabled',
    priority       INTEGER NOT NULL DEFAULT 5,
    score          INTEGER NOT NULL DEFAULT 10,
    condition_json TEXT    NOT NULL,
    description    TEXT    NOT NULL DEFAULT '',
    updated_at     TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rules_status ON risk_rules(rule_status);

-- ---------- 核心表：规则命中明细 ----------
CREATE TABLE IF NOT EXISTS rule_hits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL,
    rule_id       INTEGER NOT NULL,
    hit_score     REAL    NOT NULL,
    hit_message   TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id)
);
CREATE INDEX IF NOT EXISTS idx_hits_assessment ON rule_hits(assessment_id);
CREATE INDEX IF NOT EXISTS idx_hits_rule       ON rule_hits(rule_id);

-- ---------- 核心表：风险案件 ----------
CREATE TABLE IF NOT EXISTS risk_cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL UNIQUE,
    user_id       TEXT    NOT NULL,
    order_id      TEXT,
    case_status   TEXT    NOT NULL DEFAULT 'pending',
    reviewer_id   TEXT,
    review_result TEXT,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id)
);
CREATE INDEX IF NOT EXISTS idx_cases_status ON risk_cases(case_status);
CREATE INDEX IF NOT EXISTS idx_cases_user   ON risk_cases(user_id);
CREATE INDEX IF NOT EXISTS idx_cases_created ON risk_cases(created_at);

-- ---------- 核心表：黑名单 ----------
CREATE TABLE IF NOT EXISTS blacklists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    blacklist_type  TEXT    NOT NULL,
    blacklist_value TEXT    NOT NULL,
    remark          TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'active',
    created_at      TEXT    NOT NULL,
    UNIQUE (blacklist_type, blacklist_value)
);
CREATE INDEX IF NOT EXISTS idx_blacklists_type   ON blacklists(blacklist_type);
CREATE INDEX IF NOT EXISTS idx_blacklists_status ON blacklists(status);

-- ---------- 核心表：审核日志 ----------
CREATE TABLE IF NOT EXISTS review_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id      INTEGER NOT NULL,
    operator_id  TEXT    NOT NULL,
    action_type  TEXT    NOT NULL,
    action_remark TEXT   NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    FOREIGN KEY (case_id) REFERENCES risk_cases(id)
);
CREATE INDEX IF NOT EXISTS idx_logs_case ON review_logs(case_id);

-- ============================================================
-- 业务明细表：为特征计算提供真实数据来源
-- ============================================================

CREATE TABLE IF NOT EXISTS biz_users (
    user_id          TEXT PRIMARY KEY,
    user_name        TEXT NOT NULL,
    phone            TEXT NOT NULL,
    phone_city       TEXT NOT NULL,
    register_at      TEXT NOT NULL,
    register_province TEXT NOT NULL,
    register_city    TEXT NOT NULL,
    is_enterprise    INTEGER NOT NULL DEFAULT 0,
    credit_score     INTEGER NOT NULL DEFAULT 80,
    vip_level        TEXT NOT NULL DEFAULT '普通会员'
);

CREATE TABLE IF NOT EXISTS biz_addresses (
    address_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    receiver_name TEXT NOT NULL,
    phone         TEXT NOT NULL,
    province      TEXT NOT NULL,
    city          TEXT NOT NULL,
    detail        TEXT NOT NULL,
    is_default    INTEGER NOT NULL DEFAULT 0,
    change_cnt    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_addresses_user ON biz_addresses(user_id);

CREATE TABLE IF NOT EXISTS biz_devices (
    device_id     TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    device_name   TEXT NOT NULL,
    os            TEXT NOT NULL,
    first_seen    TEXT NOT NULL,
    last_login_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devices_user ON biz_devices(user_id);

CREATE TABLE IF NOT EXISTS biz_login_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT NOT NULL,
    city       TEXT NOT NULL,
    ip         TEXT NOT NULL,
    device_id  TEXT NOT NULL,
    login_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_user ON biz_login_logs(user_id);

CREATE TABLE IF NOT EXISTS biz_orders (
    order_id           TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL,
    amount             REAL NOT NULL,
    discount_rate      REAL NOT NULL DEFAULT 0,
    freight            REAL NOT NULL DEFAULT 0,
    pay_method         TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    paid_at            TEXT,
    pay_interval_sec   INTEGER NOT NULL DEFAULT 0,
    category           TEXT NOT NULL,
    category_risk_score INTEGER NOT NULL DEFAULT 0,
    item_count         INTEGER NOT NULL DEFAULT 1,
    address_id         TEXT NOT NULL,
    device_id          TEXT NOT NULL,
    ip                 TEXT NOT NULL,
    receive_province   TEXT NOT NULL,
    receive_city       TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'paid'
);
CREATE INDEX IF NOT EXISTS idx_orders_user    ON biz_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_created ON biz_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_ip      ON biz_orders(ip);
CREATE INDEX IF NOT EXISTS idx_orders_device  ON biz_orders(device_id);
CREATE INDEX IF NOT EXISTS idx_orders_address ON biz_orders(address_id);

CREATE TABLE IF NOT EXISTS biz_after_sales (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    after_sale_id TEXT NOT NULL UNIQUE,
    order_id     TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    apply_type   TEXT NOT NULL,
    reason       TEXT NOT NULL,
    amount       REAL NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'finished',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_after_sales_user ON biz_after_sales(user_id);

-- ============================================================
-- 审计辅助表：Agent 轨迹与黑名单命中留痕
-- ============================================================

CREATE TABLE IF NOT EXISTS assessment_traces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL UNIQUE,
    trace_json    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id)
);

CREATE TABLE IF NOT EXISTS blacklist_hit_records (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id  INTEGER NOT NULL,
    blacklist_id   INTEGER NOT NULL,
    blacklist_type TEXT NOT NULL,
    blacklist_value TEXT NOT NULL,
    added_score    REAL NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (assessment_id) REFERENCES risk_assessments(id)
);
CREATE INDEX IF NOT EXISTS idx_bl_hits_assessment ON blacklist_hit_records(assessment_id);
CREATE INDEX IF NOT EXISTS idx_bl_hits_value      ON blacklist_hit_records(blacklist_value);
