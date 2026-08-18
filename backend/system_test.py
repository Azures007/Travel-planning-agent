"""系统全面测试：覆盖成功、失败、边界情况。"""
import httpx
import json

BASE = "http://localhost:8000"
results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name} {detail}")


def run_tests():
    with httpx.Client(base_url=BASE, timeout=15.0) as c:
        # ========== 1. 健康检查 ==========
        r = c.get("/api/health")
        check("健康检查", r.status_code == 200 and r.json().get("status") == "ok")
        check("响应头含RequestID", "x-request-id" in r.headers)

        # ========== 2. 会话 CRUD ==========
        # 创建
        r = c.post("/api/sessions", json={})
        sid = r.json().get("id")
        check("创建会话", r.status_code == 200 and sid is not None, f"id={sid}")

        # 列表
        r = c.get("/api/sessions")
        check("会话列表", r.status_code == 200 and isinstance(r.json(), list))

        # 获取详情
        r = c.get(f"/api/sessions/{sid}")
        check("会话详情", r.status_code == 200 and r.json()["id"] == sid)

        # 重命名
        r = c.patch(f"/api/sessions/{sid}", json={"title": "测试行程"})
        check("重命名会话", r.status_code == 200 and r.json()["title"] == "测试行程")

        # ========== 3. 边界：不存在的会话 ==========
        r = c.get("/api/sessions/999999")
        check("获取不存在会话", r.status_code in (200, 404),
              f"status={r.status_code}")

        # ========== 4. 地理编码 ==========
        # 正常查询
        r = c.post("/api/geocode/batch",
                   json={"locations": ["五店市传统街区", "安平桥"], "destination": "晋江"})
        data = r.json()
        found = sum(1 for x in data if x.get("lat"))
        check("地理编码-正常", r.status_code == 200 and found == 2, f"{found}/2")

        # 缓存命中（第二次应该很快）
        import time
        start = time.time()
        r = c.post("/api/geocode/batch",
                   json={"locations": ["五店市传统街区", "安平桥"], "destination": "晋江"})
        elapsed = time.time() - start
        cached = sum(1 for x in r.json() if x.get("cached"))
        check("地理编码-缓存命中", cached == 2 and elapsed < 2.0,
              f"cached={cached}, {elapsed:.2f}s")

        # 边界：空列表
        r = c.post("/api/geocode/batch",
                   json={"locations": [], "destination": "晋江"})
        check("地理编码-空列表", r.status_code == 200 and r.json() == [])

        # 边界：不存在的地点
        r = c.post("/api/geocode/batch",
                   json={"locations": ["这个地方根本不存在xyz123"], "destination": "晋江"})
        check("地理编码-无效地点", r.status_code == 200)

        # ========== 5. 参数验证 ==========
        # 缺少必填字段
        r = c.post("/api/geocode/batch", json={"locations": ["test"]})
        check("参数验证-缺字段", r.status_code == 422, f"status={r.status_code}")

        # ========== 6. 导出（需先有行程，这里测试404）==========
        r = c.get(f"/api/export/{sid}/html")
        check("导出HTML-无行程", r.status_code == 404, f"status={r.status_code}")

        r = c.get(f"/api/export/{sid}/markdown")
        check("导出MD-无行程", r.status_code == 404, f"status={r.status_code}")

        # ========== 7. 分享链接 ==========
        r = c.get(f"/api/export/{sid}/share")
        check("分享链接", r.status_code == 200 and "url" in r.json())

        # ========== 8. 清理：删除测试会话 ==========
        r = c.delete(f"/api/sessions/{sid}")
        check("删除会话", r.status_code == 200)

        # 确认已删除
        r = c.get(f"/api/sessions/{sid}")
        deleted = r.status_code == 404 or (
            r.status_code == 200 and r.json().get("error")
        )
        check("确认删除", deleted, f"status={r.status_code}")

    # ========== 汇总 ==========
    print("\n" + "=" * 50)
    passed = sum(1 for s, _, _ in results if s == "PASS")
    total = len(results)
    print(f"测试结果: {passed}/{total} 通过")
    failed = [(n, d) for s, n, d in results if s == "FAIL"]
    if failed:
        print("\n失败项:")
        for n, d in failed:
            print(f"  - {n} {d}")
    else:
        print("全部通过！")


if __name__ == "__main__":
    run_tests()
