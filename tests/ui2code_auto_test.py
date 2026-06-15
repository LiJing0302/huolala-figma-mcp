#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UI2Code 自动化测试脚本
批量跑 Figma 链接，输出 Markdown 报告，并用 SQLite 记录每个链接的历史最大 SSIM 与像素相似度。

额外依赖（仅本脚本需要，生产环境不必安装）：
  pip install ".[ui2code-test]"
  playwright install chromium

运行（在项目根目录）：
  python tests/ui2code_auto_test.py
"""
import asyncio
import html
import json
import sys
import os
import logging
import zipfile
import requests
import shutil
import sqlite3
import time
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# 项目根目录与 src 加入 Python 路径（脚本位于 tests/ 下）
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_TESTS_DIR)
_SRC_PATH = os.path.join(_PROJECT_ROOT, "src")
sys.path.insert(0, _SRC_PATH)
sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from PIL import Image
from mdap_u2c.config.http_config import get_http_timeout, get_ssl_verify
from mdap_u2c.services.ui2code_service import UI2CodeService
from compare_html_with_origin import compare_html_with_origin_local
from fastmcp import Context


# 测试输出目录（报告、SQLite、各 node 产物）
_OUTPUT_DIR = os.path.join(_TESTS_DIR, "output_dir")


# SQLite 数据库路径（与测试输出目录一致）
def _db_path() -> str:
    return os.path.join(_OUTPUT_DIR, "ui2code_auto_test.db")


def get_simplified_url_key(url: str) -> str:
    """
    精简 URL 作为 DB key：只保留 query 中的 node-id 参数值。
    例如: ...?node-id=148-4774&t=xxx -> 148-4774
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        node_id = params.get('node-id', [None])[0]
        if node_id:
            return node_id.replace(':', '-')
        return ""
    except Exception as e:
        logging.warning(f"无法从 URL 提取 node-id: {url}, 错误: {e}")
        return ""


def init_sqlite(project_root: str) -> sqlite3.Connection:
    """初始化 SQLite，建表（key = 简化 URL，即 node-id 值）"""
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    conn = sqlite3.connect(_db_path())
    conn.execute("""
        CREATE TABLE IF NOT EXISTS url_history (
            key TEXT PRIMARY KEY,
            max_ssim REAL DEFAULT 0,
            max_pixel_similarity REAL DEFAULT 0,
            updated_at TEXT
        )
    """)
    conn.commit()
    return conn


def get_historical_max(conn: sqlite3.Connection, key: str) -> tuple:
    """查询 key 对应的历史最大 ssim 和像素相似度。返回 (max_ssim, max_pixel_similarity)。"""
    if not key:
        return (0.0, 0.0)
    row = conn.execute(
        "SELECT max_ssim, max_pixel_similarity FROM url_history WHERE key = ?",
        (key,)
    ).fetchone()
    if row is None:
        return (0.0, 0.0)
    return (float(row[0] or 0), float(row[1] or 0))


def update_historical_max(
    conn: sqlite3.Connection,
    key: str,
    ssim: float,
    pixel_similarity: float,
) -> None:
    """用本次运行的 ssim、像素相似度更新历史最大值（只增不减）。"""
    if not key:
        return
    now = datetime.now().isoformat()
    conn.execute("""
        INSERT INTO url_history (key, max_ssim, max_pixel_similarity, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            max_ssim = max(max_ssim, excluded.max_ssim),
            max_pixel_similarity = max(max_pixel_similarity, excluded.max_pixel_similarity),
            updated_at = excluded.updated_at
    """, (key, ssim, pixel_similarity, now))
    conn.commit()


class MockMcpContext(Context):
    """模拟 MCP Context"""

    def __init__(self):
        pass

    async def report_progress(self, progress: int, total: int, message: str):
        print(f"  [Progress {progress}/{total}] {message}")

    def get_state(self, key: str):
        if key == "login_user_info":
            return {
                "name_en": "debug_test",
                "name_cn": "调试测试用户",
                "client_id": "debug_client_id",
            }
        return None


def extract_node_id_from_url(url: str) -> str | None:
    """从 URL 中提取 node-id 参数（用于目录名等）。"""
    key = get_simplified_url_key(url)
    return key if key else None


def read_urls_from_file(file_path: str) -> list[str]:
    """从文件中读取所有 URL"""
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
        return urls
    except FileNotFoundError:
        logging.error(f"文件不存在: {file_path}")
        return []
    except Exception as e:
        logging.error(f"读取文件失败: {file_path}, 错误: {e}")
        return []


def process_single_url_complete(
    url: str,
    project_root: str,
    conn: sqlite3.Connection,
) -> dict:
    """完整处理单个 URL：转换、下载、解压、生成 HTML、计算相似度，并记录耗时。"""
    start_time = time.perf_counter()
    print("\n" + "=" * 60)
    print(f"开始处理URL: {url}")

    node_id = extract_node_id_from_url(url)
    if not node_id:
        node_id = "unknown"
        logging.warning(f"URL 没有 node-id，使用默认名称: {node_id}")

    url_key = get_simplified_url_key(url)
    print(f"Node ID: {node_id}")

    # 步骤1: UI2Code 转换
    print("\n[步骤1] 开始执行 UI2Code 转换...")
    service = UI2CodeService(url=url, target_platform="h5",image_scale=[3])
    service.set_mcp_context(MockMcpContext())
    try:
        zip_url, _ = asyncio.run(
            service.run(file_key=None, node_id=None)
        )
    except Exception as e:
        duration = time.perf_counter() - start_time
        logging.exception("UI2Code 转换异常:")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": str(e),
            "duration_seconds": round(duration, 2),
        }

    if not zip_url:
        duration = time.perf_counter() - start_time
        print("❌ 转换失败，请查看日志了解详情。")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": "转换失败",
            "duration_seconds": round(duration, 2),
        }

    print(f"✅ 转换成功! ZIP 文件链接: {zip_url}")

    # 步骤2: 下载和解压
    print("\n[步骤2] 开始下载和解压...")
    output_base_dir = os.path.join(_OUTPUT_DIR, node_id)

    if os.path.exists(output_base_dir):
        shutil.rmtree(output_base_dir, ignore_errors=True)
    os.makedirs(output_base_dir, exist_ok=True)
    zip_path = os.path.join(output_base_dir, "downloaded.zip")

    try:
        print("📥 开始下载 zip 文件...")
        response = requests.get(
            zip_url,
            stream=True,
            verify=get_ssl_verify(),
            timeout=get_http_timeout(default=120),
        )
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"✅ zip 文件下载完成: {zip_path}")

        zip_filename = os.path.basename(zip_path)
        for item in os.listdir(output_base_dir):
            if item == zip_filename:
                continue
            item_path = os.path.join(output_base_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path, ignore_errors=True)
            else:
                try:
                    os.remove(item_path)
                except Exception:
                    pass

        print(f"📦 开始解压 zip 到: {output_base_dir}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(output_base_dir)
        os.remove(zip_path)
        print("✅ zip 解压完成，已删除临时 zip")

        nested_mdap_dir = os.path.join(output_base_dir, "mdap_u2c")
        if os.path.exists(nested_mdap_dir) and os.path.isdir(nested_mdap_dir):
            for item in os.listdir(nested_mdap_dir):
                src = os.path.join(nested_mdap_dir, item)
                dst = os.path.join(output_base_dir, item)
                if os.path.exists(dst):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    else:
                        os.remove(dst)
                shutil.move(src, dst)
            os.rmdir(nested_mdap_dir)

    except requests.RequestException as e:
        duration = time.perf_counter() - start_time
        print(f"❌ 下载 zip 失败: {str(e)}")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": f"下载失败: {str(e)}",
            "duration_seconds": round(duration, 2),
        }
    except zipfile.BadZipFile as e:
        duration = time.perf_counter() - start_time
        print(f"❌ zip 格式错误: {str(e)}")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": f"zip 格式错误: {str(e)}",
            "duration_seconds": round(duration, 2),
        }
    except Exception as e:
        duration = time.perf_counter() - start_time
        print(f"❌ 下载/解压错误: {str(e)}")
        logging.exception("详细错误信息:")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": str(e),
            "duration_seconds": round(duration, 2),
        }

    # 步骤3: 图像相似度
    print("\n[步骤3] 计算图像相似度...")
    dsl_file = None
    for root, dirs, files in os.walk(output_base_dir):
        for file in files:
            if file == "dsl.json":
                dsl_file = os.path.join(root, file)
                break
        if dsl_file:
            break

    if not dsl_file:
        duration = time.perf_counter() - start_time
        print("❌ 未找到 dsl.json")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": "未找到 dsl.json",
            "duration_seconds": round(duration, 2),
        }

    try:
        result = compare_html_with_origin_local(dsl_file, output_base_dir)
        ssim = result["ssim"]
        absdiff = result["absdiff"]
        # 像素相似度使用与 compare 一致的 absdiff（0-1，越大越相似）
        pixel_similarity = absdiff

        duration = time.perf_counter() - start_time

        print(f"\n{'='*50}")
        print("📊 图像相似度:")
        print(f"  SSIM: {ssim}, 像素相似度(absdiff): {pixel_similarity}")
        print(f"  原始尺寸: {result['origin_size']}, 渲染尺寸: {result['rendered_size']}")
        print(f"{'='*50}")

        result_filename = f"ssim_{ssim:.4f}_absdiff_{absdiff:.4f}.json"
        result_filepath = os.path.join(output_base_dir, result_filename)
        with open(result_filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"💾 结果已保存: {result_filepath}")

        # 更新 SQLite 历史最大 SSIM 与像素相似度
        update_historical_max(conn, url_key, ssim, pixel_similarity)

        compare_dir = os.path.join(output_base_dir, "compare")
        origin_cropped_path = os.path.join(compare_dir, "origin_cropped.png")
        rendered_path = os.path.join(compare_dir, "rendered.png")
        diff_path = os.path.join(compare_dir, "diff.png")
        # 相对路径便于报告内引用
        rel = lambda p: os.path.relpath(p, project_root) if os.path.exists(p) else ""
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": True,
            "ssim": ssim,
            "absdiff": absdiff,
            "pixel_similarity": pixel_similarity,
            "output_dir": output_base_dir,
            "duration_seconds": round(duration, 2),
            "origin_cropped": rel(origin_cropped_path),
            "rendered": rel(rendered_path),
            "diff": rel(diff_path),
        }
    except Exception as e:
        duration = time.perf_counter() - start_time
        print(f"❌ 计算相似度错误: {str(e)}")
        logging.exception("详细错误信息:")
        return {
            "node_id": node_id,
            "url_key": url_key,
            "url": url,
            "success": False,
            "error": str(e),
            "duration_seconds": round(duration, 2),
        }


def generate_html_report(
    results: list[dict],
    conn: sqlite3.Connection,
    output_dir: str,
) -> str:
    """
    生成 HTML 报告，包含：
    1）整体成功率、失败数量、SSIM ≥ 90% 的设计稿数量
    2）失败链接与原因/堆栈
    3）运行详情表：node-id, ssim, 历史最高ssim, 像素相似度, 历史最高像素相似度, 三张对比图, 运行耗时, 链接
    """
    success_list = [r for r in results if r.get("success")]
    failed_list = [r for r in results if not r.get("success")]
    total = len(results)
    success_count = len(success_list)
    failed_count = len(failed_list)
    success_rate = (success_count / total * 100) if total else 0
    ssim_over_90 = sum(1 for r in success_list if r.get("ssim", 0) >= 0.90)
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 整体统计
    stats_html = f"""
    <h2>1. 整体统计</h2>
    <ul>
        <li><strong>总数</strong>: {total}</li>
        <li><strong>成功</strong>: {success_count}</li>
        <li><strong>失败</strong>: {failed_count}</li>
        <li><strong>成功率</strong>: {success_rate:.1f}%</li>
        <li><strong>SSIM ≥ 90% 的设计稿数量</strong>: {ssim_over_90}</li>
    </ul>"""

    # 2. 失败链接与原因
    if failed_list:
        fail_items = []
        for r in failed_list:
            url = r.get("url", "")
            err = r.get("error", "未知错误")
            url_esc = html.escape(url)
            err_esc = html.escape(err)
            fail_items.append(
                f'<li><strong>链接</strong>: <a href="{url_esc}" target="_blank" rel="noopener">figma地址</a><br/>'
                f'<strong>原因/堆栈</strong>: <pre>{err_esc}</pre></li>'
            )
        fail_html = "<h2>2. 失败链接与原因</h2><ul>" + "".join(fail_items) + "</ul>"
    else:
        fail_html = "<h2>2. 失败链接与原因</h2><p>无失败记录。</p>"

    # 3. 运行详情表
    rows_html = []
    for r in results:
        node_id = html.escape(r.get("node_id", "-"))
        url = r.get("url", "")
        url_esc = html.escape(url)
        url_cell = f'<a href="{url_esc}" target="_blank" rel="noopener">figma地址</a>' if url else "-"
        duration = r.get("duration_seconds", "-")

        out_dir = r.get("output_dir", "")
        if out_dir:
            o_path = os.path.relpath(os.path.join(out_dir, "compare", "origin_cropped.png"), output_dir) if os.path.exists(os.path.join(out_dir, "compare", "origin_cropped.png")) else ""
            r_path = os.path.relpath(os.path.join(out_dir, "compare", "rendered.png"), output_dir) if os.path.exists(os.path.join(out_dir, "compare", "rendered.png")) else ""
            d_path = os.path.relpath(os.path.join(out_dir, "compare", "diff.png"), output_dir) if os.path.exists(os.path.join(out_dir, "compare", "diff.png")) else ""
        else:
            o_path, r_path, d_path = "", "", ""

        _w = 375
        _h = 400
        if o_path:
            _origin_full = os.path.join(out_dir, "compare", "origin_cropped.png")
            if os.path.exists(_origin_full):
                try:
                    _img_w, _img_h = Image.open(_origin_full).size
                    _h = _img_h
                except Exception:
                    pass
        _img_style = f'width:{_w}px;height:{_h}px;object-fit:contain;display:block;'
        _td_img_style = f'width:{_w}px;min-width:{_w}px;box-sizing:border-box;vertical-align:top;'

        def _img_cell(path: str, alt: str) -> str:
            if not path:
                return "-"
            return f'<img src="{html.escape(path)}" style="{_img_style}" alt="{html.escape(alt)}" />'

        origin_cropped_cell = _img_cell(o_path, "裁剪原图")
        rendered_cell = _img_cell(r_path, "渲染图")
        diff_cell = _img_cell(d_path, "差异图")

        if r.get("success"):
            ssim = r.get("ssim", 0)
            pixel = r.get("pixel_similarity", 0)
            key = r.get("url_key", "") or node_id if node_id != "unknown" else ""
            hist_ssim, hist_pixel = get_historical_max(conn, key)
            ssim_cell = f"{ssim:.4f} (历史最高 {hist_ssim:.4f})"
            pixel_cell = f"{pixel:.4f} (历史最高 {hist_pixel:.4f})"
            rows_html.append(f"""
                <tr>
                    <td style="{_td_img_style}">{origin_cropped_cell}</td>
                    <td style="{_td_img_style}">{rendered_cell}</td>
                    <td style="{_td_img_style}">{diff_cell}</td>
                    <td>{ssim_cell}</td>
                    <td>{pixel_cell}</td>
                    <td>{duration}</td>
                    <td>{url_cell}</td>
                </tr>""")
        else:
            key = r.get("url_key", "") or (node_id if node_id != "unknown" else "")
            hist_ssim, hist_pixel = get_historical_max(conn, key)
            hist_ssim_s = f"{hist_ssim:.4f}" if hist_ssim > 0 else "-"
            hist_pixel_s = f"{hist_pixel:.4f}" if hist_pixel > 0 else "-"
            ssim_cell = f"- (历史最高 {hist_ssim_s})"
            pixel_cell = f"- (历史最高 {hist_pixel_s})"
            rows_html.append(f"""
                <tr>
                    <td style="{_td_img_style}">{origin_cropped_cell}</td>
                    <td style="{_td_img_style}">{rendered_cell}</td>
                    <td style="{_td_img_style}">{diff_cell}</td>
                    <td>{ssim_cell}</td>
                    <td>{pixel_cell}</td>
                    <td>{duration}</td>
                    <td>{url_cell}</td>
                </tr>""")

    table_html = f"""
    <h2>3. 运行详情</h2>
    <table class="report-table">
        <thead>
            <tr>
                <th>原始设计稿图</th>
                <th>实际渲染图</th>
                <th>差分图</th>
                <th>结构相似度</th>
                <th>像素相似度</th>
                <th>运行耗时(s)</th>
                <th>链接地址</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows_html)}
        </tbody>
    </table>"""

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>UI2Code 自动化测试报告</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 24px; color: #333; }}
        h1 {{ margin-bottom: 0.25em; }}
        .meta {{ color: #666; margin-bottom: 24px; }}
        .report-table {{ border-collapse: collapse; width: 100%; }}
        .report-table th, .report-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        .report-table th {{ background: #f5f5f5; }}
        .report-table tbody tr:hover {{ background: #f9f9f9; }}
        .report-table pre {{ margin: 0; white-space: pre-wrap; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>UI2Code 自动化测试报告</h1>
    <p class="meta"><strong>生成时间</strong>: {gen_time}</p>
    {stats_html}
    {fail_html}
    {table_html}
</body>
</html>"""

    report_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    report_filepath = os.path.join(output_dir, report_filename)
    os.makedirs(output_dir, exist_ok=True)
    with open(report_filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    return report_filepath


def main():
    project_root = _PROJECT_ROOT
    tests_file = os.path.join(_TESTS_DIR, "test_url_list.txt")
    urls = read_urls_from_file(tests_file)

    if not urls:
        print(f"❌ 未从 {tests_file} 读取到任何 URL")
        return

    conn = init_sqlite(project_root)
    try:
        print(f"📋 共 {len(urls)} 个 URL")
        print(f"📁 输出目录: {_OUTPUT_DIR}")
        print("开始批量处理...")

        all_results = []
        for idx, url in enumerate(urls, 1):
            print(f"\n{'#'*60}")
            print(f"[{idx}/{len(urls)}] 处理 URL {idx}")
            print(f"{'#'*60}")
            result = process_single_url_complete(url, project_root, conn)
            if result:
                all_results.append(result)
                if not result.get("success"):
                    print("❌ 本 URL 处理失败，继续下一个...")

        output_dir = _OUTPUT_DIR
        report_filepath = generate_html_report(all_results, conn, output_dir)

        success_count = sum(1 for r in all_results if r.get("success"))
        print(f"\n{'='*60}")
        print(f"✅ 批量处理完成! 成功: {success_count}/{len(urls)}")
        print(f"📁 输出目录: {output_dir}")
        print(f"📄 报告已保存: {report_filepath}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
