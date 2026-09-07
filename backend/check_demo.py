"""Demo bazani rollar kesimida tekshirish: har rol nimani ko'radi, KPI mantiqan to'g'rimi."""
import os, sys, time, socket, subprocess, json
import httpx

BASE = os.environ["BASE"]

def login(login, pw):
    r = httpx.post(f"{BASE}/auth/login", json={"login": login, "password": pw}, timeout=20)
    assert r.status_code == 200, (login, r.text)
    return r.json()["access_token"]

def H(tok): return {"Authorization": f"Bearer {tok}", "X-Source": "web"}

def get(tok, path, **params):
    r = httpx.get(f"{BASE}{path}", headers=H(tok), params=params, timeout=60)
    return r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)

admin = login("admin", os.environ.get("ADMIN_PASSWORD", "SaffAdmin2026!"))
print("=" * 72)
_, me = get(admin, "/auth/me")
print(f"ADMIN: {me['user']['full_name']} · {len(me['permissions'])} ruxsat")

_, s = get(admin, "/reports/summary")
k = s["kpi"]
print(f"\nKPI (butun tizim): jami={k['total']} ochiq={k['open']} kechikkan={k['overdue']} "
      f"(bajaruvchi {k['overdue_by_assignee']} / tekshiruvchi {k['overdue_by_reviewer']}) "
      f"bloklangan={k['blocked']} tekshiruvda={k['review']} (eng eskisi {k['review_oldest_days']} kun)")
print(f"     bajarildi={k['done']} muddatida={k['on_time_pct']}% o'rtacha={k['avg_duration_days']} kun qaytarish={k['return_pct']}%")
print("     holatlar:", s["by_status"])
print("     blok sabablari:", [(r['code'], r['count']) for r in s['blocked_reasons']][:6])
print("     eng band 3 xodim:", [(x['name'], x['open'], x['overdue']) for x in s['staff'][:3]])
print("     14 kunlik bajarilish:", [d['done'] for d in s['daily_done']])

# --- business sanity checks ---
errs = []
_, page = get(admin, "/tasks", limit=200, status="done")
for t in page["items"]:
    if t["progress_percent"] != 100: errs.append(f"{t['code']}: done but progress {t['progress_percent']}")
    if not t["actual_end"]: errs.append(f"{t['code']}: done but no actual_end")
    if t["checklist_total"] and t["checklist_done"] < t["checklist_total"]: pass
_, page = get(admin, "/tasks", limit=200, blocked=True)
for t in page["items"]:
    if not t["blocked_reason"]: errs.append(f"{t['code']}: blocked without reason")
    if not t["blocked_note"]: errs.append(f"{t['code']}: blocked without note")
    if not t["previous_status"]: errs.append(f"{t['code']}: blocked without previous_status")
_, page = get(admin, "/tasks", limit=200, status="review")
for t in page["items"]:
    if t["photos_count"] == 0: errs.append(f"{t['code']}: in review with no photo")
    d = get(admin, f"/tasks/{t['id']}")[1]
    missing = [c["title"] for c in d["checklist"] if c["is_required"] and not c["is_done"]]
    if missing: errs.append(f"{t['code']}: in review with unfinished required checklist {missing}")
    have = {a["kind"] for a in d["attachments"]}
    lack = [x for x in d["required_evidence_kinds"] if x not in have]
    if lack: errs.append(f"{t['code']}: in review missing evidence {lack}")
_, page = get(admin, "/tasks", limit=200, status="plan")
for t in page["items"]:
    if t["progress_percent"]: errs.append(f"{t['code']}: plan but progress {t['progress_percent']}")

print("\nBIZNES TEKSHIRUV:", "✓ hammasi joyida" if not errs else f"✗ {len(errs)} muammo")
for e in errs[:10]: print("   ", e)

print("\n" + "=" * 72)
print("ROLLAR KESIMI (har kim nimani ko'radi):")
for lg, pw, label in [("arustamov", "1234", "Loyiha rahbari"), ("skarimov", "1234", "Prorab"),
                      ("rergashev", "1234", "Bajaruvchi"), ("dtoshmatov", "1234", "Tekshiruvchi"),
                      ("mahmedova", "1234", "Kuzatuvchi")]:
    tok = login(lg, pw)
    _, m = get(tok, "/auth/me")
    _, pg = get(tok, "/tasks", limit=200)
    _, ov = get(tok, "/tasks", limit=200, overdue=True)
    st, rep = get(tok, "/reports/summary")
    st_csv, _ = get(tok, "/reports/export.csv")
    st_users, _ = get(tok, "/users")
    scope = m["user"]["scope_type"]
    projs = get(tok, "/projects")[1]
    print(f"\n  {label:16} ({lg}) doira={scope}")
    print(f"    ko'radigan vazifa: {pg['total']:<5} kechikkan: {ov['total']:<4} loyiha: {len(projs)}")
    print(f"    hisobot: {'✓' if st == 200 else '✗ ' + str(st)}   CSV: {'✓' if st_csv == 200 else '✗'}   "
          f"foydalanuvchilar: {'✓' if st_users == 200 else '✗'}")
    if pg["items"]:
        t0 = pg["items"][0]
        d = get(tok, f"/tasks/{t0['id']}")[1]
        p = d["permissions"]
        can = [k for k, v in p.items() if v]
        buttons = ", ".join(can) if can else "— (faqat ko'rish)"
        print(f"    kartochkadagi tugmalar ({t0['code']}): {buttons}")
