#!/usr/bin/env python3
"""
Salinas Maya Natural — Actualizador diario (español)
Open-Meteo ERA5 + WorldTides
"""
import json, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from math import pi, cos

LAT  = 13.8262
LON  = -90.2971
TZ   = "America/Guatemala"
YRS  = 5
KEY  = "d5c3fb60-7908-405d-94c6-13ad987658ae"
DAYS = 10
W1, W2, W3 = 1.8, 2.2, 2.5
WS  = 15
RM  = 20
OUT = "salina_historico.html"

def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def climate():
    e = datetime.now(timezone.utc) - timedelta(days=2)
    s = e - timedelta(days=365*YRS)
    sf, ef = s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
    v = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,relative_humidity_2m_max,relative_humidity_2m_min,precipitation_sum,wind_speed_10m_mean"
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={sf}&end_date={ef}&daily={v}&timezone={TZ}&wind_speed_unit=kmh"
    print("[Clima] descargando...")
    d = get(url)["daily"]
    print(f"  {len(d['time'])} dias · {sf} → {ef}")
    return d, sf, ef

def forecast():
    url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&daily=precipitation_sum,wind_speed_10m_max,wind_direction_10m_dominant&forecast_days=10&timezone={TZ}&wind_speed_unit=kmh"
    print("[Pronóstico] descargando...")
    return get(url)["daily"]

def tides():
    url = f"https://www.worldtides.info/api/v3?lat={LAT}&lon={LON}&key={KEY}&days={DAYS}&heights=1&extremes=1&datum=MSL&step=3600"
    print("[Mareas] descargando...")
    d = get(url)
    print(f"  créditos: {d.get('callCount','?')}")
    return d

def moon():
    ref = datetime(2000,1,6,18,14, tzinfo=timezone.utc)
    syn = 29.530588853
    pos = ((datetime.now(timezone.utc)-ref).total_seconds()/86400 % syn)/syn
    ill = round((1-cos(2*pi*pos))/2*100)
    names = ["Luna Nueva","Cuarto Creciente","Cuarto Creciente","Gibosa Creciente",
             "Luna Llena","Gibosa Menguante","Cuarto Menguante","Cuarto Menguante"]
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
    out = []
    today = datetime.now(timezone.utc).date()
    for i in range(DAYS):
        d = today+timedelta(days=i); ds = d.strftime("%Y-%m-%d")
        tide=hi.get(ds,1.2); rain=fp.get(ds,0); wind=fw.get(ds,0); wdir=fd.get(ds,0)
        south = 135<=wdir<=225; sc=0; fx=[]
        if tide>=W3: sc+=3; fx.append("Marea extrema %.2fm" % tide)
        elif tide>=W2: sc+=2; fx.append("Marea alta %.2fm" % tide)
        elif tide>=W1: sc+=1; fx.append("Marea elevada %.2fm" % tide)
        if syzy and i==0: sc+=2; fx.append("Marea de sicigia activa")
        elif d2s<=2 and i<=2: sc+=1; fx.append("Sicigia próxima (%.1fd)" % d2s)
        if south and wind>=WS: sc+=1; fx.append("Viento S %.0fkm/h" % wind)
        if rain>=RM: sc+=1; fx.append("Lluvia %.0fmm pronosticada" % rain)
        if sc>=5:   lv,co,lb="CRÍTICO","#e85050","🔴 CRÍTICO"
        elif sc>=3: lv,co,lb="ALTO","#e8b84b","🟠 ALTO"
        elif sc>=2: lv,co,lb="MODERADO","#e3a733","🟡 MODERADO"
        elif sc>=1: lv,co,lb="BAJO","#52c9a0","🟢 BAJO"
        else:       lv,co,lb="MÍNIMO","#6b7d62","⚪ MÍNIMO"
        # Spanish day names
        dias = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
        meses = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
        dl = "%s %d" % (meses[d.month-1], d.day)
        wd = dias[d.weekday()]
        out.append({"date":ds,"dl":dl,"wd":wd,
                    "tide":round(tide,2),"rain":round(rain,1),"wind":round(wind,1),
                    "south":south,"score":sc,"level":lv,"color":co,"label":lb,"fx":fx})
    return out

def build(monthly, sa, kp, rs, mn, tide_data, s_date, e_date):
    MN  = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    MNF = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio",
           "Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
    gt  = (datetime.now(timezone.utc) + timedelta(hours=-6)).strftime("%d de %B de %Y a las %H:%M hora Guatemala")
    mname,memoji,mill,md2s,msyzy = mn
    tr = rs[0]

    th=[]; tv=[]
    for h in tide_data.get("heights",[]):
        th.append(datetime.fromtimestamp(h["dt"],tz=timezone.utc).strftime("%d/%m %H:%M"))
        tv.append(round(h["height"],2))
    th3=th[::3]; tv3=tv[::3]

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

    rdates  = [r["dl"]    for r in rs]
    rscores = [r["score"] for r in rs]
    rcolors = [r["color"] for r in rs]
    rtides  = [r["tide"]  for r in rs]

    emax = max((sa[m]["evap"] or 0) for m in range(1,13))
    rows = ""
    for m in range(1,13):
        r = sa[m]
        er = (r["evap"] or 0)/emax if emax else 0
        bg = "evap-high" if er>0.65 else ("evap-med" if er>0.35 else "evap-low")
        bt = "Alto ↑"    if er>0.65 else ("Medio →" if er>0.35 else "Bajo ↓")
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

    bmap = {"CRÍTICO":("#e85050","rgba(232,80,80,.15)","#5c1010"),
            "ALTO":   ("#e8b84b","rgba(232,184,75,.15)","#6b4f10"),
            "MODERADO":("#e3a733","rgba(232,184,75,.08)","#6b4f10"),
            "BAJO":   ("#52c9a0","rgba(82,201,160,.08)","#1a5c43"),
            "MÍNIMO": ("#6b7d62","rgba(107,125,98,.08)","#2a3025")}
    bco,bbg,bbd = bmap[tr["level"]]
    tfx = "".join("<span class='ab-factor'>%s</span>" % x for x in tr["fx"]) or "<span class='ab-factor' style='color:#6b7d62'>Sin factores de riesgo significativos hoy</span>"

    rcards = ""
    for r in rs[:10]:
        fhtml = "".join("<div class='risk-factor'>%s</div>" % x for x in r["fx"]) or "<div class='risk-factor' style='color:#6b7d62'>Sin factores de riesgo</div>"
        rcards += "<div class='risk-card' style='border-top-color:%s'><div class='rc-date'>%s<span class='rc-day'>%s</span></div><div class='rc-tide'>%sm</div><div class='rc-label' style='color:%s'>%s</div><div class='rc-factors'>%s</div><div class='rc-stats'><span>🌧 %smm</span><span>💨 %skm/h%s</span></div></div>" % (
            r["color"], r["dl"], r["wd"], r["tide"], r["color"], r["label"],
            fhtml, r["rain"], r["wind"], " ↙S" if r["south"] else "")

    d2s_warn = "⚠ Sicigia inminente" if md2s<=3 else "Próxima luna nueva/llena"
    d2s_cls  = "amber" if md2s<=3 else "teal"
    tr_kpi_cls = "red" if tr["level"] in ["CRÍTICO","ALTO"] else "teal"
    k = kp

    js_data = "var TH=%s;var TV=%s;var W1=%s;var W2=%s;var W3=%s;var RD=%s;var RS=%s;var RC=%s;var RT=%s;var CL=%s;var CMAX=%s;var CMIN=%s;var CMN=%s;var CRH=%s;var CPR=%s;var CWI=%s;var CEV=%s;" % (
        jl(th3),jl(tv3),W1,W2,W3,
        jl(rdates),jl(rscores),jl(rcolors),jl(rtides),
        jl(lbs),jl(tmax_s),jl(tmin_s),jl(tmean_s),
        jl(rh_s),jl(prec_s),jl(wind_s),jl(evap_s))

    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Salinas Maya Natural — Panel Climático y de Mareas</title>
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

    parts.append("""<header>
  <div class="h-title">
    <div class="h-badge">🧂</div>
    <div>
      <h1>Salinas Maya Natural — <em>Panel Climático y de Mareas</em></h1>
      <div class="h-sub">Registro histórico · Pronóstico de mareas 10 días · Índice de riesgo · Actualización diaria automática</div>
    </div>
  </div>
  <div class="h-right">
    <div class="tag tag-coords">13.8262°N, 90.2971°W · Chiquimulilla, Santa Rosa, GT</div>
""")
    parts.append('    <div class="tag tag-moon">%s %s &middot; %s%% &middot; %sd a sicigia</div>\n' % (memoji, mname, mill, md2s))
    parts.append('    <div class="tag tag-update">&#8635; Actualizado %s</div>\n' % gt)
    parts.append("""  </div>
</header>
""")

    parts.append('<div class="alert-banner" style="border:1px solid %s;background:%s">\n' % (bbd, bbg))
    parts.append('  <div style="font-size:36px">%s</div>\n' % tr["label"].split()[0])
    parts.append('  <div class="ab-main">\n')
    parts.append('    <div class="ab-title" style="color:%s">Riesgo de inundación hoy: %s</div>\n' % (bco, tr["level"]))
    parts.append('    <div class="ab-sub">Marea máx: %sm &middot; Lluvia: %smm &middot; Viento: %s km/h &middot; %s %s</div>\n' % (tr["tide"], tr["rain"], tr["wind"], memoji, mname))
    parts.append('    <div class="ab-factors">%s</div>\n' % tfx)
    parts.append("""  </div>
</div>
""")

    parts.append("""<div class="tabs">
  <button class="tab active" onclick="switchTab('mareas',this)">🌊 Pronóstico Mareas</button>
  <button class="tab" onclick="switchTab('riesgo',this)">⚠ Índice de Riesgo</button>
  <button class="tab" onclick="switchTab('clima',this)">📊 Registro Climático</button>
  <button class="tab" onclick="switchTab('estacional',this)">📅 Patrón Estacional</button>
</div>
""")

    # Tab: Mareas
    parts.append("""<div id="tab-mareas" class="panel active">
  <div class="kpi-grid">
""")
    parts.append('    <div class="kpi %s"><div class="kpi-label">Marea máxima hoy</div><div class="kpi-val" style="color:%s">%s<span class="kpi-unit">m</span></div><div class="kpi-sub">Riesgo: %s</div></div>\n' % (tr_kpi_cls, bco, tr["tide"], tr["level"]))
    parts.append('    <div class="kpi amber"><div class="kpi-label">Fase lunar</div><div class="kpi-val" style="font-size:32px">%s</div><div class="kpi-sub">%s &middot; %s%% iluminada</div></div>\n' % (memoji, mname, mill))
    parts.append('    <div class="kpi %s"><div class="kpi-label">Días a sicigia</div><div class="kpi-val">%s<span class="kpi-unit">d</span></div><div class="kpi-sub">%s</div></div>\n' % (d2s_cls, md2s, d2s_warn))
    parts.append('    <div class="kpi blue"><div class="kpi-label">Umbral crítico</div><div class="kpi-val">%.1f<span class="kpi-unit">m</span></div><div class="kpi-sub">Ref. inundación 28 abr 2024</div></div>\n' % W3)
    parts.append("""  </div>
  <div class="sec-title">Mareas hora a hora — próximos 10 días (WorldTides · MSL)</div>
  <div class="chart-card">
    <div class="chart-wrap-lg"><canvas id="chart-tides"></canvas></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--blue)"></div>Altura de marea (m)</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--red);opacity:.6"></div>Umbral crítico</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--amber);opacity:.6"></div>Umbral de alerta</div>
    </div>
  </div>
  <div class="sec-title">Calendario de riesgo 10 días</div>
  <div class="risk-grid">
""")
    parts.append(rcards)
    parts.append("  </div>\n</div>\n")

    # Tab: Riesgo
    parts.append("""<div id="tab-riesgo" class="panel">
  <div class="chart-card" style="margin-bottom:20px;font-size:12px;color:var(--muted);line-height:1.9">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div>
        <div style="color:var(--text);font-weight:500;margin-bottom:8px">Factores de riesgo diarios:</div>
""")
    parts.append('        <div>Marea &ge; %.1fm +1pt | &ge;%.1fm +2pts | &ge;%.1fm +3pts</div>\n' % (W1,W2,W3))
    parts.append("""        <div>Sicigia activa (luna nueva/llena) +2pts</div>
        <div>Sicigia próxima (&le;2 días) +1pt</div>
""")
    parts.append('        <div>Viento sur &ge; %d km/h +1pt</div>\n' % WS)
    parts.append('        <div>Lluvia pronosticada &ge; %dmm +1pt</div>\n' % RM)
    parts.append("""      </div>
      <div>
        <div style="color:var(--text);font-weight:500;margin-bottom:8px">Niveles de riesgo:</div>
        <div><span style="color:var(--red)">🔴 CRÍTICO</span> &ge;5 pts &middot; Proteger eras inmediatamente</div>
        <div><span style="color:var(--amber)">🟠 ALTO</span> &ge;3 pts &middot; Inspeccionar diques, monitoreo horario</div>
        <div><span style="color:var(--amber)">🟡 MODERADO</span> &ge;2 pts &middot; Vigilancia elevada</div>
        <div><span style="color:var(--teal)">🟢 BAJO</span> &ge;1 pt &middot; Operación normal</div>
        <div><span style="color:var(--muted)">⚪ MÍNIMO</span> 0 pts &middot; Condiciones despejadas</div>
      </div>
    </div>
    <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border)">
      &#x26a0; Calibrado al <strong style="color:var(--text)">evento de inundación del 28 de abril de 2024</strong>.
      El modelo habría emitido una <strong style="color:var(--red)">alerta CRÍTICA 5 días antes</strong>.
    </div>
  </div>
  <div class="sec-title">Puntuación de riesgo 10 días y altura de marea</div>
  <div class="chart-card"><div class="chart-wrap"><canvas id="chart-risk"></canvas></div></div>
</div>
""")

    # Tab: Clima
    parts.append('<div id="tab-clima" class="panel">\n  <div class="kpi-grid">\n')
    parts.append('    <div class="kpi coral"><div class="kpi-label">Temp. máx. prom.</div><div class="kpi-val">%s<span class="kpi-unit">&deg;C</span></div><div class="kpi-sub">Pico: %s&deg;C</div></div>\n' % (k["avg_tmax"], k["peak_tmax"]))
    parts.append('    <div class="kpi blue"><div class="kpi-label">Temp. mín. prom.</div><div class="kpi-val">%s<span class="kpi-unit">&deg;C</span></div><div class="kpi-sub">Valle: %s&deg;C</div></div>\n' % (k["avg_tmin"], k["low_tmin"]))
    parts.append('    <div class="kpi teal"><div class="kpi-label">Humedad promedio</div><div class="kpi-val">%s<span class="kpi-unit">%%</span></div><div class="kpi-sub">Humedad relativa mensual</div></div>\n' % k["avg_rh"])
    parts.append('    <div class="kpi blue"><div class="kpi-label">Lluvia anual est.</div><div class="kpi-val">%d<span class="kpi-unit">mm</span></div><div class="kpi-sub">%s mm/mes promedio</div></div>\n' % (int(k["avg_rain_yr"]), k["avg_rain_mo"]))
    parts.append('    <div class="kpi purple"><div class="kpi-label">Viento promedio</div><div class="kpi-val">%s<span class="kpi-unit">km/h</span></div><div class="kpi-sub">A 10m de altura</div></div>\n' % k["avg_wind"])
    parts.append('    <div class="kpi amber"><div class="kpi-label">Índice evap. prom.</div><div class="kpi-val">%s<span class="kpi-unit">pts</span></div><div class="kpi-sub">Potencial producción de sal</div></div>\n' % k["avg_evap"])
    parts.append("""  </div>
  <div class="sec-title">Registro de temperatura mensual</div>
  <div class="chart-card">
    <div class="chart-wrap"><canvas id="chart-temp"></canvas></div>
    <div class="legend">
      <div class="legend-item"><div class="legend-dot" style="background:var(--coral)"></div>Máxima</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--blue)"></div>Mínima</div>
      <div class="legend-item"><div class="legend-dot" style="background:var(--amber)"></div>Media</div>
    </div>
  </div>
  <div class="two-col">
    <div>
      <div class="sec-title">Humedad relativa (%)</div>
      <div class="chart-card"><div class="chart-wrap"><canvas id="chart-hum"></canvas></div></div>
    </div>
    <div>
      <div class="sec-title">Precipitación mensual total (mm)</div>
      <div class="chart-card"><div class="chart-wrap"><canvas id="chart-prec"></canvas></div></div>
    </div>
  </div>
  <div class="sec-title">Índice de evaporación — potencial producción de sal</div>
  <div class="chart-card">
    <div style="font-size:11px;color:var(--muted);margin-bottom:12px">Fórmula: Evap = (T_máx &times; (1 &minus; HR/100) &times; &radic;Viento) / 10</div>
    <div class="chart-wrap"><canvas id="chart-evap"></canvas></div>
  </div>
</div>
""")

    # Tab: Estacional
    parts.append("""<div id="tab-estacional" class="panel">
  <div class="chart-card">
    <div style="font-size:11px;color:var(--muted);margin-bottom:6px">⚠ = meses con riesgo histórico elevado de inundación por mareas</div>
    <div class="season-bar">
      <div class="seg seg-dry" style="width:33.3%">Seca (Ene–Abr)</div>
      <div class="seg seg-wet" style="width:50%">Lluviosa (May–Oct)</div>
      <div class="seg seg-dry" style="width:16.7%">Seca (Nov–Dic)</div>
    </div>
    <div style="overflow-x:auto;margin-top:16px">
      <table>
        <thead><tr><th>Mes</th><th>Máx &deg;C</th><th>Mín &deg;C</th><th>Humedad %</th><th>Lluvia mm</th><th>Viento km/h</th><th>Índice evap.</th></tr></thead>
        <tbody>
""")
    parts.append(rows)
    parts.append("""        </tbody>
      </table>
    </div>
  </div>
</div>
""")

    parts.append('<footer>\n')
    parts.append('  <span>Clima: Open-Meteo ERA5-Land &middot; ECMWF</span>\n')
    parts.append('  <span>Mareas: WorldTides API &middot; datum MSL</span>\n')
    parts.append('  <span>13.8262&deg;N, 90.2971&deg;W &middot; Chiquimulilla, Santa Rosa, Guatemala</span>\n')
    parts.append('  <span>Actualización automática diaria 06:00 AM GT &middot; Última ejecución: %s</span>\n' % gt)
    parts.append('</footer>\n')

    parts.append('<script>\n')
    parts.append(js_data + "\n")
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
    {label:'Marea (m)',data:TV,borderColor:'#70b8e8',backgroundColor:'rgba(112,184,232,.12)',fill:true,tension:.4,pointRadius:0,borderWidth:2},
    {label:'Crítico',data:Array(TH.length).fill(W3),borderColor:'rgba(232,80,80,.6)',borderDash:[4,4],backgroundColor:'transparent',fill:false,pointRadius:0,borderWidth:1.5},
    {label:'Alerta', data:Array(TH.length).fill(W1),borderColor:'rgba(232,184,75,.4)',borderDash:[4,4],backgroundColor:'transparent',fill:false,pointRadius:0,borderWidth:1}
  ]},options:{...bO,plugins:{...bO.plugins,legend:{display:true,labels:{color:'#6b7d62',boxWidth:24,font:{size:11}}}},
    scales:{...bO.scales,y:{...bO.scales.y,min:Math.floor((Math.min.apply(null,TV)-0.3)*2)/2,max:Math.ceil((Math.max.apply(null,TV.concat([W3]))+0.3)*2)/2,title:{display:true,text:'metros (MSL)',color:'#6b7d62',font:{size:10}}}}}});
}

function initRisk(){
  mk('chart-risk',{type:'bar',data:{labels:RD,datasets:[
    {type:'bar',label:'Puntuación riesgo',data:RS,backgroundColor:RC.map(function(c){return c+'99';}),borderColor:RC,borderWidth:1,borderRadius:4,yAxisID:'y1'},
    {type:'line',label:'Marea máx (m)',data:RT,borderColor:'#70b8e8',backgroundColor:'rgba(112,184,232,.1)',fill:true,tension:.4,pointRadius:4,pointBackgroundColor:'#70b8e8',borderWidth:2,yAxisID:'y2'}
  ]},options:{responsive:true,maintainAspectRatio:false,
    plugins:{legend:{display:true,labels:{color:'#6b7d62',boxWidth:12,font:{size:11}}},tooltip:{mode:'index',intersect:false,backgroundColor:'#1c2117',borderColor:'#2a3025',borderWidth:1,titleColor:'#dde8d4',bodyColor:'#6b7d62',padding:10}},
    scales:{x:{grid:{color:G}},
      y1:{type:'linear',position:'left',grid:{color:G},min:0,max:8,ticks:{stepSize:1},title:{display:true,text:'Puntuación riesgo',color:'#6b7d62',font:{size:10}}},
      y2:{type:'linear',position:'right',grid:{display:false},min:0,max:3.5,title:{display:true,text:'Marea (m)',color:'#70b8e8',font:{size:10}},ticks:{color:'#70b8e8'}}}}});
}

function initClimate(){
  mk('chart-temp',{type:'line',data:{labels:CL,datasets:[
    {label:'Máx', data:CMAX,borderColor:'#e87070',fill:false,tension:.35,pointRadius:0,borderWidth:1.5},
    {label:'Mín', data:CMIN,borderColor:'#70b8e8',fill:false,tension:.35,pointRadius:0,borderWidth:1.5},
    {label:'Media',data:CMN, borderColor:'#e8b84b',fill:false,tension:.35,pointRadius:0,borderWidth:1,borderDash:[4,3]}
  ]},options:{...bO,plugins:{...bO.plugins,legend:{display:true,labels:{color:'#6b7d62',boxWidth:12,font:{size:11}}}}}});
  mk('chart-hum',{type:'line',data:{labels:CL,datasets:[
    {label:'HR%',data:CRH,borderColor:'#52c9a0',backgroundColor:'rgba(82,201,160,.1)',fill:true,tension:.4,pointRadius:0,borderWidth:1.5}
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

function switchTab(id,el){
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});
  document.getElementById('tab-'+id).classList.add('active');
  el.classList.add('active');
  if(id==='mareas')    initTides();
  if(id==='riesgo')    initRisk();
  if(id==='clima')     initClimate();
}

initTides();
""")
    parts.append('</script>\n</body>\n</html>\n')
    return "".join(parts)


def main():
    print("="*60)
    print("Actualización:", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print("="*60)
    mn = moon()
    print("[Luna] %s %s · %d%% · %.1fd a sicigia" % (mn[1],mn[0],mn[2],mn[3]))
    daily, s, e = climate()
    fc = forecast()
    td = tides()
    monthly, sa = process_climate(daily)
    kp = calc_kpis(monthly)
    rs = calc_risks(td, fc, mn)
    print("[Riesgo] Hoy: %s (puntuación %d) · marea %.2fm" % (rs[0]["level"],rs[0]["score"],rs[0]["tide"]))
    html = build(monthly, sa, kp, rs, mn, td, s, e)
    Path(OUT).write_text(html, encoding="utf-8")
    print("✓ Generado: %s (%.1f KB)" % (OUT, Path(OUT).stat().st_size/1024))

if __name__ == "__main__":
    main()
