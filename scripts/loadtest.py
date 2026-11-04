#!/usr/bin/env python3
"""Kiểm thử tải AI Study Agent (đối chiếu API nhánh main, 01/11/2026).

Chỉ chạy trên bản sao dữ liệu / máy thử nghiệm. Script KHÔNG sửa code hệ thống.
Cài đặt: pip install requests

Bước 1 (thử ít tải, chỉ GET, không gọi AI):
    python scripts/loadtest.py --users 2 --requests 3 --runs 1 --allow-setup-writes

Bước 2 (đo chính thức, sau khi thử ổn):
    python scripts/loadtest.py --users 10 25 50 --requests 20 --runs 3 --allow-setup-writes

Tùy chọn Chat AI thật, tốn quota và ghi lịch sử chat vào database TEST:
    python scripts/loadtest.py --users 1 --requests 1 --runs 1 --chat --chat-users 1 --chat-requests 2 --allow-setup-writes

Kết quả: ketqua_hieunang/tonghop.md, tonghop.csv, chitiet.csv, thongtin.json.
Chạy lần đầu cần --allow-setup-writes để tạo tài khoản/môn TEST trong database.
Không đo tải production. Không coi HTTP 200 của Chat là bằng chứng nội dung AI đúng.
"""

import argparse
import csv
import json
import math
import os
import platform
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

PASSWORD = "LoadTest-2026-Pass"  # CHỈ dành cho database thử nghiệm.
SUBJECT = {
    "name": "Cấu trúc dữ liệu và giải thuật",
    "code": "CTDL01",
    "description": "Môn dùng để đo hiệu năng",
    "credits": 3,
    "target_score": 8,
}
QUESTIONS = [
    "Danh sách liên kết đơn khác mảng ở điểm nào?",
    "Độ phức tạp thời gian của tìm kiếm nhị phân là bao nhiêu?",
    "Ngăn xếp và hàng đợi khác nhau thế nào?",
    "Cây nhị phân tìm kiếm cân bằng có lợi gì?",
]
READ_SCENARIOS = [
    ("Dashboard (API Mobile)", "GET", "/api/mobile/dashboard"),
    ("Danh sách môn học", "GET", "/api/mobile/subjects"),
    ("Danh sách tài liệu", "GET", "/api/mobile/documents"),
    ("Thời khóa biểu (Web)", "GET", "/study-plan"),
]


def percentile(values, p):
    if not values:
        return float("nan")
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * p / 100.0
    lo = int(index)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (index - lo)


def require_json(response, context):
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"{context}: phản hồi không phải JSON (HTTP {response.status_code})") from exc


class VirtualUser:
    def __init__(self, base, index, allow_setup_writes):
        self.base = base.rstrip("/")
        self.index = index
        self.allow_setup_writes = allow_setup_writes
        self.email = f"loadtest_{index}@example.local"
        self.http = requests.Session()  # mỗi người giữ cookie phiên độc lập
        self.subject_id = None
        self.conversation_id = None

    def _call(self, method, path, *, json_body=None, timeout=30):
        return self.http.request(
            method, self.base + path, json=json_body,
            timeout=timeout, allow_redirects=False,
        )

    def setup(self, need_chat=False):
        """Tạo hoặc đăng nhập test user. Không tính thời gian setup vào kết quả đo."""
        login = {"email": self.email, "password": PASSWORD}
        response = self._call("POST", "/api/mobile/login", json_body=login)
        if response.status_code == 401:
            if not self.allow_setup_writes:
                raise RuntimeError(
                    f"Chưa có {self.email}. Dùng --allow-setup-writes trên DATABASE BẢN SAO "
                    "để cho phép tạo tài khoản test."
                )
            response = self._call(
                "POST", "/api/mobile/register",
                json_body={**login, "name": f"Load Test {self.index}"},
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Không đăng nhập/đăng ký được {self.email}: "
                f"HTTP {response.status_code} {response.text[:160]}"
            )

        response = self._call("GET", "/api/mobile/subjects")
        if response.status_code != 200:
            raise RuntimeError(f"Không lấy được danh sách môn: HTTP {response.status_code}")
        subjects_payload = require_json(response, "Danh sách môn")
        # Nhánh main trả thẳng một MẢNG, không phải {'subjects': [...]}.
        if isinstance(subjects_payload, list):
            subjects = subjects_payload
        elif isinstance(subjects_payload, dict) and isinstance(subjects_payload.get("subjects"), list):
            subjects = subjects_payload["subjects"]
        else:
            raise RuntimeError("API /api/mobile/subjects trả định dạng không được hỗ trợ.")

        chosen = next(
            (s for s in subjects if isinstance(s, dict) and s.get("code") == SUBJECT["code"]),
            None,
        )
        # Đã có môn khác thì có thể dùng lại khi chỉ đo tải đọc; dùng môn đúng cho Chat.
        if chosen is None and subjects and not need_chat:
            chosen = next((s for s in subjects if isinstance(s, dict) and s.get("id")), None)
        if chosen is not None:
            self.subject_id = chosen.get("id")
        else:
            if not self.allow_setup_writes:
                raise RuntimeError(
                    f"Tài khoản {self.email} chưa có môn phù hợp; "
                    "dùng --allow-setup-writes trên DATABASE BẢN SAO."
                )
            created = self._call("POST", "/api/mobile/subjects", json_body=SUBJECT)
            if created.status_code != 201:
                raise RuntimeError(
                    f"Không tạo được môn cho {self.email}: "
                    f"HTTP {created.status_code} {created.text[:160]}"
                )
            payload = require_json(created, "Tạo môn")
            self.subject_id = (payload.get("subject") or {}).get("id") if isinstance(payload, dict) else None
        if not self.subject_id:
            raise RuntimeError(f"Không xác định được subject_id của {self.email}.")

        if need_chat:
            response = self._call("GET", f"/api/mobile/chat/{self.subject_id}")
            if response.status_code != 200:
                raise RuntimeError(
                    f"Không lấy được hội thoại của {self.email}: HTTP {response.status_code} "
                    f"{response.text[:150]}"
                )
            payload = require_json(response, "Hội thoại môn học")
            self.conversation_id = payload.get("conversation_id") if isinstance(payload, dict) else None
            if not isinstance(self.conversation_id, int) or self.conversation_id <= 0:
                raise RuntimeError("Thiếu conversation_id trong API /api/mobile/chat/<subject_id>.")

    def hit(self, method, path, body=None, timeout=30):
        """Trả về (thời gian tính giây, HTTP 2xx, lỗi). Không retry gây sai số đo."""
        start = time.perf_counter()
        try:
            response = self._call(method, path, json_body=body, timeout=timeout)
            elapsed = time.perf_counter() - start
            ok = 200 <= response.status_code < 300
            return elapsed, ok, "" if ok else f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            return time.perf_counter() - start, False, "timeout"
        except requests.exceptions.RequestException as exc:
            return time.perf_counter() - start, False, type(exc).__name__


def run_level(users, scenario, request_count, run_number, *, warmup=True):
    """Gửi đồng thời, có đồng bộ điểm bắt đầu và không treo khi worker bị lỗi."""
    name, method, path, body_factory, timeout = scenario
    gate = threading.Barrier(len(users) + 1, timeout=90)
    results = [[] for _ in users]
    failures = []
    errors_lock = threading.Lock()

    def worker(i, user):
        try:
            # Chỉ làm nóng GET. Không gọi AI thừa ngoài số lần đã cấu hình.
            if warmup:
                user.hit(method, path, None, timeout)
            gate.wait()
            for j in range(request_count):
                payload = body_factory(user, j) if callable(body_factory) else body_factory
                elapsed, ok, error = user.hit(method, path, payload, timeout)
                results[i].append((elapsed, ok, error))
        except Exception as exc:
            with errors_lock:
                failures.append(f"{user.email}: {type(exc).__name__}: {exc}")
            gate.abort()

    threads = [threading.Thread(target=worker, args=(i, user), daemon=True)
               for i, user in enumerate(users)]
    for thread in threads:
        thread.start()
    try:
        gate.wait()
    except threading.BrokenBarrierError as exc:
        for thread in threads:
            thread.join(timeout=1)
        raise RuntimeError("Không thể đồng bộ các người dùng: " + "; ".join(failures)) from exc
    start = time.perf_counter()
    for thread in threads:
        thread.join(timeout=request_count * timeout + 30)
    wall_seconds = time.perf_counter() - start
    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("Có luồng chưa kết thúc trong thời hạn; không ghi số liệu không đầy đủ.")
    if failures:
        raise RuntimeError("Lỗi luồng kiểm thử: " + "; ".join(failures))
    if sum(len(batch) for batch in results) != len(users) * request_count:
        raise RuntimeError("Mất mẫu kiểm thử; đã hủy thay vì ghi bảng thiếu.")
    rows = [(run_number, name, len(users), dt, ok, error)
            for batch in results for dt, ok, error in batch]
    return rows, wall_seconds


def summarize(rows, walls):
    all_latencies = [r[3] * 1000 for r in rows]
    successful = [r[3] * 1000 for r in rows if r[4]]
    count = len(rows)
    errors = count - len(successful)
    total_wall = sum(walls)
    return {
        "mau": count,
        "thanh_cong": len(successful),
        # Nếu không có request nào thành công, KHÔNG lấy độ trễ lỗi để giả làm p50/p95.
        "p50_ms": percentile(successful, 50),
        "p95_ms": percentile(successful, 95),
        "max_ms": max(all_latencies) if all_latencies else float("nan"),
        "loi_pct": 100 * errors / count if count else float("nan"),
        "thong_luong": len(successful) / total_wall if total_wall > 0 else float("nan"),
    }


def number(value, digits=1):
    return f"{value:.{digits}f}" if math.isfinite(value) else "N/A"


def save_results(out_dir, all_rows, summaries, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "chitiet.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["luot", "kich_ban", "nguoi_dung", "do_tre_giay", "thanh_cong", "loi"])
        writer.writerows((r[0], r[1], r[2], number(r[3], 5), int(r[4]), r[5]) for r in all_rows)

    cols = ["kich_ban", "nguoi_dung", "mau", "thanh_cong", "p50_ms",
            "p95_ms", "max_ms", "loi_pct", "thong_luong"]
    with (out_dir / "tonghop.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for item in summaries:
            writer.writerow([item["kich_ban"], item["nguoi_dung"], item["mau"],
                             item["thanh_cong"], number(item["p50_ms"]),
                             number(item["p95_ms"]), number(item["max_ms"]),
                             number(item["loi_pct"], 2), number(item["thong_luong"], 2)])

    with (out_dir / "tonghop.md").open("w", encoding="utf-8") as f:
        f.write("# Kết quả kiểm thử hiệu năng AI Study Agent\n\n")
        f.write(f"- Thời điểm bắt đầu: {meta['thoi_diem_bat_dau']}\n")
        f.write(f"- Địa chỉ máy chủ test: {meta['base_url']}\n")
        f.write(f"- Ghi chú máy chủ / commit: {meta['ghi_chu'] or 'CHƯA CUNG CẤP'}\n")
        f.write("- p50/p95 chỉ tính trên HTTP thành công (2xx); HTTP lỗi được tính riêng.\n")
        f.write("- Độ trễ bao gồm HTTP tổng thể, **không phải** TTFB; thông lượng là yêu cầu 2xx/giây.\n")
        f.write("- Kết quả thể hiện môi trường đo và kịch bản; không phải năng lực triển khai Internet.\n\n")
        f.write("| Kịch bản | Người đồng thời | Số mẫu | Thành công | p50 (ms) | p95 (ms) | Max (ms, mọi yêu cầu) | Lỗi (%) | Thành công/giây |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for s in summaries:
            f.write(f"| {s['kich_ban']} | {s['nguoi_dung']} | {s['mau']} | {s['thanh_cong']} | "
                    f"{number(s['p50_ms'], 0)} | {number(s['p95_ms'], 0)} | "
                    f"{number(s['max_ms'], 0)} | {number(s['loi_pct'], 2)} | "
                    f"{number(s['thong_luong'], 2)} |\n")
        if meta["tham_so"]["chat"]:
            f.write("\n**Lưu ý Chat:** HTTP 2xx không chứng minh nội dung AI chính xác/đúng nguồn; "
                    "tốc độ bị ảnh hưởng bởi quota/dịch vụ AI, bộ nhớ đệm và lịch sử hội thoại.\n")

    with (out_dir / "thongtin.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, allow_nan=False)


def positive_int(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError("Giá trị phải >= 1")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--users", type=positive_int, nargs="+", default=[10, 25, 50])
    parser.add_argument("--requests", type=positive_int, default=20)
    parser.add_argument("--runs", type=positive_int, default=3)
    parser.add_argument("--chat", action="store_true", help="Gọi Chat AI THẬT, tốn quota và ghi lịch sử")
    parser.add_argument("--chat-users", type=positive_int, nargs="+", default=[1, 5])
    parser.add_argument("--chat-requests", type=positive_int, default=4)
    parser.add_argument("--allow-setup-writes", action="store_true",
                        help="Cho phép tạo tài khoản/môn thử nghiệm trên DB BẢN SAO")
    parser.add_argument("--allow-remote", action="store_true",
                        help="Cho phép URL không phải localhost (chỉ dùng máy thử nghiệm riêng)")
    parser.add_argument("--out", default="ketqua_hieunang")
    parser.add_argument("--note", default="", help="Môi trường Flask, CPU/RAM máy chủ, commit, mạng...")
    args = parser.parse_args(argv)

    parsed = urlsplit(args.base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        parser.error("--base-url phải là HTTP(S) URL hợp lệ")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        parser.error("--base-url chỉ chứa scheme + host + port; không gồm đường dẫn/query/credentials")
    if parsed.hostname not in ("localhost", "127.0.0.1", "::1") and not args.allow_remote:
        parser.error("Mặc định chỉ đo localhost. Nếu là server TEST riêng, thêm --allow-remote.")
    if max(args.users + (args.chat_users if args.chat else [])) > 200:
        parser.error("Giới hạn an toàn tối đa là 200 người dùng đồng thời")

    started = datetime.now().isoformat(timespec="seconds")
    max_users = max(args.users + (args.chat_users if args.chat else []))
    print(f"Chuẩn bị {max_users} tài khoản test; Chat AI {'BẬT' if args.chat else 'TẮT'}.")
    print("Chỉ dùng database BẢN SAO. Không chạy trên dữ liệu sinh viên thật.")
    pool = []
    try:
        for index in range(max_users):
            user = VirtualUser(args.base_url, index, args.allow_setup_writes)
            user.setup(need_chat=args.chat and index < max(args.chat_users))
            pool.append(user)
    except (requests.exceptions.RequestException, RuntimeError) as exc:
        parser.exit(2, f"Không thể chuẩn bị dữ liệu test: {exc}\n")

    all_rows, summary = [], []

    def measure(scenario, levels, n_requests, *, warmup):
        for level in levels:
            rows, durations = [], []
            for run_no in range(1, args.runs + 1):
                batch, wall = run_level(pool[:level], scenario, n_requests, run_no, warmup=warmup)
                rows.extend(batch)
                durations.append(wall)
                print(f"  {scenario[0]} | {level} người | lượt {run_no}/{args.runs} | "
                      f"{len(batch)} yêu cầu | {wall:.2f}s")
            all_rows.extend(rows)
            item = summarize(rows, durations)
            item.update({"kich_ban": scenario[0], "nguoi_dung": level})
            summary.append(item)

    try:
        for name, method, path in READ_SCENARIOS:
            print(f"Kịch bản: {name}")
            measure((name, method, path, None, 30), args.users, args.requests, warmup=True)

        if args.chat:
            print("Kịch bản: Chat AI theo môn (/api/chat, API thật, không warm-up)")

            def chat_body(user, k):
                return {
                    "conversation_id": user.conversation_id,
                    "question": QUESTIONS[(user.index + k) % len(QUESTIONS)],
                }

            measure(("Chat AI theo môn", "POST", "/api/chat", chat_body, 120),
                    args.chat_users, args.chat_requests, warmup=False)
    finally:
        for user in pool:
            user.http.close()

    metadata = {
        "thoi_diem_bat_dau": started,
        "thoi_diem_ket_thuc": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "tham_so": {
            "users": args.users,
            "requests_moi_nguoi": args.requests,
            "so_luot": args.runs,
            "chat": args.chat,
            "chat_users": args.chat_users if args.chat else None,
            "chat_requests": args.chat_requests if args.chat else None,
            "allow_setup_writes": args.allow_setup_writes,
        },
        "may_do": {
            "he_dieu_hanh": platform.platform(),
            "python": platform.python_version(),
            "cpu": platform.processor() or platform.machine(),
            "so_nhan_cpu": os.cpu_count(),
        },
        "ghi_chu": args.note,
        "luu_y": "p50/p95 tính trên yêu cầu HTTP 2xx; lỗi tính riêng; tốc độ HTTP không phải TTFB.",
    }
    save_results(Path(args.out), all_rows, summary, metadata)
    print(f"XONG. Bảng kết quả: {Path(args.out) / 'tonghop.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())