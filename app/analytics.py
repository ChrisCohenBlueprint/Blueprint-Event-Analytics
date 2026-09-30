"""Aggregations behind every dashboard tab. Returns plain JSON-able dicts; no personal data."""
from datetime import timedelta

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import dictionary as d
from .db import IngestRun, Registration, Show, engine

SEGMENTS = {
    "attendees": ("All attendees", lambda f: f[f.category == "Attendee"]),
    "visitors": ("Visitors", lambda f: f[(f.category == "Attendee") & f.reg_type_raw.str.lower().str.startswith("visitor")]),
    "vip": ("VIPs", lambda f: f[(f.category == "Attendee") & (f.reg_type_raw.str.upper() == "VIP")]),
    "speakers": ("Speakers", lambda f: f[(f.category == "Attendee") & (f.reg_type_raw.str.lower() == "speaker")]),
    "exhibitors": ("Exhibitors", lambda f: f[f.category == "Exhibitor"]),
}

_COLS = ["source_id", "created_at", "reg_type_raw", "category", "company", "email", "country",
         "world_region", "job_title", "job_function", "seniority", "industry", "industry_group",
         "buyer_supplier", "budget_responsibility", "budget_band", "products", "commercial_interest",
         "attended", "previous_attendee", "source_channel", "updated_at"]

_cache = {}


def invalidate(show_code=None):
    for k in list(_cache):
        if show_code is None or k[0] == show_code:
            del _cache[k]


def load_frame(show_code):
    with Session(engine) as s:
        rows = s.execute(select(*[getattr(Registration, c) for c in _COLS])
                         .where(Registration.show_code == show_code)).all()
    f = pd.DataFrame(rows, columns=_COLS)
    if not f.empty:
        f["created_at"] = pd.to_datetime(f["created_at"])
        f["day"] = f["created_at"].dt.normalize()
        f["reg_type_raw"] = f["reg_type_raw"].fillna("")
    return f


def pct(n, total):
    return round(100.0 * n / total, 1) if total else 0.0


def dist(series, total=None, order=None, top=None, other_label="All others", drop_zero=False):
    """Value counts -> [{label, n, pct}], optionally ordered or capped with an 'Other' fold."""
    vc = series.dropna().value_counts()
    total = total if total is not None else int(vc.sum())
    if order:
        items = [(k, int(vc.get(k, 0))) for k in order if k in vc.index or k in order]
        items += [(k, int(v)) for k, v in vc.items() if k not in order]
    else:
        items = [(k, int(v)) for k, v in vc.items()]
    if drop_zero:
        items = [(k, v) for k, v in items if v]
    if top and len(items) > top:
        rest = sum(v for _, v in items[top:])
        items = items[:top] + ([(other_label, rest)] if rest else [])
    return [{"label": k, "n": v, "pct": pct(v, total)} for k, v in items]


_ACRONYMS = {"Ceo", "Cfo", "Coo", "Cto", "Cmo", "Cco", "Md", "Gm", "Vp", "Svp", "Evp", "R&D", "Hse", "Qa", "Qc",
             "Bd", "It", "Hr", "Ehs", "Emea", "Apac", "Us", "Uk", "Eu", "Rd", "Kam"}


def nice_title(t):
    if not isinstance(t, str) or not t.strip():
        return None
    words = t.strip().title().split()
    return " ".join(w.upper() if w in _ACRONYMS else w for w in words)


def explode(series):
    return series.dropna().str.split("|").explode().str.strip().replace("", pd.NA).dropna()


# ---------------------------------------------------------------------------
def _data_stamp():
    # Changes whenever any feed (upload, cron sync, API push) writes data - including from
    # another process such as the Render cron job - so cached summaries never go stale.
    with Session(engine) as s:
        return s.scalar(select(func.max(IngestRun.id))) or 0


def summary(show_code, segment="attendees"):
    key = (show_code, segment, _data_stamp())
    if key in _cache:
        return _cache[key]
    if len(_cache) > 200:
        _cache.clear()
    with Session(engine) as s:
        show = s.get(Show, show_code)
        last_run = s.scalars(select(IngestRun).where(IngestRun.show_code == show_code)
                             .order_by(IngestRun.started_at.desc()).limit(1)).first()
    if show is None:
        raise KeyError(show_code)
    full = load_frame(show_code)
    meta = {
        "code": show.code, "brand": show.brand, "name": show.name, "region": show.region,
        "year": show.year,
        "start_date": show.start_date.isoformat() if show.start_date else None,
        "end_date": show.end_date.isoformat() if show.end_date else None,
        "segment": segment, "segment_label": SEGMENTS[segment][0],
        "segments": [{"key": k, "label": v[0]} for k, v in SEGMENTS.items()],
        "last_ingest": last_run.started_at.isoformat() + "Z" if last_run else None,
        "last_source": last_run.source if last_run else None,
        "has_data": not full.empty,
    }
    if full.empty:
        out = {"meta": meta}
        _cache[key] = out
        return out

    # Earlier editions of the same show: returning visitors, pacing and lapsed audience
    prev_show, prev_full, earlier_emails, earlier_codes = previous_editions(show)
    meta["previous_code"] = prev_show.code if prev_show is not None else None
    meta["returning_basis"] = None
    if full.previous_attendee.isna().all() and earlier_emails:
        full["previous_attendee"] = full.email.isin(earlier_emails).where(full.email.notna())
        meta["returning_basis"] = "Registered for an earlier edition (" + ", ".join(earlier_codes) + "), matched on email"
    elif full.previous_attendee.notna().any():
        meta["returning_basis"] = "From the previous-attendee field in the export"

    f = SEGMENTS[segment][1](full)
    n = len(f)
    attendees = full[full.category == "Attendee"]
    exhibitors = full[full.category == "Exhibitor"]
    prev_f = SEGMENTS[segment][1](prev_full) if prev_full is not None else None

    out = {
        "meta": meta,
        "mix": mix(full, attendees, exhibitors),
        "kpis": kpis(f),
        "audience": audience(f),
        "behaviour": behaviour(f, show),
        "geography": geography(f),
        "commercial": commercial(f),
        "journey": journey(f),
        "gaps": gaps(f, show),
        "coverage": coverage(f),
        "pacing": pacing(f, show, prev_f, prev_show) if prev_f is not None and len(prev_f) else None,
        "lapsed": lapsed(full, prev_f, prev_show) if prev_f is not None and len(prev_f) else None,
    }
    out["meta"]["segment_n"] = n
    out["meta"]["latest_registration"] = f.created_at.max().isoformat() if n else None
    _cache[key] = out
    return out


def previous_editions(show):
    """(previous show, its frame, emails from all earlier editions, their codes) for the same brand."""
    with Session(engine) as s:
        earlier = list(s.scalars(select(Show).where(Show.brand == show.brand, Show.year < show.year)
                                 .order_by(Show.year.desc())))
    prev_show, prev_full, emails, codes = None, None, set(), []
    for e in earlier:
        frame = load_frame(e.code)
        if frame.empty:
            continue
        codes.append(e.code)
        emails |= set(frame.loc[frame.category == "Attendee", "email"].dropna())
        if prev_show is None:
            prev_show, prev_full = e, frame
    return prev_show, prev_full, emails, codes


def _start_of(frame, show):
    if show.start_date:
        return pd.Timestamp(show.start_date)
    return frame.day.max() + timedelta(days=1)


def pacing(f, show, prev_f, prev_show):
    """Cumulative registrations by days before opening, this edition vs the previous one."""
    if f.day.isna().all() or prev_f.day.isna().all():
        return None
    start, pstart = _start_of(f, show), _start_of(prev_f, prev_show)
    cur_out = (start - f.day).dt.days
    prev_out = (pstart - prev_f.day).dt.days
    horizon = int(max(cur_out.max(), prev_out.max()))
    end = -int(max(0, (pd.Timestamp(show.end_date) - start).days if show.end_date else 2)) - 1
    xs = list(range(horizon, end - 1, -1))

    def cum(out):
        counts = out.value_counts()
        total, series = 0, []
        for x in xs:
            total += int(counts.get(x, 0))
            series.append(total)
        return series

    cur, prev = cum(cur_out), cum(prev_out)
    latest_out = int(cur_out.min())
    # Only draw this edition up to its latest registration (the future hasn't happened yet)
    cur = [v if x >= latest_out else None for x, v in zip(xs, cur)]
    idx = xs.index(latest_out) if latest_out in xs else len(xs) - 1
    prev_same = prev[idx]
    return {
        "days_out": xs,
        "current": cur, "previous": prev,
        "current_code": show.code, "previous_code": prev_show.code,
        "latest_days_out": latest_out,
        "current_total": len(f), "previous_same_point": prev_same, "previous_final": prev[-1],
        "vs_previous_pct": round(100.0 * (len(f) - prev_same) / prev_same, 1) if prev_same else None,
    }


def lapsed(full, prev_f, prev_show):
    """People who registered for the previous edition but not (yet) for this one."""
    current = set(full.email.dropna())
    prev = prev_f[prev_f.email.notna()]
    lost = prev[~prev.email.isin(current)]
    k = len(lost)
    return {
        "previous_code": prev_show.code,
        "previous_total": len(prev), "n": k, "pct": pct(k, len(prev)),
        "retained": len(prev) - k, "retained_pct": pct(len(prev) - k, len(prev)),
        "countries": dist(lost.country, k, top=10),
        "seniority": dist(lost.seniority, k, order=d.SENIORITY_ORDER),
        "job_function": dist(lost.job_function, k, top=8),
        "companies": dist(lost.company.map(lambda c: c if isinstance(c, str) else None), k, top=12),
    }


def mix(full, attendees, exhibitors):
    na, ne = len(attendees), len(exhibitors)
    return {
        "total_records": len(full),
        "attendees": na,
        "exhibitors": ne,
        "exhibitor_pct_of_attendees": pct(ne, na),
        "attendees_per_exhibitor": round(na / ne, 1) if ne else None,
        "by_category": dist(full.category),
        "attendee_types": dist(attendees.reg_type_raw.str.replace(r"\s+-\s*\w+$", "", regex=True).replace("", pd.NA)),
    }


def kpis(f):
    n = len(f)
    senior = f.seniority.isin(d.SENIOR_LEVELS).sum()
    buying = f.budget_responsibility.isin(["Yes", "Influence"]).sum()
    ret = f.previous_attendee.dropna()
    att = f.attended.dropna()
    return {
        "total": n,
        "countries": int(f.country.nunique()),
        "companies": int(f.company.dropna().map(d.company_key).nunique()),
        "senior": int(senior), "senior_pct": pct(senior, n),
        "buying_power": int(buying), "buying_power_pct": pct(buying, n),
        "budget_holders": int((f.budget_responsibility == "Yes").sum()),
        "buyers": int((f.buyer_supplier == "Buyer").sum()),
        "buyers_pct": pct((f.buyer_supplier == "Buyer").sum(), n),
        "top_country": f.country.value_counts().index[0] if f.country.notna().any() else None,
        "top_country_pct": pct(f.country.value_counts().iloc[0], n) if f.country.notna().any() else 0,
        "returning_pct": pct(ret.sum(), len(ret)) if len(ret) else None,
        "attended": int(att.sum()) if len(att) else None,
        "no_show": int((~att.astype(bool)).sum()) if len(att) else None,
    }


def audience(f):
    n = len(f)
    return {
        "seniority": dist(f.seniority, n, order=d.SENIORITY_ORDER),
        "job_function": dist(f.job_function, n, top=12),
        "industry": dist(f.industry, n, top=15),
        "industry_group": dist(f.industry_group, n),
        "buyer_supplier": dist(f.buyer_supplier, n),
        "budget_responsibility": dist(f.budget_responsibility, n, order=["Yes", "Influence", "No"]),
        "products": dist(explode(f.products), n, top=18),
        "top_job_titles": dist(f.job_title.map(nice_title), n, top=15),
        "industry_tree": [{"label": k, "n": int(v), "pct": pct(v, n), "group": d.industry_group(k)}
                          for k, v in f.industry.value_counts().items()],
        "function_by_seniority": function_by_seniority(f),
        "new_vs_returning": (dist(f.previous_attendee.map({True: "Returning", False: "New to the show"}), n)
                             if f.previous_attendee.notna().any() else None),
        "companies": {
            "total": int(f.company.dropna().map(d.company_key).nunique()),
            "avg_per_company": round(n / max(1, f.company.dropna().map(d.company_key).nunique()), 2),
        },
    }


def function_by_seniority(f):
    """Job function x seniority counts for the heatmap (top 10 functions)."""
    funcs = [x for x in f.job_function.value_counts().index if x != "Other"][:10]
    levels = [lvl for lvl in d.SENIORITY_ORDER if lvl != "Unclassified"]
    tab = pd.crosstab(f.job_function, f.seniority)
    return {
        "functions": funcs, "levels": levels,
        "cells": [[int(tab.at[fn, lvl]) if fn in tab.index and lvl in tab.columns else 0 for lvl in levels] for fn in funcs],
        "totals": [int((f.job_function == fn).sum()) for fn in funcs],
    }


def _windows(f, show):
    days = f.day.dropna()
    first = days.min()
    if show.start_date:
        start = pd.Timestamp(show.start_date)
        end = pd.Timestamp(show.end_date or show.start_date)
        inferred = False
    else:
        start = days.max() + timedelta(days=1)
        end = start
        inferred = True
    return first, start, end, inferred


def behaviour(f, show):
    n = len(f)
    if not n or f.day.isna().all():
        return None
    first, start, end, inferred = _windows(f, show)
    day = f.day
    td = lambda k: timedelta(days=k)
    windows = [
        ("Opening day", day == first, "early"),
        ("First 7 days", day < first + td(7), "early"),
        ("First 14 days", day < first + td(14), "early"),
        ("First 30 days", day < first + td(30), "early"),
        ("Final 30 days", (day >= start - td(30)) & (day < start), "late"),
        ("Final 14 days", (day >= start - td(14)) & (day < start), "late"),
        ("Final 7 days", (day >= start - td(7)) & (day < start), "late"),
        ("Final 3 days", (day >= start - td(3)) & (day < start), "late"),
        ("Day before show", day == start - td(1), "late"),
        ("During show (onsite)", (day >= start) & (day <= end), "onsite"),
    ]
    win = [{"label": l, "n": int(m.sum()), "pct": pct(m.sum(), n), "phase": p} for l, m, p in windows]

    # Daily + cumulative curve
    daily = day.value_counts().sort_index()
    rng = pd.date_range(first, max(daily.index.max(), end))
    daily = daily.reindex(rng, fill_value=0)
    curve = [{"date": dt.date().isoformat(), "n": int(v), "cum": int(c)}
             for dt, v, c in zip(daily.index, daily.values, daily.cumsum().values)]

    # Weeks-out profile
    weeks_out = ((start - day).dt.days // 7).clip(lower=-1)
    wk = weeks_out.value_counts().sort_index(ascending=False)
    weeks = [{"label": ("Onsite" if w < 0 else ("Show week" if w == 0 else f"{int(w)}w out")),
              "weeks_out": int(w), "n": int(v)} for w, v in wk.items()]

    # Cohorts: where do early and late deciders behave differently?
    top_country = f.country.value_counts().index[0] if f.country.notna().any() else None
    cohorts_def = [
        ("Early bird", "First 30 days", day < first + td(30)),
        ("Mid-cycle", "Day 31 to 31 days out", (day >= first + td(30)) & (day < start - td(30))),
        ("Late", "Final 30 to 8 days", (day >= start - td(30)) & (day < start - td(7))),
        ("Last minute", "Final 7 days", (day >= start - td(7)) & (day < start)),
        ("Onsite", "During the show", (day >= start) & (day <= end)),
    ]
    cohorts = []
    for name, desc, m in cohorts_def:
        c = f[m]
        k = len(c)
        if not k:
            continue
        cohorts.append({
            "name": name, "desc": desc, "n": k, "pct": pct(k, n),
            "senior_pct": pct(c.seniority.isin(d.SENIOR_LEVELS).sum(), k),
            "buyer_pct": pct((c.buyer_supplier == "Buyer").sum(), k),
            "budget_pct": pct(c.budget_responsibility.isin(["Yes", "Influence"]).sum(), k),
            "procurement_pct": pct(c.job_function.fillna("").str.startswith("Purchasing").sum(), k),
            "top_country_pct": pct((c.country == top_country).sum(), k),
            "international_pct": pct((c.country != top_country).sum(), k),
            "exhibit_interest_pct": pct(c.commercial_interest.isin(["Exhibiting", "Sponsoring"]).sum(), k),
            "top_countries": [x["label"] for x in dist(c.country, k)[:3]],
        })

    weekday = f.created_at.dt.day_name().value_counts()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hours = f.created_at.dt.hour.value_counts().reindex(range(24), fill_value=0)

    first7 = next(w for w in win if w["label"] == "First 7 days")
    last7 = next(w for w in win if w["label"] == "Final 7 days")
    return {
        "first_registration": first.date().isoformat(),
        "show_start": start.date().isoformat(),
        "show_start_inferred": inferred,
        "cycle_days": int((start - first).days),
        "windows": win,
        "curve": curve,
        "weeks": weeks,
        "cohorts": cohorts,
        "top_country": top_country,
        "weekday": [{"label": dname[:3], "n": int(weekday.get(dname, 0))} for dname in order],
        "hours_utc": [{"label": f"{h:02d}", "n": int(v)} for h, v in hours.items()],
        "late_vs_early_ratio": round(last7["n"] / first7["n"], 1) if first7["n"] else None,
        "half_registered_by": _half_point(curve, n),
    }


def _half_point(curve, n):
    for p in curve:
        if p["cum"] >= n / 2:
            return p["date"]
    return None


def geography(f):
    n = len(f)
    vc = f.country.value_counts()
    countries = [{"label": c, "n": int(v), "pct": pct(v, n), "region": d.world_region(c)}
                 for c, v in vc.items()]
    top5 = int(vc.head(5).sum())
    core = set(vc.head(6).index)
    opp = [c for c in countries if c["label"] not in core and c["n"] >= 30][:12]
    return {
        "countries": countries,
        "regions": dist(f.world_region, n),
        "country_count": int(vc.size),
        "top5_share": pct(top5, n),
        "long_tail": sum(1 for c in countries if c["n"] < 10),
        "opportunity_markets": opp,
    }


def commercial(f):
    n = len(f)
    budget = f.budget_band.dropna()
    over250 = budget.isin(["$250k-500k", "$500k-1M", "Over $1M"]).sum()
    ci = f.commercial_interest.fillna("")
    comp = f.dropna(subset=["company"]).assign(key=lambda x: x.company.map(d.company_key))
    grp = comp.groupby("key")
    top_companies = (grp.agg(company=("company", "first"), n=("source_id", "size"),
                             senior=("seniority", lambda s: int(s.isin(d.SENIOR_LEVELS).sum())),
                             country=("country", lambda s: s.mode().iat[0] if s.notna().any() else None))
                     .sort_values("n", ascending=False).head(20))
    size_dist = grp.size().pipe(lambda s: pd.cut(s, [0, 1, 2, 5, 10, 10_000],
                                                 labels=["1 person", "2", "3-5", "6-10", "11+"]))
    sen_x_bs = []
    for lvl in d.SENIORITY_ORDER:
        sub = f[f.seniority == lvl]
        sen_x_bs.append({"label": lvl,
                         "Buyer": int((sub.buyer_supplier == "Buyer").sum()),
                         "Supplier": int((sub.buyer_supplier == "Supplier").sum()),
                         "Not stated": int(sub.buyer_supplier.isna().sum())})
    return {
        "budget_responsibility": dist(f.budget_responsibility, n, order=["Yes", "Influence", "No"]),
        "budget_bands": dist(budget, len(budget), order=d.BUDGET_ORDER, drop_zero=True),
        "budget_respondents": int(len(budget)),
        "budget_250k_plus": int(over250),
        "budget_1m_plus": int((budget == "Over $1M").sum()),
        "exhibit_interest": int((ci == "Exhibiting").sum()),
        "sponsor_interest": int((ci == "Sponsoring").sum()),
        "commercial_interest": dist(f.commercial_interest, n),
        "top_companies": [{"company": r.company, "n": int(r.n), "senior": int(r.senior), "country": r.country}
                          for r in top_companies.itertuples()],
        "company_delegation": [{"label": str(k), "n": int(v)} for k, v in size_dist.value_counts().sort_index().items()],
        "seniority_by_buyer": sen_x_bs,
    }


def journey(f):
    n = len(f)
    att = f.attended.dropna()
    has_att = len(att) > 0
    stages = [
        {"stage": "First touch", "detail": "Website / LinkedIn / email / paid", "n": None, "source": "GA4, LinkedIn, Dotdigital"},
        {"stage": "Engaged", "detail": "Content viewed / email clicked", "n": None, "source": "Dotdigital, GA4"},
        {"stage": "Registered", "detail": "Completed registration", "n": n, "source": "Registration platform"},
        {"stage": "Attended", "detail": "Badge scanned onsite", "n": int(att.sum()) if has_att else None, "source": "Onsite badge scans"},
        {"stage": "Engaged onsite", "detail": "Sessions, meetings, app", "n": None, "source": "Show app"},
        {"stage": "Returned / exhibited / sponsored", "detail": "Next edition", "n": None, "source": "CRM, Sales data"},
    ]
    no_show = None
    if has_att:
        ns = f[f.attended == False]  # noqa: E712
        k = len(ns)
        no_show = {
            "n": k, "pct": pct(k, len(att)),
            "countries": dist(ns.country, k, top=10),
            "seniority": dist(ns.seniority, k, order=d.SENIORITY_ORDER),
            "job_function": dist(ns.job_function, k, top=8),
            "companies": dist(ns.company, k, top=15),
        }
    return {"stages": stages, "no_show": no_show}


def gaps(f, show):
    """'Who are we missing?' - generated findings with an opportunity question each."""
    n = len(f)
    out = []
    vc = f.country.value_counts()
    if len(vc) > 6:
        lead, lead_n = vc.index[0], int(vc.iloc[0])
        big_markets = ["United States", "India", "China", "Japan", "Brazil", "Saudi Arabia",
                       "South Korea", "Indonesia", "Mexico", "Türkiye", "Poland", "Nigeria", "Egypt"]
        rows = [(c, int(vc.get(c, 0))) for c in big_markets if c != lead]
        rows = sorted(rows, key=lambda r: r[1], reverse=True)[:6]
        out.append({
            "type": "Geographic",
            "headline": f"{lead} brings {lead_n:,} attendees; large lubricant markets bring far fewer",
            "rows": [{"label": c, "n": v, "ratio": f"1 : {round(lead_n / v)}" if v else "none"} for c, v in rows],
            "opportunity": "Which of these are under-developed markets for us? Test country-specific paid audiences where interest already exists.",
        })
    jf = f.job_function.value_counts()
    proc = int(f.job_function.fillna("").str.startswith("Purchasing").sum())
    sales = int(f.job_function.fillna("").str.startswith("Sales").sum())
    eng = int(f.job_function.fillna("").str.match(r"^(Engineering|R&D|Maintenance)").sum())
    execs = int((f.seniority == "Executive / Owner").sum())
    out.append({
        "type": "Seniority & role",
        "headline": f"Procurement is {pct(proc, n)}% of the audience, against {pct(sales, n)}% sales and marketing",
        "rows": [{"label": "Sales / marketing / BD", "n": sales, "ratio": f"{pct(sales, n)}%"},
                 {"label": "Engineering / R&D / maintenance", "n": eng, "ratio": f"{pct(eng, n)}%"},
                 {"label": "Purchasing / procurement", "n": proc, "ratio": f"{pct(proc, n)}%"},
                 {"label": "Executive / owner (any function)", "n": execs, "ratio": f"{pct(execs, n)}%"}],
        "opportunity": "Could we target procurement and buying roles with their own message, such as sourcing, supplier discovery and price benchmarking?",
    })
    ig = f.industry_group.value_counts()
    ends = f[f.industry_group == "End-user industry"].industry.value_counts()
    out.append({
        "type": "Industry",
        "headline": f"{pct(ig.get('Lubricant supply chain', 0), n)}% come from the lubricant supply chain; "
                    f"end-user industries make up {pct(ig.get('End-user industry', 0), n)}%",
        "rows": [{"label": k, "n": int(v), "ratio": f"{pct(v, n)}%"} for k, v in ends.head(4).items()]
                + [{"label": k, "n": int(v), "ratio": f"{pct(v, n)}%"} for k, v in ends.tail(4).items()
                   if k not in ends.head(4).index],
        "opportunity": "Is the content reaching the end users who buy and specify lubricants, such as mining, energy, food and marine?",
    })
    comp = f.company.dropna().map(d.company_key).value_counts()
    single = int((comp == 1).sum())
    out.append({
        "type": "Company",
        "headline": f"{single:,} of {comp.size:,} companies ({pct(single, comp.size)}%) sent a single person",
        "rows": [{"label": "Companies sending 1 person", "n": single, "ratio": f"{pct(single, comp.size)}%"},
                 {"label": "Companies sending 2 to 5", "n": int(comp.between(2, 5).sum()), "ratio": f"{pct(comp.between(2, 5).sum(), comp.size)}%"},
                 {"label": "Companies sending 6 or more", "n": int((comp >= 6).sum()), "ratio": f"{pct((comp >= 6).sum(), comp.size)}%"}],
        "opportunity": "Company size isn't captured yet. Add it to the form or pull it from the CRM to test whether smaller specialist firms are under-represented.",
    })
    return out


def coverage(f):
    n = len(f)
    rows = []
    for field, label, _ in d.FIELDS:
        if field not in f.columns:
            continue
        filled = f[field].notna() & (f[field].astype(str).str.strip() != "")
        rows.append({"field": field, "label": label, "pct": pct(filled.sum(), n)})
    return rows


def _latest_per_region(shows):
    """Latest edition with data for each region (or the latest edition if none has data)."""
    have = {code for (code,) in Session(engine).execute(select(Registration.show_code).distinct())}
    best = {}
    for sh in sorted(shows, key=lambda r: -r.year):
        cur = best.get(sh.region)
        if cur is None or (sh.code in have and cur.code not in have):
            best[sh.region] = sh
    return sorted(best.values(), key=lambda r: d.REGION_ORDER.get(r.region, 9))


def history(segment="attendees"):
    """Year-over-year headline measures for every brand with data."""
    with Session(engine) as s:
        shows = list(s.scalars(select(Show).order_by(Show.year)))
    out = {}
    for show in shows:
        sm = summary(show.code, segment)
        if not sm["meta"]["has_data"]:
            continue
        k, b = sm["kpis"], sm.get("behaviour") or {}
        out.setdefault(show.brand, {"brand": show.brand, "region": show.region, "editions": []})["editions"].append({
            "code": show.code, "year": show.year, "total": k["total"], "countries": k["countries"],
            "senior_pct": k["senior_pct"], "buying_power_pct": k["buying_power_pct"], "buyers_pct": k["buyers_pct"],
            "international_pct": round(100 - k["top_country_pct"], 1), "returning_pct": k["returning_pct"],
            "final7_pct": next((w["pct"] for w in b.get("windows", []) if w["label"] == "Final 7 days"), None),
        })
    return sorted(out.values(), key=lambda r: d.REGION_ORDER.get(r["region"], 9))


def compare(segment="attendees"):
    with Session(engine) as s:
        shows = _latest_per_region(list(s.scalars(select(Show))))
    out = []
    for show in shows:
        sm = summary(show.code, segment)
        row = {"code": show.code, "name": show.name, "region": show.region, "has_data": sm["meta"]["has_data"]}
        if sm["meta"]["has_data"]:
            k, a, b = sm["kpis"], sm["audience"], sm.get("behaviour") or {}
            row.update({
                "total": k["total"], "countries": k["countries"], "companies": k["companies"],
                "senior_pct": k["senior_pct"], "buying_power_pct": k["buying_power_pct"],
                "buyers_pct": k["buyers_pct"], "top_country": k["top_country"],
                "top_country_pct": k["top_country_pct"], "returning_pct": k["returning_pct"],
                "final7_pct": next((w["pct"] for w in b.get("windows", []) if w["label"] == "Final 7 days"), None),
                "first30_pct": next((w["pct"] for w in b.get("windows", []) if w["label"] == "First 30 days"), None),
                "top_countries": [c["label"] for c in sm["geography"]["countries"][:10]],
                "seniority": a["seniority"], "industry_group": a["industry_group"],
            })
        out.append(row)
    return out
