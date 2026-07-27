from fastapi.routing import APIRoute
from app.main import app
from check_route_guards import _walk_routes, _dependant_calls

AUTHY = {"require_auth","require_active_user","checker","require_project_access","require_user_admin","get_db","token_claims"}
rows=[]
for p, r in _walk_routes(app.routes):
    calls=[getattr(c,"__qualname__",str(c)) for c in _dependant_calls(r.dependant)]
    names=set(calls)
    guards=[c for c in calls if c!="get_db"]
    authed = any(g in ("require_auth","require_active_user","require_project_access","require_user_admin") or "checker" in g for g in guards)
    m=",".join(sorted(r.methods))
    rows.append((p,m,authed,sorted(set(guards))))
for p,m,a,g in sorted(rows):
    flag = "" if a else "  <<<< NO AUTH GUARD"
    print(f"{m:7} {p:55} {g}{flag}")
