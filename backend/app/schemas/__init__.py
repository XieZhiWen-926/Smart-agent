"""Pydantic Schema 层：定义 API 的"请求长什么样、响应长什么样"。

【为什么需要 schemas，而不直接用 models 层的 ORM 类？】
- 安全：ORM 对象含 hashed_password 等敏感字段，不能直接吐给前端；
- 解耦：数据库表结构变了，不影响对外 API 契约；
- 校验：Pydantic 会在请求进路由函数前自动校验类型/长度，不合法直接 422。

在分层中的位置：api 层的入参/出参都由本层描述，
FastAPI 用它们自动生成 Swagger 文档并做数据校验。
"""
