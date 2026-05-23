#!/usr/bin/env python3
"""
Salinas Maya Natural — Daily Dashboard Updater
Open-Meteo ERA5 + WorldTides + bilingual EN/ES toggle
"""
import json, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from math import pi, cos

# ── CONFIG ────────────────────────────────────────────────────
LAT  = 13.8262
LON  = -90.2971
TZ   = "America/Guatemala"
YRS  = 5
KEY  = "d5c3fb60-7908-405d-94c6-13ad987658ae"
DAYS = 10
W1, W2, W3 = 1.8, 2.2, 2.5   # tide thresholds
WS  = 15                        # south wind km/h threshold
RM  = 20                        # rain mm threshold
OUT = "salina_historical.html"

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def climate():
    e = datetime.now(timezone.utc) - timedelta(days=2)
    s = e - timedelta(days=365*YRS)
    sf, ef = s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
    v = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,relative_humidity_2m_max,relative_humidity_2m_min,precipitation_sum,wind_speed_10m_mean"
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={sf}&end_date={ef}&daily={v}&timezone={TZ}&wind_speed_unit=kmh"
    print("[Climate] fetching...")
    d = get(url)["daily"]
    print(f"  {len(d['time'])} days · {sf} → {ef}")
    return d, sf, ef

def forecast():
    vars_ = "precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant,temperature_2m_max,temperature_2m_min,relative_humidity_2m_max,relative_humidity_2m_min"
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily={vars_}&forecast_days=10&past_days=60&timezone={TZ}&wind_speed_unit=kmh"
    print("[Forecast] fetching...")
    return get(url)["daily"]

def tides():
    url = f"https://www.worldtides.info/api/v3?lat={LAT}&lon={LON}&key={KEY}&days={DAYS}&heights=1&extremes=1&datum=MSL&step=3600"
    print("[Tides] fetching...")
    d = get(url)
    print(f"  credits: {d.get('callCount','?')}")
    return d

def moon():
    ref = datetime(2000,1,6,18,14, tzinfo=timezone.utc)
    syn = 29.530588853
    pos = ((datetime.now(timezone.utc)-ref).total_seconds()/86400 % syn)/syn
    ill = round((1-cos(2*pi*pos))/2*100)
    names = ["New Moon","Waxing Crescent","First Quarter","Waxing Gibbous",
             "Full Moon","Waning Gibbous","Last Quarter","Waning Crescent"]
    emojis= ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    idx   = int(pos*8)%8
    d2s   = round((0.5-pos if pos<0.5 else 1.5-pos)*syn, 1)
    syzy  = pos<0.05 or pos>0.95 or 0.45<pos<0.55
    return names[idx], emojis[idx], ill, d2s, syzy

def process_climate(daily):
    by = {}
    for i,ds in enumerate(daily["time"]):
        k = ds[:7]
        if k not in by: by[k] = {f:[] for f in ["tmax","tmin","tmean","rh","prec","wind"]}
        b = by[k]
        def p(a,v):
            if v is not None: a.append(v)
        p(b["tmax"],  daily["temperature_2m_max"][i])
        p(b["tmin"],  daily["temperature_2m_min"][i])
        p(b["tmean"], daily["temperature_2m_mean"][i])
        mx = daily["relative_humidity_2m_max"][i]
        mn = daily["relative_humidity_2m_min"][i]
        if mx and mn: b["rh"].append((mx+mn)/2)
        elif mx: b["rh"].append(mx)
        p(b["prec"],  daily["precipitation_sum"][i])
        p(b["wind"],  daily["wind_speed_10m_mean"][i])

    def avg(a): return round(sum(a)/len(a),2) if a else None

    monthly = {}
    for k,b in sorted(by.items()):
        tm=avg(b["tmax"]); rh=avg(b["rh"]); wi=avg(b["wind"])
        ev = round((tm*(1-rh/100)*(wi**0.5))/10,3) if (tm and rh and wi) else None
        monthly[k] = {"tmax":tm,"tmin":avg(b["tmin"]),"tmean":avg(b["tmean"]),
                      "rh":rh,"prec":round(sum(b["prec"]),1) if b["prec"] else None,
                      "wind":wi,"evap":ev}

    seas = {m:{f:[] for f in ["tmax","tmin","rh","prec","wind","evap"]} for m in range(1,13)}
    for k,r in monthly.items():
        m = int(k[5:7])
        for f in seas[m]:
            if r[f] is not None: seas[m][f].append(r[f])
    sa = {m:{f:(round(sum(seas[m][f])/len(seas[m][f]),2) if seas[m][f] else None)
             for f in seas[m]} for m in range(1,13)}
    return monthly, sa

def calc_kpis(monthly):
    def fl(f): return [v[f] for v in monthly.values() if v[f]]
    def av(a): return round(sum(a)/len(a),2) if a else None
    tm=fl("tmax"); tn=fl("tmin"); rh=fl("rh"); pr=fl("prec"); wi=fl("wind"); ev=fl("evap")
    return {"avg_tmax":av(tm),"peak_tmax":round(max(tm),1) if tm else None,
            "avg_tmin":av(tn),"low_tmin":round(min(tn),1) if tn else None,
            "avg_rh":av(rh),"avg_rain_yr":round((av(pr) or 0)*12,0),
            "avg_rain_mo":av(pr),"avg_wind":av(wi),"avg_evap":av(ev)}

def harvest_score(tmax, rh, wind, rain):
    """Score 0-10: how good are conditions for salt harvesting today"""
    s = 0.0
    # Temperature (ideal 32-36°C)
    if tmax is None: s += 5
    elif tmax >= 34: s += 10
    elif tmax >= 32: s += 8
    elif tmax >= 30: s += 6
    elif tmax >= 28: s += 4
    else: s += 2
    # Humidity (lower = better, ideal <65%)
    if rh is None: s += 5
    elif rh <= 60: s += 10
    elif rh <= 70: s += 8
    elif rh <= 78: s += 5
    elif rh <= 85: s += 3
    else: s += 1
    # Wind (moderate wind helps evaporation, ideal 8-15 km/h)
    if wind is None: s += 5
    elif 8 <= wind <= 15: s += 10
    elif 5 <= wind <= 20: s += 7
    elif wind > 20: s += 5
    else: s += 3
    # Rain (any rain hurts)
    if rain is None: s += 5
    elif rain == 0: s += 10
    elif rain < 5: s += 7
    elif rain < 20: s += 3
    else: s += 0
    return round(s / 4, 1)

def calc_risks(tide_data, fc, mn):
    _,_,_,d2s,syzy = mn
    hi = {}
    for ex in tide_data.get("extremes",[]):
        if ex["type"] != "High": continue
        ds = datetime.fromtimestamp(ex["dt"], tz=timezone.utc).strftime("%Y-%m-%d")
        hi[ds] = max(hi.get(ds,0), ex["height"])
    fp = {fc["time"][i]:(fc["precipitation_sum"][i] or 0) for i in range(len(fc["time"]))}
    fw = {fc["time"][i]:(fc["wind_speed_10m_max"][i] or 0) for i in range(len(fc["time"]))}
    fd = {fc["time"][i]:(fc["wind_direction_10m_dominant"][i] or 0) for i in range(len(fc["time"]))}
    ftmax = {fc["time"][i]:fc["temperature_2m_max"][i] for i in range(len(fc["time"]))}
    frhmax = {fc["time"][i]:fc["relative_humidity_2m_max"][i] for i in range(len(fc["time"]))}
    frhmin = {fc["time"][i]:fc["relative_humidity_2m_min"][i] for i in range(len(fc["time"]))}
    out = []
    today = datetime.now(timezone.utc).date()
    for i in range(DAYS):
        d = today+timedelta(days=i); ds = d.strftime("%Y-%m-%d")
        tide=hi.get(ds,1.2); rain=fp.get(ds,0); wind=fw.get(ds,0); wdir=fd.get(ds,0)
        tmax=ftmax.get(ds); rhmax=frhmax.get(ds); rhmin=frhmin.get(ds)
        rh = round((rhmax+rhmin)/2) if (rhmax and rhmin) else rhmax
        hs = harvest_score(tmax, rh, wind, rain)
        south = 135<=wdir<=225; sc=0; fx=[]
        if tide>=W3: sc+=3; fx.append("Extreme tide %.2fm" % tide)
        elif tide>=W2: sc+=2; fx.append("High tide %.2fm" % tide)
        elif tide>=W1: sc+=1; fx.append("Elevated tide %.2fm" % tide)
        if syzy and i==0: sc+=2; fx.append("Spring tide (syzygy active)")
        elif d2s<=2 and i<=2: sc+=1; fx.append("Approaching syzygy (%.1fd)" % d2s)
        if south and wind>=WS: sc+=1; fx.append("S wind %.0fkm/h" % wind)
        if rain>=RM: sc+=1; fx.append("Rain %.0fmm forecast" % rain)
        if sc>=5:   lv,co,lb="CRITICAL","#e85050","🔴 CRITICAL"
        elif sc>=3: lv,co,lb="HIGH","#e8b84b","🟠 HIGH"
        elif sc>=2: lv,co,lb="MODERATE","#e3a733","🟡 MODERATE"
        elif sc>=1: lv,co,lb="LOW","#52c9a0","🟢 LOW"
        else:       lv,co,lb="MINIMAL","#6b7d62","⚪ MINIMAL"
        out.append({"date":ds,"dl":d.strftime("%b %d"),"wd":d.strftime("%A")[:3],
                    "tide":round(tide,2),"rain":round(rain,1),"wind":round(wind,1),
                    "tmax":round(tmax,1) if tmax else None,"rh":rh,
                    "south":south,"score":sc,"level":lv,"color":co,"label":lb,"fx":fx,
                    "hs":hs})
    return out

def build(monthly, sa, kp, rs, mn, tide_data, s_date, e_date):
    MN  = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    MNF = ["January","February","March","April","May","June","July",
           "August","September","October","November","December"]
    gt  = (datetime.now(timezone.utc) + timedelta(hours=-6)).strftime("%B %d, %Y at %H:%M Guatemala time")
    mname,memoji,mill,md2s,msyzy = mn
    tr = rs[0]

    # Tide series (every 3h)
    th=[]; tv=[]
    for h in tide_data.get("heights",[]):
        th.append(datetime.fromtimestamp(h["dt"],tz=timezone.utc).strftime("%b %d %H:%M"))
        tv.append(round(h["height"],2))
    th3=th[::3]; tv3=tv[::3]

    # Monthly series
    ks = sorted(monthly.keys())
    def jl(arr): return json.dumps(arr)
    lbs    = ["%s '%s" % (MN[int(k[5:7])-1], k[2:4]) for k in ks]
    tmax_s = [monthly[k]["tmax"]  for k in ks]
    tmin_s = [monthly[k]["tmin"]  for k in ks]
    tmean_s= [monthly[k]["tmean"] for k in ks]
    rh_s   = [monthly[k]["rh"]    for k in ks]
    prec_s = [monthly[k]["prec"]  for k in ks]
    wind_s = [monthly[k]["wind"]  for k in ks]
    evap_s = [monthly[k]["evap"]  for k in ks]

    # Risk series
    rdates  = [r["dl"]    for r in rs]
    rscores = [r["score"] for r in rs]
    rcolors = [r["color"] for r in rs]
    rtides  = [r["tide"]  for r in rs]

    # Seasonal table rows
    emax = max((sa[m]["evap"] or 0) for m in range(1,13))
    rows = ""
    for m in range(1,13):
        r = sa[m]
        er = (r["evap"] or 0)/emax if emax else 0
        bg = "evap-high" if er>0.65 else ("evap-med" if er>0.35 else "evap-low")
        bt = "High ↑"    if er>0.65 else ("Medium →" if er>0.35 else "Low ↓")
        tc = "cell-hot"  if (r["tmax"] or 0)>34  else ""
        nc = "cell-cool" if (r["tmin"] or 0)<22  else ""
        rc = "cell-wet"  if (r["rh"]   or 0)>80  else ("cell-dry" if (r["rh"] or 100)<60 else "")
        pc = "cell-wet"  if (r["prec"] or 0)>200 else ("cell-dry" if (r["prec"] or 100)<30 else "")
        fl = "⚠" if m in [4,5,10,11] else ""
        f1 = lambda v: ("%.1f" % v) if v else "—"
        f0 = lambda v: ("%.0f" % v) if v else "—"
        rows += "<tr><td>%s %s</td><td class='%s'>%s</td><td class='%s'>%s</td><td class='%s'>%s</td><td class='%s'>%s</td><td class='cell-wind'>%s</td><td><span class='evap-badge %s'>%s</span></td></tr>" % (
            MNF[m-1],fl, tc,f1(r["tmax"]), nc,f1(r["tmin"]), rc,f0(r["rh"]),
            pc,f0(r["prec"]), f1(r["wind"]), bg,bt)

    # Risk cards
    bmap = {"CRITICAL":("#e85050","rgba(232,80,80,.15)","#5c1010"),
            "HIGH":    ("#e8b84b","rgba(232,184,75,.15)","#6b4f10"),
            "MODERATE":("#e3a733","rgba(232,184,75,.08)","#6b4f10"),
            "LOW":     ("#52c9a0","rgba(82,201,160,.08)","#1a5c43"),
            "MINIMAL": ("#6b7d62","rgba(107,125,98,.08)","#2a3025")}
    bco,bbg,bbd = bmap[tr["level"]]
    tfx = "".join("<span class='ab-factor'>%s</span>" % x for x in tr["fx"]) or "<span class='ab-factor' style='color:#6b7d62'>No significant risk factors today</span>"

    rcards = ""
    for r in rs[:10]:
        fhtml = "".join("<div class='risk-factor'>%s</div>" % x for x in r["fx"]) or "<div class='risk-factor' style='color:#6b7d62'>No risk factors</div>"
        rcards += "<div class='risk-card' style='border-top-color:%s'><div class='rc-date'>%s<span class='rc-day'>%s</span></div><div class='rc-tide'>%sm</div><div class='rc-label' style='color:%s'>%s</div><div class='rc-factors'>%s</div><div class='rc-stats'><span>🌧 %smm</span><span>💨 %skm/h%s</span></div></div>" % (
            r["color"], r["dl"], r["wd"], r["tide"], r["color"], r["label"],
            fhtml, r["rain"], r["wind"], " ↙S" if r["south"] else "")

    d2s_warn = "⚠ Spring tide imminent" if md2s<=3 else "Next new/full moon"
    d2s_cls  = "amber" if md2s<=3 else "teal"
    tr_kpi_cls = "red" if tr["level"] in ["CRITICAL","HIGH"] else "teal"
    k = kp

    # ── ALL JS DATA (no f-string conflicts) ───────────────────
    # Field conditions: rs already has 10 future days with tmax/rh/wind/rain/hs
    # For past 5 days we need to reference fc directly
    fc_all = tide_data.get("_fc_ref", {})  # passed via tide_data hack - see below

    js_data = "var TH=%s;var TV=%s;var W1=%s;var W2=%s;var W3=%s;var RD=%s;var RS=%s;var RC=%s;var RT=%s;var CL=%s;var CMAX=%s;var CMIN=%s;var CMN=%s;var CRH=%s;var CPR=%s;var CWI=%s;var CEV=%s;" % (
        jl(th3),jl(tv3),W1,W2,W3,
        jl(rdates),jl(rscores),jl(rcolors),jl(rtides),
        jl(lbs),jl(tmax_s),jl(tmin_s),jl(tmean_s),
        jl(rh_s),jl(prec_s),jl(wind_s),jl(evap_s))

    # Field conditions data (past 5 + today + future 10 = 16 days)
    fc_data = tide_data.get("_fc", {})
    fc_dates = fc_data.get("time", [])
    fc_tmax  = fc_data.get("temperature_2m_max", [])
    fc_tmin  = fc_data.get("temperature_2m_min", [])
    fc_rhmax = fc_data.get("relative_humidity_2m_max", [])
    fc_rhmin = fc_data.get("relative_humidity_2m_min", [])
    fc_prec  = fc_data.get("precipitation_sum", [])
    fc_wind  = fc_data.get("wind_speed_10m_max", [])

    today_str = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")

    # Build daily max tide lookup from WorldTides data (extremes)
    tide_daily_max = {}
    for ex in tide_data.get("extremes", []):
        if ex["type"] != "High": continue
        ds = datetime.fromtimestamp(ex["dt"], tz=timezone.utc).strftime("%Y-%m-%d")
        tide_daily_max[ds] = max(tide_daily_max.get(ds, 0), ex["height"])
    # Also from heights (hourly) for any days not in extremes
    for h in tide_data.get("heights", []):
        ds = datetime.fromtimestamp(h["dt"], tz=timezone.utc).strftime("%Y-%m-%d")
        tide_daily_max[ds] = max(tide_daily_max.get(ds, 0), h["height"])

    fc_rows = []
    for i, ds in enumerate(fc_dates):
        tm = fc_tmax[i] if i < len(fc_tmax) else None
        tn = fc_tmin[i] if i < len(fc_tmin) else None
        rhx = fc_rhmax[i] if i < len(fc_rhmax) else None
        rhn = fc_rhmin[i] if i < len(fc_rhmin) else None
        pr = fc_prec[i] if i < len(fc_prec) else None
        wi = fc_wind[i] if i < len(fc_wind) else None
        rh = round((rhx + rhn) / 2) if (rhx and rhn) else rhx
        tide_h = tide_daily_max.get(ds)
        hs = harvest_score(tm, rh, wi, pr or 0)
        past = ds < today_str
        fc_rows.append({
            "ds": ds,
            "dl": datetime.strptime(ds, "%Y-%m-%d").strftime("%b %d"),
            "wd": datetime.strptime(ds, "%Y-%m-%d").strftime("%a"),
            "tmax": round(tm, 1) if tm else None,
            "tmin": round(tn, 1) if tn else None,
            "rh": rh,
            "prec": round(pr, 1) if pr is not None else 0,
            "wind": round(wi, 1) if wi else None,
            "tide": round(tide_h, 2) if tide_h else None,
            "hs": hs,
            "past": past,
            "today": ds == today_str
        })

    # Monthly rain averages for reference line
    monthly_rain_avg = [sa[m]["prec"] for m in range(1, 13)]

    js_field = "var FC=%s;var RAIN_AVG=%s;" % (jl(fc_rows), jl(monthly_rain_avg))

    # ── BUILD HTML (regular strings, NO f-string for CSS/JS) ──
    parts = []

    parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Salinas Maya Natural — Climate &amp; Tide Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Fraunces:ital,wght@0,500;1,500&display=swap');
:root{--bg:#0c0f0a;--bg2:#13170f;--bg3:#1c2117;--border:#2a3025;--text:#dde8d4;--muted:#6b7d62;--teal:#52c9a0;--teal-d:#1a5c43;--amber:#e8b84b;--amber-d:#6b4f10;--coral:#e87070;--blue:#70b8e8;--blue-d:#1a3d5c;--green:#7ed45e;--red:#e85050;--red-d:#5c1010;--purple:#c07ee8;--mono:'DM Mono',monospace;--serif:'Fraunces',serif;}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{font-family:var(--mono);background:var(--bg);color:var(--text);min-height:100vh;}
header{border-bottom:1px solid var(--border);padding:20px 32px 16px;display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;}
.h-badge{width:36px;height:36px;background:linear-gradient(135deg,var(--teal-d),var(--teal));border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:18px;}
.h-title{display:flex;align-items:center;gap:14px;}
h1{font-family:var(--serif);font-size:18px;font-weight:500;}
h1 em{font-style:italic;color:var(--teal);}
.h-sub{font-size:11px;color:var(--muted);margin-top:2px;}
.h-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
.tag{font-size:11px;padding:4px 10px;border-radius:6px;}
.tag-coords{color:var(--muted);background:var(--bg3);border:1px solid var(--border);}
.tag-update{color:var(--teal);background:rgba(82,201,160,.1);border:1px solid var(--teal-d);}
.tag-moon{color:var(--amber);background:rgba(232,184,75,.1);border:1px solid var(--amber-d);}
.tabs{display:flex;border-bottom:1px solid var(--border);padding:0 32px;gap:2px;overflow-x:auto;}
.tab{padding:10px 18px;font-size:12px;font-weight:500;cursor:pointer;border-bottom:2px solid transparent;color:var(--muted);white-space:nowrap;background:none;border-top:none;border-left:none;border-right:none;font-family:var(--mono);}
.tab.active{color:var(--teal);border-bottom-color:var(--teal);}
.panel{display:none;padding:24px 32px 40px;}
.panel.active{display:block;}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px;}
.kpi{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px 18px;position:relative;overflow:hidden;}
.kpi::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;}
.kpi.teal::before{background:var(--teal);}.kpi.amber::before{background:var(--amber);}
.kpi.blue::before{background:var(--blue);}.kpi.purple::before{background:var(--purple);}
.kpi.coral::before{background:var(--coral);}.kpi.red::before{background:var(--red);}
.kpi-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:8px;}
.kpi-val{font-family:var(--serif);font-size:26px;font-weight:500;line-height:1;}
.kpi-unit{font-size:13px;color:var(--muted);margin-left:2px;}
.kpi-sub{font-size:11px;color:var(--muted);margin-top:6px;}
.sec-title{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:14px;}
.chart-card{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:20px;}
.chart-wrap{position:relative;height:220px;}
.chart-wrap-lg{position:relative;height:280px;}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.risk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px;margin-bottom:20px;}
.risk-card{background:var(--bg2);border:1px solid var(--border);border-top:3px solid;border-radius:10px;padding:14px 16px;}
.rc-date{font-size:13px;font-weight:500;display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;}
.rc-day{font-size:10px;color:var(--muted);}
.rc-tide{font-family:var(--serif);font-size:28px;font-weight:500;line-height:1;margin-bottom:6px;}
.rc-label{font-size:11px;font-weight:500;margin-bottom:8px;}
.rc-factors{display:flex;flex-direction:column;gap:3px;margin-bottom:8px;}
.risk-factor{font-size:10px;color:var(--muted);}
.rc-stats{font-size:10px;color:var(--muted);display:flex;gap:10px;}
.alert-banner{margin:16px 32px;padding:16px 20px;border-radius:10px;display:flex;align-items:center;gap:16px;flex-wrap:wrap;}
.ab-main{flex:1;}
.ab-title{font-family:var(--serif);font-size:17px;font-weight:500;}
.ab-sub{font-size:12px;color:var(--muted);margin-top:4px;}
.ab-factors{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;}
.ab-factor{font-size:11px;padding:2px 10px;border-radius:12px;background:rgba(255,255,255,.06);color:var(--text);}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{text-align:right;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border);}
th:first-child{text-align:left;}
td{text-align:right;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:var(--text);}
td:first-child{text-align:left;color:var(--muted);}
tr:hover td{background:rgba(255,255,255,.02);}
.cell-hot{color:var(--coral);}.cell-cool{color:var(--blue);}
.cell-wet{color:var(--blue);}.cell-dry{color:var(--amber);}.cell-wind{color:var(--purple);}
.evap-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;}
.evap-high{background:rgba(82,201,160,.15);color:var(--teal);}
.evap-med{background:rgba(232,184,75,.15);color:var(--amber);}
.evap-low{background:rgba(232,112,112,.15);color:var(--coral);}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;}
.legend-item{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);}
.legend-dot{width:10px;height:10px;border-radius:2px;}
.season-bar{display:flex;height:28px;border-radius:6px;overflow:hidden;margin-top:12px;border:1px solid var(--border);}
.seg{display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;text-transform:uppercase;}
.seg-dry{background:rgba(227,167,51,.25);color:var(--amber);}
.seg-wet{background:rgba(88,166,255,.2);color:var(--blue);}
footer{padding:24px 32px 0;font-size:11px;color:var(--muted);border-top:1px solid var(--border);margin-top:32px;display:flex;gap:24px;flex-wrap:wrap;}
@media(max-width:700px){.two-col{grid-template-columns:1fr;}header,.tabs,.panel,.alert-banner,footer{padding-left:16px;padding-right:16px;}.alert-banner{margin:12px 16px;}}
</style>
</head>
<body>
""")

    # Dynamic HTML sections
    parts.append("""<header>
  <div class="h-title">
    <div class="h-badge">🧂</div>
    <div>
      <h1>Salinas Maya Natural — <em>Climate &amp; Tide Intelligence</em></h1>
      <div class="h-sub" id="t-subtitle">Historical record · 10-day tide forecast · Flood risk index · Auto-updated daily</div>
    </div>
  </div>
  <div class="h-right">
    <div class="tag tag-coords">13.8262°N, 90.2971°W · Chiquimulilla, Santa Rosa, GT</div>
""")
    parts.append('    <div class="tag tag-moon">%s %s &middot; %s%% &middot; %sd to syzygy</div>\n' % (memoji, mname, mill, md2s))
    parts.append('    <div class="tag tag-update">&#8635; %s</div>\n' % gt)
    parts.append("""  </div>
</header>
""")

    # Alert banner
    parts.append('<div class="alert-banner" style="border:1px solid %s;background:%s">\n' % (bbd, bbg))
    parts.append('  <div style="font-size:36px">%s</div>\n' % tr["label"].split()[0])
    parts.append('  <div class="ab-main">\n')
    parts.append('    <div class="ab-title" style="color:%s"><span id="t-flood-risk">Today\'s Flood Risk</span>: %s</div>\n' % (bco, tr["level"]))
    parts.append('    <div class="ab-sub">Max tide: %sm &middot; Rain: %smm &middot; Wind: %s km/h &middot; %s %s</div>\n' % (tr["tide"], tr["rain"], tr["wind"], memoji, mname))
    hs_color = "#52c9a0" if tr["hs"] >= 7 else "#e8b84b" if tr["hs"] >= 5 else "#e87070"
    hs_label = "Optimal" if tr["hs"] >= 7 else "Good" if tr["hs"] >= 5 else "Poor"
    parts.append('    <div class="ab-factors"><span class="ab-factor">🌾 Harvest conditions: <strong style="color:%s">%s (%s/10)</strong></span></div>\n' % (hs_color, hs_label, tr["hs"]))
    parts.append('    <div class="ab-factors">%s</div>\n' % tfx)
    parts.append("""  </div>
</div>
""")

    # Tabs
    parts.append("""<div class="tabs">
  <button class="tab active" onclick="switchTab('tides',this)"><span id="t-tab1">🌊 Tide Forecast</span></button>
  <button class="tab" onclick="switchTab('risk',this)"><span id="t-tab2">⚠ Risk Index</span></button>
  <button class="tab" onclick="switchTab('rain',this)">🌧 Rain Forecast</button>
  <button class="tab" onclick="switchTab('field',this)">🌡 Field Conditions</button>
  <button class="tab" onclick="switchTab('climate',this)"><span id="t-tab3">📊 Climate Record</span></button>
  <button class="tab" onclick="switchTab('seasonal',this)"><span id="t-tab4">📅 Seasonal Pattern</span></button>
</div>
""")

    # Tab: Tides
    parts.append("""<div id="tab-tides" class="panel active">
  <div class="kpi-grid">
""")
    parts.append('    <div class="kpi %s"><div class="kpi-label" id="t-kpi1">Today\'s max tide</div><div class="kpi-val" style="color:%s">%s<span class="kpi-unit">m</span></div><div class="kpi-sub">Risk: %s</div></div>\n' % (tr_kpi_cls, bco, tr["tide"], tr["level"]))
    parts.append('    <div class="kpi amber"><div class="kpi-label" id="t-kpi2">Moon phase</div><div class="kpi-val" style="font-size:32px">%s</div><div class="kpi-sub">%s &middot; %s%% illuminated</div></div>\n' % (memoji, mname, mill))
    parts.append('    <div class="kpi %s"><div class="kpi-label" id="t-kpi3">Days to syzygy</div><div class="kpi-val">%s<span class="kpi-unit">d</span></div><div class="kpi-sub">%s</div></div>\n' % (d2s_cls, md2s, d2s_warn))
    parts.append('    <div class="kpi blue"><div class="kpi-label" id="t-kpi4">Critical threshold</div><div class="kpi-val">%.1f<span class="kpi-unit">m</span></div><div class="kpi-sub">Apr 28 2024 flood ref.</div></div>\n' % W3)
    parts.append("""  </div>
  <div class="sec-title" id="t-sec1">Hourly tide heights — next 10 days (WorldTides · MSL datum)</div>
  <div class="chart-card">
    <div class="chart-wrap-lg"><canvas id="chart-tides"></canvas></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--blue)"></div>Tide height (m)</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--red);opacity:.6"></div>Critical threshold</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--amber);opacity:.6"></div>Warning threshold</div>
    </div>
  </div>
  <div class="sec-title" id="t-sec2">10-day risk calendar</div>
  <div class="risk-grid">
""")
    parts.append(rcards)
    parts.append("  </div>\n</div>\n")

    # Tab: Risk
    parts.append("""<div id="tab-risk" class="panel">
  <div class="chart-card" style="margin-bottom:20px;font-size:12px;color:var(--muted);line-height:1.9">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div>
        <div style="color:var(--text);font-weight:500;margin-bottom:8px" id="t-risk-factors-title">Risk factors scored daily:</div>
""")
    parts.append('        <div>Tide &ge; %.1fm +1pt | &ge;%.1fm +2pts | &ge;%.1fm +3pts</div>\n' % (W1,W2,W3))
    parts.append("""        <div>Spring tide active (syzygy) +2pts</div>
        <div>Approaching syzygy (&le;2 days) +1pt</div>
""")
    parts.append('        <div>Southerly wind &ge; %d km/h +1pt</div>\n' % WS)
    parts.append('        <div>Rainfall forecast &ge; %dmm +1pt</div>\n' % RM)
    parts.append("""      </div>
      <div>
        <div style="color:var(--text);font-weight:500;margin-bottom:8px" id="t-risk-levels-title">Risk levels:</div>
        <div><span style="color:var(--red)">🔴 CRITICAL</span> &ge;5 pts</div>
        <div><span style="color:var(--amber)">🟠 HIGH</span> &ge;3 pts</div>
        <div><span style="color:var(--amber)">🟡 MODERATE</span> &ge;2 pts</div>
        <div><span style="color:var(--teal)">🟢 LOW</span> &ge;1 pt</div>
        <div><span style="color:var(--muted)">⚪ MINIMAL</span> 0 pts</div>
      </div>
    </div>
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
      &#x26a0; Calibrated to the <strong style="color:var(--text)">April 28, 2024 flood event</strong>.
      Model would have issued a <strong style="color:var(--red)">CRITICAL alert 5 days in advance</strong>.
    </div>
  </div>
  <div class="sec-title" id="t-sec4">10-day risk score &amp; tide height</div>
  <div class="chart-card"><div class="chart-wrap"><canvas id="chart-risk"></canvas></div></div>
</div>
""")

    # Tab: Climate
    parts.append('<div id="tab-climate" class="panel">\n  <div class="kpi-grid">\n')
    parts.append('    <div class="kpi coral"><div class="kpi-label" id="t-kpi5">Avg max temp</div><div class="kpi-val">%s<span class="kpi-unit">&deg;C</span></div><div class="kpi-sub">Peak: %s&deg;C</div></div>\n' % (k["avg_tmax"], k["peak_tmax"]))
    parts.append('    <div class="kpi blue"><div class="kpi-label" id="t-kpi6">Avg min temp</div><div class="kpi-val">%s<span class="kpi-unit">&deg;C</span></div><div class="kpi-sub">Low: %s&deg;C</div></div>\n' % (k["avg_tmin"], k["low_tmin"]))
    parts.append('    <div class="kpi teal"><div class="kpi-label" id="t-kpi7">Avg humidity</div><div class="kpi-val">%s<span class="kpi-unit">%%</span></div><div class="kpi-sub">Monthly relative avg</div></div>\n' % k["avg_rh"])
    parts.append('    <div class="kpi blue"><div class="kpi-label" id="t-kpi8">Est. annual rainfall</div><div class="kpi-val">%d<span class="kpi-unit">mm</span></div><div class="kpi-sub">%s mm/month</div></div>\n' % (int(k["avg_rain_yr"]), k["avg_rain_mo"]))
    parts.append('    <div class="kpi purple"><div class="kpi-label" id="t-kpi9">Avg wind</div><div class="kpi-val">%s<span class="kpi-unit">km/h</span></div><div class="kpi-sub">At 10m height</div></div>\n' % k["avg_wind"])
    parts.append('    <div class="kpi amber"><div class="kpi-label" id="t-kpi10">Avg evap. index</div><div class="kpi-val">%s<span class="kpi-unit">pts</span></div><div class="kpi-sub">Salt production potential</div></div>\n' % k["avg_evap"])
    parts.append("""  </div>
  <div class="sec-title" id="t-sec5">Monthly temperature record</div>
  <div class="chart-card">
    <div class="chart-wrap"><canvas id="chart-temp"></canvas></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--coral)"></div>Max</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--blue)"></div>Min</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--amber)"></div>Mean</div>
    </div>
  </div>
  <div class="two-col">
    <div>
      <div class="sec-title" id="t-sec6">Relative humidity (%)</div>
      <div class="chart-card"><div class="chart-wrap"><canvas id="chart-hum"></canvas></div></div>
    </div>
    <div>
      <div class="sec-title" id="t-sec7">Monthly precipitation (mm)</div>
      <div class="chart-card"><div class="chart-wrap"><canvas id="chart-prec"></canvas></div></div>
    </div>
  </div>
  <div class="sec-title" id="t-sec8">Evaporation index — salt production potential</div>
  <div class="chart-card">
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px">Formula: Evap = (T_max &times; (1 &minus; RH/100) &times; &radic;Wind) / 10</div>
    <div class="chart-wrap"><canvas id="chart-evap"></canvas></div>
  </div>
</div>
""")

    # Tab: Seasonal
    parts.append("""<div id="tab-seasonal" class="panel">
  <div class="chart-card">
    <div style="font-size:11px;color:var(--muted);margin-bottom:6px" id="t-seasonal-note">&#x26a0; = historically elevated tide flood risk</div>
    <div class="season-bar">
      <div class="seg seg-dry" style="width:33.3%" id="t-seg-dry1">Dry (Jan&ndash;Apr)</div>
      <div class="seg seg-wet" style="width:50%" id="t-seg-wet">Rainy (May&ndash;Oct)</div>
      <div class="seg seg-dry" style="width:16.7%" id="t-seg-dry2">Dry (Nov&ndash;Dec)</div>
    </div>
    <div style="overflow-x:auto;margin-top:16px">
      <table>
        <thead><tr><th>Month</th><th>Max &deg;C</th><th>Min &deg;C</th><th>Humidity %</th><th>Rainfall mm</th><th>Wind km/h</th><th>Evap. index</th></tr></thead>
        <tbody>
""")
    parts.append(rows)
    parts.append("""        </tbody>
      </table>
    </div>
  </div>
</div>
""")

    # Tab: Rain Forecast
    parts.append("""<div id="tab-rain" class="panel">
  <div class="sec-title">10-day rainfall forecast</div>
  <div class="chart-card">
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px">Daily precipitation forecast (mm) vs. monthly historical average &middot; Open-Meteo</div>
    <div class="chart-wrap-lg"><canvas id="chart-rain"></canvas></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:#70b8e8"></div>Forecast (mm/day)</div>
      <div class="legend-item"><div class="legend-dot" style="background:rgba(232,184,75,.5)"></div>Monthly historical avg (mm/day)</div>
      <div class="legend-item"><div class="legend-dot" style="background:rgba(232,80,80,.4)"></div>Threshold &ge;20mm (risk)</div>
    </div>
  </div>
  <div class="sec-title">Rainfall risk breakdown</div>
  <div id="rain-cards" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin-bottom:20px"></div>
</div>
""")

    # Tab: Field Conditions
    parts.append("""<div id="tab-field" class="panel">
  <div class="sec-title">Field conditions &mdash; past 5 days &amp; next 10</div>
  <div style="font-size:11px;color:var(--muted);margin-bottom:14px">Harvest score: 0&ndash;10 composite index &middot; temperature + humidity + wind + rainfall &middot; green &ge;7 optimal &middot; amber 5&ndash;7 good &middot; red &lt;5 poor</div>
  <div class="chart-card" style="margin-bottom:20px">
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px">Harvest score trend &middot; 15-day window</div>
    <div class="chart-wrap"><canvas id="chart-harvest"></canvas></div>
  </div>
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:12px" id="field-table">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Date</th>
          <th style="text-align:right;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Max &deg;C</th>
          <th style="text-align:right;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Humidity %</th>
          <th style="text-align:right;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Wind km/h</th>
          <th style="text-align:right;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Rain mm</th>
          <th style="text-align:right;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Tide m</th>
          <th style="text-align:center;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);border-bottom:1px solid var(--border)">Harvest Score</th>
        </tr>
      </thead>
      <tbody id="field-tbody"></tbody>
    </table>
  </div>
</div>
""")

    # Footer
    parts.append('<footer>\n')
    parts.append('  <span>Climate: Open-Meteo ERA5-Land &middot; ECMWF</span>\n')
    parts.append('  <span>Tides: WorldTides API &middot; MSL datum</span>\n')
    parts.append('  <span>13.8262&deg;N, 90.2971&deg;W &middot; Chiquimulilla, Santa Rosa, Guatemala</span>\n')
    parts.append('  <span>Auto-updated daily 06:00 AM GT &middot; Last run: %s</span>\n' % gt)
    parts.append('</footer>\n')

    # JavaScript (plain string, no f-string)
    parts.append('<script>\n')
    parts.append(js_data + "\n")
    parts.append(js_field + "\n")
    parts.append("""
var G='rgba(42,48,37,0.7)';
Chart.defaults.color='#6b7d62';
Chart.defaults.font.family="'DM Mono',monospace";
Chart.defaults.font.size=11;
var bO={responsive:true,maintainAspectRatio:false,
  plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false,backgroundColor:'#1c2117',borderColor:'#2a3025',borderWidth:1,titleColor:'#dde8d4',bodyColor:'#6b7d62',padding:10}},
  scales:{x:{grid:{color:G},ticks:{maxTicksLimit:20,maxRotation:45}},y:{grid:{color:G}}}};

var CI={};
function mk(id,cfg){if(CI[id])CI[id].destroy();CI[id]=new Chart(document.getElementById(id),cfg);}

function initTides(){
  mk('chart-tides',{type:'line',data:{labels:TH,datasets:[
    {label:'Tide (m)',data:TV,borderColor:'#70b8e8',backgroundColor:'rgba(112,184,232,.12)',fill:true,tension:.4,pointRadius:0,borderWidth:2},
    {label:'Critical',data:Array(TH.length).fill(W3),borderColor:'rgba(232,80,80,.6)',borderDash:[4,4],backgroundColor:'transparent',fill:false,pointRadius:0,borderWidth:1.5},
    {label:'Warning', data:Array(TH.length).fill(W1),borderColor:'rgba(232,184,75,.4)',borderDash:[4,4],backgroundColor:'transparent',fill:false,pointRadius:0,borderWidth:1}
  ]},options:{...bO,plugins:{...bO.plugins,legend:{display:true,labels:{color:'#6b7d62',boxWidth:24,font:{size:11}}}},
    scales:{...bO.scales,y:{...bO.scales.y,min:Math.floor((Math.min.apply(null,TV)-0.3)*2)/2,max:Math.ceil((Math.max.apply(null,TV.concat([W3]))+0.3)*2)/2,title:{display:true,text:'meters (MSL)',color:'#6b7d62',font:{size:10}}}}}});
}

function initRisk(){
  mk('chart-risk',{type:'bar',data:{labels:RD,datasets:[
    {type:'bar',label:'Risk score',data:RS,backgroundColor:RC.map(function(c){return c+'99';}),borderColor:RC,borderWidth:1,borderRadius:4,yAxisID:'y1'},
    {type:'line',label:'Max tide (m)',data:RT,borderColor:'#70b8e8',backgroundColor:'rgba(112,184,232,.1)',fill:true,tension:.4,pointRadius:4,pointBackgroundColor:'#70b8e8',borderWidth:2,yAxisID:'y2'}
  ]},options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:true,labels:{color:'#6b7d62',boxWidth:12,font:{size:11}}},tooltip:{mode:'index',intersect:false,backgroundColor:'#1c2117',borderColor:'#2a3025',borderWidth:1,titleColor:'#dde8d4',bodyColor:'#6b7d62',padding:10}},
    scales:{x:{grid:{color:G}},
      y1:{type:'linear',position:'left',grid:{color:G},min:0,max:8,ticks:{stepSize:1},title:{display:true,text:'Risk score',color:'#6b7d62',font:{size:10}}},
      y2:{type:'linear',position:'right',grid:{display:false},min:0,max:3.5,title:{display:true,text:'Tide (m)',color:'#70b8e8',font:{size:10}},ticks:{color:'#70b8e8'}}}}});
}

function initClimate(){
  mk('chart-temp',{type:'line',data:{labels:CL,datasets:[
    {label:'Max', data:CMAX,borderColor:'#e87070',fill:false,tension:.35,pointRadius:0,borderWidth:1.5},
    {label:'Min', data:CMIN,borderColor:'#70b8e8',fill:false,tension:.35,pointRadius:0,borderWidth:1.5},
    {label:'Mean',data:CMN, borderColor:'#e8b84b',fill:false,tension:.35,pointRadius:0,borderWidth:1,borderDash:[4,3]}
  ]},options:{...bO,plugins:{...bO.plugins,legend:{display:true,labels:{color:'#6b7d62',boxWidth:12,font:{size:11}}}}}});
  mk('chart-hum',{type:'line',data:{labels:CL,datasets:[
    {label:'RH%',data:CRH,borderColor:'#52c9a0',backgroundColor:'rgba(82,201,160,.1)',fill:true,tension:.4,pointRadius:0,borderWidth:1.5}
  ]},options:{...bO,scales:{...bO.scales,y:{...bO.scales.y,min:40,max:100}}}});
  mk('chart-prec',{type:'bar',data:{labels:CL,datasets:[
    {label:'mm',data:CPR,backgroundColor:'rgba(112,184,232,.45)',borderColor:'#70b8e8',borderWidth:0.5,borderRadius:2}
  ]},options:{...bO}});
  var em=Math.max.apply(null,CEV.filter(function(v){return v!=null;}));
  mk('chart-evap',{type:'bar',data:{labels:CL,datasets:[
    {label:'Evap.',data:CEV,backgroundColor:CEV.map(function(v){
      if(!v)return 'rgba(125,133,144,.3)';
      var r=v/em;
      return r>0.65?'rgba(82,201,160,.6)':r>0.35?'rgba(232,184,75,.5)':'rgba(232,112,112,.4)';
    }),borderWidth:0,borderRadius:3}
  ]},options:{...bO}});
}

function initRain(){
  var today = new Date().toISOString().slice(0,10);
  var labels = FC.map(function(r){return r.past ? r.dl+' ★' : r.today ? r.dl+' ◆' : r.dl;});
  var prec   = FC.map(function(r){return r.prec;});
  var colors = FC.map(function(r){
    if(r.past) return 'rgba(107,125,98,.4)';
    if(r.prec>=20) return 'rgba(232,80,80,.7)';
    if(r.prec>=10) return 'rgba(232,184,75,.7)';
    return 'rgba(112,184,232,.6)';
  });
  // Monthly avg per day for reference - map each date to its month avg/30
  var avgLine = FC.map(function(r){
    var m = parseInt(r.ds.slice(5,7))-1;
    return RAIN_AVG[m] ? Math.round(RAIN_AVG[m]/30*10)/10 : null;
  });
  mk('chart-rain',{type:'bar',data:{labels:labels,datasets:[
    {type:'bar',label:'Forecast mm/day',data:prec,backgroundColor:colors,borderWidth:0,borderRadius:3},
    {type:'line',label:'Monthly hist. avg (mm/day)',data:avgLine,borderColor:'rgba(232,184,75,.6)',borderDash:[4,3],fill:false,pointRadius:0,borderWidth:1.5},
    {type:'line',label:'Risk threshold (20mm)',data:Array(FC.length).fill(20),borderColor:'rgba(232,80,80,.35)',borderDash:[4,4],fill:false,pointRadius:0,borderWidth:1}
  ]},options:{...bO,plugins:{...bO.plugins,legend:{display:true,labels:{color:'#6b7d62',boxWidth:10,font:{size:10}}}},
    scales:{...bO.scales,y:{...bO.scales.y,min:0,title:{display:true,text:'mm',color:'#6b7d62',font:{size:10}}}}}});
  // Rain cards (future only)
  var cards = document.getElementById('rain-cards');
  cards.innerHTML = '';
  FC.filter(function(r){return !r.past;}).forEach(function(r){
    var c=r.prec>=20?'var(--red)':r.prec>=10?'var(--amber)':'var(--teal)';
    var d=document.createElement('div');
    d.style.cssText='background:var(--bg2);border:1px solid var(--border);border-top:2px solid '+c+';border-radius:8px;padding:10px 12px;text-align:center';
    d.innerHTML='<div style="font-size:11px;color:var(--muted)">'+r.dl+(r.today?' <b style="color:var(--amber)">TODAY</b>':'')+'</div>'
      +'<div style="font-family:var(--serif);font-size:22px;color:'+c+'">'+r.prec+'<span style="font-size:11px;color:var(--muted)">mm</span></div>'
      +'<div style="font-size:10px;color:var(--muted)">'+r.wd+'</div>';
    cards.appendChild(d);
  });
}

function initField(){
  var labels = FC.map(function(r){return r.past ? r.dl+' ★' : r.today ? r.dl+' ◆' : r.dl;});
  var scores = FC.map(function(r){return r.hs;});
  var scoreColors = scores.map(function(s){return s>=7?'rgba(82,201,160,.7)':s>=5?'rgba(232,184,75,.7)':'rgba(232,112,112,.7)';});
  var tides_fc = FC.map(function(r){return r.tide||null;});
  mk('chart-harvest',{type:'bar',data:{labels:labels,datasets:[
    {type:'bar',label:'Harvest score',data:scores,backgroundColor:scoreColors,borderWidth:0,borderRadius:4,yAxisID:'y1'},
    {type:'line',label:'Optimal (7)',data:Array(FC.length).fill(7),borderColor:'rgba(82,201,160,.3)',borderDash:[4,3],fill:false,pointRadius:0,borderWidth:1,yAxisID:'y1'},
    {type:'line',label:'Max tide (m)',data:tides_fc,borderColor:'#70b8e8',backgroundColor:'rgba(112,184,232,.08)',fill:true,tension:.4,pointRadius:2,borderWidth:1.5,yAxisID:'y2',spanGaps:true}
  ]},options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:true,labels:{color:'#6b7d62',boxWidth:10,font:{size:10}}},tooltip:{mode:'index',intersect:false,backgroundColor:'#1c2117',borderColor:'#2a3025',borderWidth:1,titleColor:'#dde8d4',bodyColor:'#6b7d62',padding:10}},
    scales:{x:{grid:{color:G}},
      y1:{type:'linear',position:'left',grid:{color:G},min:0,max:10,ticks:{stepSize:2},title:{display:true,text:'Harvest score',color:'#6b7d62',font:{size:9}}},
      y2:{type:'linear',position:'right',grid:{display:false},min:0,max:3.5,title:{display:true,text:'Tide (m)',color:'#70b8e8',font:{size:9}},ticks:{color:'#70b8e8'}}}}});
  // Field table
  document.getElementById('field-tbody').innerHTML = FC.map(function(r){
    var sc = r.hs>=7?'var(--teal)':r.hs>=5?'var(--amber)':'var(--red)';
    var bg = r.today?'background:rgba(232,184,75,.06)':'';
    var lbl = r.today?' <span style="font-size:9px;background:rgba(232,184,75,.25);color:var(--amber);padding:1px 5px;border-radius:3px">TODAY</span>':r.past?' <span style="font-size:9px;color:var(--muted)">★</span>':'';
    return '<tr style="'+bg+'">'
      +'<td style="padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:var(--muted)">'+r.dl+lbl+'</td>'
      +'<td style="text-align:right;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:'+(r.tmax>=34?'var(--coral)':'var(--text)')+'">'+( r.tmax||'—')+'</td>'
      +'<td style="text-align:right;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:'+(r.rh>80?'var(--blue)':r.rh<60?'var(--amber)':'var(--text)')+'">'+( r.rh||'—')+'</td>'
      +'<td style="text-align:right;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:var(--purple)">'+( r.wind||'—')+'</td>'
      +'<td style="text-align:right;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:'+(r.prec>=20?'var(--red)':r.prec>0?'var(--blue)':'var(--muted)')+'">'+r.prec+'</td>'
      +'<td style="text-align:right;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5);color:'+(r.tide&&r.tide>=1.8?'var(--amber)':r.tide&&r.tide>=2.2?'var(--red)':'var(--muted)')+'">'+(r.tide||'—')+'</td>'
      +'<td style="text-align:center;padding:7px 10px;border-bottom:1px solid rgba(42,48,37,.5)"><span style="font-family:var(--serif);font-size:16px;color:'+sc+'">'+r.hs+'</span></td>'
      +'</tr>';
  }).join('');
}

function switchTab(id,el){
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});
  document.getElementById('tab-'+id).classList.add('active');
  el.classList.add('active');
  if(id==='tides')   initTides();
  if(id==='risk')    initRisk();
  if(id==='rain')    initRain();
  if(id==='field')   initField();
  if(id==='climate') initClimate();
}

initTides();
""")
    parts.append('</script>\n</body>\n</html>\n')

    return "".join(parts)


def main():
    print("="*60)
    print("Run time:", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print("="*60)
    mn = moon()
    print("[Moon] %s %s · %d%% · %.1fd to syzygy" % (mn[1],mn[0],mn[2],mn[3]))
    daily, s, e = climate()
    fc = forecast()
    td = tides()
    td["_fc"] = fc  # pass forecast data into build via tide_data
    monthly, sa = process_climate(daily)
    kp = calc_kpis(monthly)
    rs = calc_risks(td, fc, mn)
    print("[Risk] Today: %s (score %d) · tide %.2fm · harvest score %.1f" % (rs[0]["level"],rs[0]["score"],rs[0]["tide"],rs[0]["hs"]))
    html = build(monthly, sa, kp, rs, mn, td, s, e)
    Path(OUT).write_text(html, encoding="utf-8")
    print("✓ Written: %s (%.1f KB)" % (OUT, Path(OUT).stat().st_size/1024))

if __name__ == "__main__":
    main()
