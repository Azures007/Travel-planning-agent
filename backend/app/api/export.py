"""行程导出 API：支持 HTML、PDF、图片等格式。"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Session, Itinerary
from app.db.session import get_db

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/{session_id}/html", response_class=HTMLResponse)
async def export_html(session_id: int, db: AsyncSession = Depends(get_db)):
    """导出为美化的 HTML（可直接打印或转 PDF）。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    itinerary = itinerary_obj.plan

    # 生成 HTML
    html = generate_html(session.title, itinerary)
    return HTMLResponse(content=html)


@router.get("/{session_id}/share")
async def get_share_link(session_id: int, db: AsyncSession = Depends(get_db)):
    """生成分享链接（前端路由）。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 简单方案：返回前端 URL（后续可增加短链接/加密）
    share_url = f"http://localhost:5173/share/{session_id}"
    return {"url": share_url, "title": session.title}


@router.get("/{session_id}/markdown")
async def export_markdown(session_id: int, db: AsyncSession = Depends(get_db)):
    """导出为 Markdown 格式（可在任何编辑器查看/转换）。"""
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = await db.execute(
        select(Itinerary).where(Itinerary.session_id == session_id)
    )
    itinerary_obj = result.scalar_one_or_none()
    if not itinerary_obj:
        raise HTTPException(status_code=404, detail="未生成行程")

    md = generate_markdown(session.title, itinerary_obj.plan)
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="itinerary_{session_id}.md"'
        },
    )


def generate_markdown(title: str, itinerary: dict) -> str:
    """生成 Markdown 格式的行程。"""
    req = itinerary.get("requirements", {})
    days = itinerary.get("days", [])
    total = itinerary.get("total_budget") or itinerary.get("total_cost", 0)

    lines = [f"# {title}", ""]

    # 需求概览
    info = []
    if req.get("destination"):
        info.append(f"**目的地**：{req['destination']}")
    if req.get("days"):
        info.append(f"**天数**：{req['days']} 天")
    if req.get("budget"):
        info.append(f"**预算**：¥{req['budget']}")
    if req.get("travelers"):
        info.append(f"**人数**：{req['travelers']}")
    if req.get("pace"):
        info.append(f"**节奏**：{req['pace']}")
    if info:
        lines.append(" · ".join(info))
        lines.append("")

    lines.append(f"**预估总花费**：¥{total}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 逐日行程
    for day in days:
        day_num = day.get("day", "")
        day_date = day.get("date", "")
        header = f"## 第 {day_num} 天"
        if day_date:
            header += f"（{day_date}）"
        lines.append(header)
        lines.append("")

        if day.get("summary"):
            lines.append(f"> {day['summary']}")
            lines.append("")

        for act in day.get("activities", []):
            time_str = act.get("time", "")
            act_title = act.get("title", "")
            location = act.get("location", "")
            detail = act.get("detail", "")
            cost = act.get("cost", 0)
            transport = act.get("transport", "")

            line = f"- **{time_str}** {act_title}"
            if location:
                line += f" @ {location}"
            if cost:
                line += f" （¥{cost}）"
            lines.append(line)
            if detail:
                lines.append(f"  - {detail}")
            if transport:
                lines.append(f"  - 🚗 {transport}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*由旅行规划助手生成*")

    return "\n".join(lines)


def generate_html(title: str, itinerary: dict) -> str:
    """生成美化的 HTML（带样式、适合打印）。"""
    requirements = itinerary.get("requirements", {})
    days = itinerary.get("days", [])
    total_cost = itinerary.get("total_budget") or itinerary.get("total_cost", 0)

    # 构建需求标签
    tags_html = ""
    if requirements.get("destination"):
        tags_html += f'<span class="tag">📍 {requirements["destination"]}</span>'
    if requirements.get("budget"):
        tags_html += f'<span class="tag">💰 预算 ¥{requirements["budget"]}</span>'
    if requirements.get("travelers"):
        tags_html += f'<span class="tag">👥 {requirements["travelers"]}人</span>'
    if requirements.get("pace"):
        tags_html += f'<span class="tag">⏱️ {requirements["pace"]}</span>'

    # 构建每日行程
    days_html = ""
    for day_idx, day in enumerate(days, 1):
        day_date = day.get("date", "")
        activities_html = ""

        for activity in day.get("activities", []):
            activities_html += f"""
            <div class="activity">
                <div class="activity-time">{activity.get('time', '')}</div>
                <div class="activity-content">
                    <h4>{activity.get('name', '')}</h4>
                    {f'<p class="desc">{activity.get("description", "")}</p>' if activity.get("description") else ''}
                    {f'<p class="cost">💵 约 ¥{activity.get("estimated_cost", 0)}</p>' if activity.get("estimated_cost") else ''}
                </div>
            </div>
            """

        days_html += f"""
        <div class="day-card">
            <h3>第 {day_idx} 天 {f'· {day_date}' if day_date else ''}</h3>
            <div class="activities">
                {activities_html}
            </div>
        </div>
        """

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
                line-height: 1.6;
                color: #333;
                background: #f5f5f5;
                padding: 20px;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #10b981 0%, #14b8a6 100%);
                color: white;
                padding: 30px;
            }}
            .header h1 {{
                font-size: 28px;
                margin-bottom: 12px;
            }}
            .tags {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 15px;
            }}
            .tag {{
                background: rgba(255,255,255,0.2);
                padding: 6px 12px;
                border-radius: 20px;
                font-size: 13px;
            }}
            .content {{
                padding: 30px;
            }}
            .summary {{
                background: #f0fdf4;
                padding: 15px 20px;
                border-radius: 8px;
                margin-bottom: 25px;
                border-left: 4px solid #10b981;
            }}
            .summary strong {{
                color: #059669;
            }}
            .day-card {{
                margin-bottom: 30px;
                padding-bottom: 30px;
                border-bottom: 1px solid #e5e7eb;
            }}
            .day-card:last-child {{
                border-bottom: none;
            }}
            .day-card h3 {{
                font-size: 20px;
                color: #10b981;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
            }}
            .activities {{
                display: flex;
                flex-direction: column;
                gap: 15px;
            }}
            .activity {{
                display: flex;
                gap: 15px;
                padding: 15px;
                background: #f9fafb;
                border-radius: 8px;
            }}
            .activity-time {{
                color: #6b7280;
                font-size: 14px;
                font-weight: 500;
                min-width: 60px;
                padding-top: 2px;
            }}
            .activity-content {{
                flex: 1;
            }}
            .activity-content h4 {{
                font-size: 16px;
                color: #111827;
                margin-bottom: 6px;
            }}
            .desc {{
                font-size: 14px;
                color: #6b7280;
                margin-bottom: 8px;
            }}
            .cost {{
                font-size: 13px;
                color: #059669;
                font-weight: 500;
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                color: #9ca3af;
                font-size: 13px;
                border-top: 1px solid #e5e7eb;
            }}
            @media print {{
                body {{ background: white; padding: 0; }}
                .container {{ box-shadow: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{title}</h1>
                <div class="tags">
                    {tags_html}
                </div>
            </div>
            <div class="content">
                <div class="summary">
                    <strong>总预算：</strong>¥{total_cost} · <strong>行程天数：</strong>{len(days)}天
                </div>
                {days_html}
            </div>
            <div class="footer">
                由旅行规划助手生成 · {title}
            </div>
        </div>
    </body>
    </html>
    """
    return html_template
