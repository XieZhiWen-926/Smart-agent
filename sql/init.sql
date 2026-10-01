-- ==============================================
-- 智扫通智能客服 v2 - 数据库初始化脚本
-- 适用：MySQL 8.0+
-- 使用方法：
--   方式一（推荐）：docker-compose 启动时自动执行
--   方式二：手动执行  mysql -u root -p < init.sql
-- ==============================================

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS smart_agent_v2
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_agent_v2;

-- ==============================================
-- 【★ 必须有这一行，否则中文会变乱码 ★】
-- SET NAMES utf8mb4 的作用：告诉服务器"客户端发过来的字节是 utf8mb4 编码"。
-- 本文件里含有中文（张三/李四/王五、工具描述等）。
-- 如果客户端默认字符集是 latin1（MySQL 客户端常见默认值），
-- 服务器会把 UTF-8 字节按 latin1 解释，再按 utf8mb4 存进去，产生"二次编码"：
--     张三(正确: E5BCA0E4B889) → 存成 C3A5C2BCC2A0... （页面上显示 å¼ ä¸‰）
-- 加这一行即可从根上避免。注意：它必须放在任何 INSERT 之前。
-- ==============================================
SET NAMES utf8mb4;

-- ==============================================
-- 1. 系统用户表 users
--    存后台登录账号（客服/管理员），与"客户"是两回事：
--    users 是系统操作者，customers 是被服务的扫地机器人机主。
-- ==============================================
CREATE TABLE IF NOT EXISTS users (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
    username        VARCHAR(64)  NOT NULL UNIQUE COMMENT '用户名',
    -- 只存 bcrypt 哈希，绝不存明文密码；登录时比对哈希
    hashed_password VARCHAR(255) NOT NULL COMMENT '密码哈希(bcrypt)',
    full_name       VARCHAR(64)  DEFAULT '' COMMENT '真实姓名',
    role            VARCHAR(32)  DEFAULT 'admin' COMMENT '角色:admin/operator',
    is_active       TINYINT(1)   DEFAULT 1 COMMENT '是否启用',
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    -- 登录按 username 查用户，走索引避免全表扫描（username 已有唯一约束，此索引为冗余兜底）
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统用户表';

-- ==============================================
-- 2. 客户信息表 customers
--    核心业务表：扫地机器人机主档案。会话、记忆都通过
--    customer_id 挂到这张表上；Text2SQL 查客户也是查它。
-- ==============================================
CREATE TABLE IF NOT EXISTS customers (
    id            INT AUTO_INCREMENT PRIMARY KEY COMMENT '客户ID',
    name          VARCHAR(64)  NOT NULL COMMENT '客户姓名',
    phone         VARCHAR(20)  NOT NULL UNIQUE COMMENT '手机号',
    city          VARCHAR(64)  DEFAULT '' COMMENT '所在城市',
    address       VARCHAR(255) DEFAULT '' COMMENT '详细地址',
    -- 经纬度由地图工具（高德地理编码）回填，用于"查附近维修点"等周边搜索
    longitude     FLOAT        NULL COMMENT '地址经度(高德坐标系)',
    latitude      FLOAT        NULL COMMENT '地址纬度(高德坐标系)',
    member_level  VARCHAR(32)  DEFAULT '普通' COMMENT '会员等级:普通/银卡/金卡/钻石',
    product_model VARCHAR(64)  DEFAULT '' COMMENT '购买的扫地机器人型号',
    purchase_date DATETIME     NULL COMMENT '购买日期',
    remark        TEXT         COMMENT '备注',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 按手机号反查客户是高频操作（来电识别），phone 已有唯一约束，索引兜底
    INDEX idx_phone (phone),
    -- "深圳金卡用户有谁"这类 Text2SQL 查询常按 city 过滤，加索引提速
    INDEX idx_city (city)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户信息表';

-- ==============================================
-- 3. 自定义工具表 custom_tools
--    ReAct 智能体的"工具箱"：每行是一个可调用的工具。
--    description 和 parameters_schema 会拼进大模型提示词，
--    模型靠它们判断"什么时候该调哪个工具、传什么参数"。
-- ==============================================
CREATE TABLE IF NOT EXISTS custom_tools (
    id               INT AUTO_INCREMENT PRIMARY KEY COMMENT '工具ID',
    -- 工具名即模型 function calling 里的函数名，必须唯一
    name             VARCHAR(128) NOT NULL UNIQUE COMMENT '工具名称(英文函数名)',
    -- 描述写给大模型看：什么场景该用它，写得越清楚模型选得越准
    description      TEXT         NOT NULL COMMENT '工具描述',
    tool_type        VARCHAR(32)  NOT NULL COMMENT '类型:builtin/map_amap/map_baidu/python_func/http_api',
    -- JSON Schema 描述入参（字段名/类型/含义/必填），模型据此生成调用参数
    parameters_schema JSON        NOT NULL COMMENT '参数JSON Schema',
    -- 工具自身的配置（如高德接口的 endpoint），与参数 Schema 区分开
    config           JSON         NULL COMMENT '工具配置JSON',
    is_enabled       TINYINT(1)   DEFAULT 1 COMMENT '是否启用',
    version          INT          DEFAULT 1 COMMENT '版本号',
    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 按工具名定位记录（name 已有唯一约束，索引兜底）
    INDEX idx_name (name),
    -- 管理页/加载器常按类型筛选工具（如只取地图类），加索引提速
    INDEX idx_type (tool_type),
    -- 启动时只加载 is_enabled=1 的工具，加索引快速过滤启用的工具
    INDEX idx_enabled (is_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自定义工具定义表';

-- ==============================================
-- 4. 会话表 conversations
--    一个客户可以有多段对话（类似微信的聊天窗口），
--    每段对话下的具体问答存在 messages 表。
-- ==============================================
CREATE TABLE IF NOT EXISTS conversations (
    id          INT AUTO_INCREMENT PRIMARY KEY COMMENT '会话ID',
    customer_id INT          NOT NULL COMMENT '关联客户ID',
    title       VARCHAR(255) DEFAULT '新会话' COMMENT '会话标题',
    created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    -- ON UPDATE CURRENT_TIMESTAMP：每次会话有动静自动刷新，可直接当"最后活跃时间"排序
    updated_at  DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后活跃时间',
    -- 聊天页左侧"某客户的会话列表"按 customer_id 查，外键列必须建索引（高频查询）
    INDEX idx_customer (customer_id),
    -- 会话列表按时间倒序展示，加索引避免每次排序全表
    INDEX idx_created (created_at),
    -- 级联删除：删客户时其会话一并删除，不留孤儿数据
    CONSTRAINT fk_conv_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话表';

-- ==============================================
-- 5. 消息表 messages
--    每个问答一条：用户提问、助手回答、工具调用结果都在这。
--    历史消息会按时间顺序拼进大模型上下文，实现"记得上下文"。
-- ==============================================
CREATE TABLE IF NOT EXISTS messages (
    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '消息ID',
    conversation_id INT          NOT NULL COMMENT '关联会话ID',
    -- tool 角色的消息记录工具返回结果，是 ReAct"观察"环节的依据
    role            VARCHAR(16)  NOT NULL COMMENT '角色:user/assistant/tool/system',
    content         TEXT         NOT NULL COMMENT '消息内容',
    token_count     INT          DEFAULT 0 COMMENT '消耗token数',
    tool_name       VARCHAR(128) NULL COMMENT '工具调用时的工具名',
    created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    -- 打开一个会话要拉它的全部历史消息，conversation_id 是最高频查询条件
    INDEX idx_conversation (conversation_id),
    -- 拼模型上下文/统计时常按角色过滤（如只取 user+assistant），加索引提速
    INDEX idx_role (role),
    -- 历史消息按时间排序，加索引避免全表排序
    INDEX idx_created (created_at),
    -- 级联删除：删会话时其消息一并删除
    CONSTRAINT fk_msg_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息表';

-- ==============================================
-- 6. 长期记忆表 long_term_memories
--    从对话中自动提炼的客户偏好/事实（如"对噪音敏感"），
--    新会话开始时按相似度召回，让客服"记得住老客户"。
-- ==============================================
CREATE TABLE IF NOT EXISTS long_term_memories (
    id               INT AUTO_INCREMENT PRIMARY KEY COMMENT '记忆ID',
    customer_id      INT          NOT NULL COMMENT '关联客户ID',
    memory_type      VARCHAR(32)  NOT NULL COMMENT '类型:fact/preference/summary',
    content          TEXT         NOT NULL COMMENT '记忆内容',
    -- 1~10 分，影响召回排序：重要的事（如过敏/投诉史）排前面
    importance       INT          DEFAULT 5 COMMENT '重要性1-10',
    -- 记忆文本的向量嵌入（embedding），召回时做相似度匹配用
    embedding        JSON         NULL COMMENT '向量嵌入(JSON数组)',
    source_message_id INT         NULL COMMENT '来源消息ID',
    -- last_used_at/use_count 记录召回命中情况，可用于淘汰长期没用的记忆
    last_used_at     DATETIME     NULL COMMENT '最后使用时间',
    use_count        INT          DEFAULT 0 COMMENT '使用次数',
    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 每次新会话都按 customer_id 召回该客户的记忆，最高频查询条件
    INDEX idx_customer (customer_id),
    -- 管理页/召回策略常按类型筛选（如只取 preference），加索引提速
    INDEX idx_type (memory_type),
    -- 记忆列表按时间排序展示
    INDEX idx_created (created_at),
    -- 级联删除：删客户时其记忆一并删除
    CONSTRAINT fk_mem_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='长期记忆表';

-- ==============================================
-- 7. 数据集元数据表 datasets
--    用户上传的 CSV 会被解析成一张独立的 MySQL 数据表，
--    本表只存"档案信息"（元数据）：真实表名、行数、列信息等。
--    CSV 解析是重活，由 Celery 异步执行，status 记录进度状态。
-- ==============================================
CREATE TABLE IF NOT EXISTS datasets (
    id            INT AUTO_INCREMENT PRIMARY KEY COMMENT '数据集ID',
    name          VARCHAR(128) NOT NULL COMMENT '数据集名称',
    description   TEXT         COMMENT '数据集描述',
    -- CSV 导入后真正存数据的表名（动态建表），Text2SQL 按它去查数据
    table_name    VARCHAR(128) NOT NULL UNIQUE COMMENT '实际存储的MySQL表名',
    source_file   VARCHAR(255) DEFAULT '' COMMENT '原始CSV文件名',
    row_count     INT          DEFAULT 0 COMMENT '数据行数',
    column_count  INT          DEFAULT 0 COMMENT '列数',
    -- 列元数据含中文列名映射，Text2SQL 靠它把"用户说的中文"对应到真实列
    columns_meta  JSON         NOT NULL COMMENT '列元数据(含中文列名映射)',
    -- 异步导入状态机：pending→processing→completed/failed，前端据此展示
    status        VARCHAR(32)  DEFAULT 'pending' COMMENT '状态:pending/processing/completed/failed',
    error_msg     TEXT         COMMENT '失败原因',
    created_by    INT          NULL COMMENT '上传者用户ID',
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at    DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 管理页常按状态筛选（如看哪些失败了），加索引提速
    INDEX idx_status (status),
    -- 按真实表名反查数据集（Text2SQL 链路），table_name 已有唯一约束，索引兜底
    INDEX idx_table (table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据集元数据表';

-- ==============================================
-- 8. 异步任务表 async_tasks
--    CSV 导入、向量化等重活都丢给 Celery 异步跑，本表记录
--    每个任务的状态和进度，前端按 task_id 轮询展示进度条，
--    避免用户盯着转圈不知道卡没卡死。
-- ==============================================
CREATE TABLE IF NOT EXISTS async_tasks (
    id         INT AUTO_INCREMENT PRIMARY KEY COMMENT '任务ID',
    -- Celery 返回的任务 ID，前端轮询进度就靠它
    task_id    VARCHAR(128) NOT NULL UNIQUE COMMENT 'Celery任务ID',
    task_type  VARCHAR(64)  NOT NULL COMMENT '类型:csv_import/vectorize/report',
    status     VARCHAR(32)  DEFAULT 'pending' COMMENT '状态:pending/processing/completed/failed',
    progress   INT          DEFAULT 0 COMMENT '进度0-100',
    result     JSON         NULL COMMENT '任务结果',
    error_msg  TEXT         COMMENT '失败原因',
    created_at DATETIME     DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 前端轮询进度按 task_id 精确查，task_id 已有唯一约束，索引兜底
    INDEX idx_task_id (task_id),
    -- 运维排查常按任务类型统计/筛选，加索引提速
    INDEX idx_type (task_type),
    -- 找"卡住的任务"（长期 processing）等场景按状态过滤，加索引提速
    INDEX idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='异步任务状态表';

-- ==============================================
-- 初始数据
-- ==============================================

-- 默认管理员用户由后端启动时自动创建（用户名 admin，密码 admin123）
-- 不在此处硬编码 bcrypt 哈希，避免哈希无效导致无法登录。
-- 生产环境请在首次登录后立即修改密码。

-- 内置工具定义（这些工具在代码中也有对应实现，数据库记录用于统一管理和前端展示）
-- 末尾 ON DUPLICATE KEY UPDATE name=name：重复执行本脚本时跳过已存在的记录，
-- 保证脚本可重复跑（幂等），不会报错也不会插重复数据。
INSERT INTO custom_tools (name, description, tool_type, parameters_schema, config, is_enabled, version) VALUES
('rag_summarize',
 '从扫地机器人知识库中检索相关资料并生成摘要回答。当用户询问产品功能、故障排除、维护保养、选购建议等知识类问题时使用。',
 'builtin',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('query', JSON_OBJECT('type', 'string', 'description', '用户的问题')), 'required', JSON_ARRAY('query')),
 JSON_OBJECT('source', 'chroma_knowledge_base'),
 1, 1),
('amap_geocode',
 '高德地图地理编码：将详细地址转换为经纬度坐标。当需要获取某个地址的经纬度时使用。',
 'map_amap',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('address', JSON_OBJECT('type', 'string', 'description', '详细地址，如北京市朝阳区望京SOHO'), 'city', JSON_OBJECT('type', 'string', 'description', '城市名，可选')), 'required', JSON_ARRAY('address')),
 JSON_OBJECT('api_endpoint', 'geocode/geo'),
 1, 1),
('amap_regeocode',
 '高德地图逆地理编码：将经纬度坐标转换为地址描述。当需要根据坐标获取地址信息时使用。',
 'map_amap',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('longitude', JSON_OBJECT('type', 'string', 'description', '经度'), 'latitude', JSON_OBJECT('type', 'string', 'description', '纬度')), 'required', JSON_ARRAY('longitude', 'latitude')),
 JSON_OBJECT('api_endpoint', 'geocode/regeo'),
 1, 1),
('amap_weather',
 '高德地图天气查询：获取指定城市的实时天气和预报信息。当用户询问天气情况时使用，返回真实天气数据。',
 'map_amap',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('city', JSON_OBJECT('type', 'string', 'description', '城市名，如北京、上海')), 'required', JSON_ARRAY('city')),
 JSON_OBJECT('api_endpoint', 'weather/weatherInfo', 'extensions', 'all'),
 1, 1),
('amap_around_search',
 '高德地图周边POI搜索：搜索指定位置附近的地点（如维修点、门店）。当用户需要查找附近的服务网点时使用。',
 'map_amap',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('keyword', JSON_OBJECT('type', 'string', 'description', '搜索关键词，如扫地机器人维修'), 'location', JSON_OBJECT('type', 'string', 'description', '中心点坐标，格式 经度,纬度'), 'radius', JSON_OBJECT('type', 'integer', 'description', '搜索半径米，默认3000')), 'required', JSON_ARRAY('keyword', 'location')),
 JSON_OBJECT('api_endpoint', 'place/around'),
 1, 1),
('baidu_geocode',
 '百度地图地理编码：将地址转换为百度坐标系经纬度。当需要使用百度地图服务获取坐标时使用。',
 'map_baidu',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('address', JSON_OBJECT('type', 'string', 'description', '详细地址')), 'required', JSON_ARRAY('address')),
 JSON_OBJECT('api_endpoint', 'geocoder/v2/'),
 1, 1),
('baidu_weather',
 '百度地图天气查询：获取指定城市的天气信息。当用户询问天气且偏好百度地图数据时使用。',
 'map_baidu',
 JSON_OBJECT('type', 'object', 'properties', JSON_OBJECT('district_id', JSON_OBJECT('type', 'string', 'description', '区县ID或城市名')), 'required', JSON_ARRAY('district_id')),
 JSON_OBJECT('api_endpoint', 'weather/v1/'),
 1, 1)
ON DUPLICATE KEY UPDATE name=name;

-- 示例客户数据（演示/联调用，上线前可删）
INSERT INTO customers (name, phone, city, address, member_level, product_model, remark) VALUES
('张三', '13800138001', '深圳', '深圳市南山区科技园', '金卡', '智扫通Pro X1', '对噪音敏感，偏好静音模式'),
('李四', '13800138002', '合肥', '合肥市蜀山区政务区', '普通', '智扫通Lite S2', ''),
('王五', '13800138003', '杭州', '杭州市西湖区文三路', '银卡', '智扫通Max M3', '养宠物，需要频繁清理毛发')
ON DUPLICATE KEY UPDATE phone=phone;
