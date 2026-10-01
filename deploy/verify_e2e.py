"""端到端功能验证脚本（只打印判定结果，不输出任何凭据）"""
import json
import urllib.request
import urllib.parse

BASE = "http://localhost:8000"


def req(method, path, data=None, token=None, form=False, timeout=30):
    url = BASE + path
    headers = {}
    body = None
    if form:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


print("=" * 60)
print("端到端功能验证")
print("=" * 60)

# ---- 1. 登录 ----
print("\n[1] 登录鉴权")
try:
    tok = req("POST", "/api/auth/login",
              {"username": "admin", "password": "admin123"}, form=True)["access_token"]
    check("admin 登录成功，拿到 token", bool(tok))
except Exception as e:
    check("admin 登录", False, str(e))
    raise SystemExit(1)

# ---- 2. 当前用户 ----
print("\n[2] 当前用户")
try:
    me = req("GET", "/api/auth/me", token=tok)
    check("GET /api/auth/me", me.get("username") == "admin", f"username={me.get('username')} role={me.get('role')}")
except Exception as e:
    check("GET /api/auth/me", False, str(e))

# ---- 3. 工具列表 ----
print("\n[3] 自定义工具（动态加载）")
try:
    tools = req("GET", "/api/tools", token=tok).get("data") or []
    check("工具数量 == 7", len(tools) == 7, f"实际 {len(tools)} 个")
    for t in tools:
        print(f"        id={t['id']:<2} {t['name']:<20} {t['tool_type']:<10} enabled={t['is_enabled']}")
except Exception as e:
    check("GET /api/tools", False, str(e))

# ---- 4. 客户列表 ----
print("\n[4] 客户数据")
try:
    custs = req("GET", "/api/customers", token=tok).get("items") or []
    names = [c["name"] for c in custs]
    check("种子客户 张三/李四/王五", {"张三", "李四", "王五"}.issubset(set(names)), f"实际 {names}")
except Exception as e:
    check("GET /api/customers", False, str(e))

# ---- 5. 新增用户（核心需求 D）----
print("\n[5] 新增用户")
newuser = "verify_qa_01"
try:
    r = req("POST", "/api/auth/register",
            {"username": newuser, "password": "verify123456",
             "full_name": "验证用账号", "role": "operator"}, token=tok)
    check("POST /api/auth/register 返回成功", r.get("code") == 0, f"message={r.get('message')} id={(r.get('data') or {}).get('id')}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    if "已存在" in body:
        check("POST /api/auth/register（账号已存在，视为通过）", True)
    else:
        check("POST /api/auth/register", False, f"HTTP {e.code} {body[:120]}")
except Exception as e:
    check("POST /api/auth/register", False, str(e))

# ---- 6. 用新账号登录（证明数据真的落库可用）----
print("\n[6] 新账号可登录（证明已落库）")
try:
    tok2 = req("POST", "/api/auth/login",
               {"username": newuser, "password": "verify123456"}, form=True)["access_token"]
    check("新账号登录成功", bool(tok2))
except Exception as e:
    check("新账号登录", False, str(e))

# ---- 7. 工具直测（真实调用高德天气）----
print("\n[7] 工具在线测试（真实调用外部 API）")
try:
    tools = req("GET", "/api/tools", token=tok).get("data") or []
    weather = next((t for t in tools if t["name"] == "amap_weather"), None)
    if weather is None:
        check("找到 amap_weather", False)
    else:
        r = req("POST", f"/api/tools/{weather['id']}/test",
                {"params": {"city": "北京"}}, token=tok)
        d = r.get("data") or {}
        ok = bool(d.get("success"))
        check("amap_weather 调用成功", ok, (str(d.get("result") or d.get("error"))[:100]))
except Exception as e:
    check("工具在线测试", False, str(e))

print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
print(f"结果：{passed}/{len(results)} 项通过")
print("=" * 60)
