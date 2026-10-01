"""API 路由层：系统的最外层，负责接收 HTTP 请求、返回 HTTP 响应。

【这一层干什么】
- 用 @router.get/post/put/delete 声明接口路径；
- 用 Depends 注入数据库会话和当前登录用户（见 deps.py）；
- 接收/返回的数据用 schemas 层的 Pydantic 模型校验和包装；
- 真正的业务逻辑全部委托给 services 层，路由本身不写业务判断、不写 SQL。

在分层中的位置：浏览器/Nginx -> api(本层) -> services -> repositories -> models。
"""
