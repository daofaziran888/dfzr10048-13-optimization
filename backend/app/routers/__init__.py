"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import resource, term_index

# /api/term-index 必须先于 /api/{module} 注册，否则会被动态模块路径抢走。
ROUTERS = [term_index, resource]
